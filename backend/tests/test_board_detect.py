"""Company career board auto-detection, the known-board starter list and the Quick start panel.

The network is always mocked: board API answers replay the recorded fixtures of
``tests/fixtures/boards/`` and company web pages are small inline HTML documents, both
served by one ``httpx.MockTransport`` installed on the board HTTP layer and on the
detector (see ``_no_job_board_network`` in ``conftest.py``). The one live test is opt-in:
``JOBPILOT_LIVE_BOARDS=1 pytest tests/test_board_detect.py -k live``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import CompanyPriority, JobSourceType
from app.models.profile import CompanyPreference
from app.modules.adapters.boards import http as board_http
from app.modules.companies import board_detect
from app.modules.companies import service as companies_service
from app.modules.companies.board_detect import (
    MAX_REQUESTS,
    candidate_tokens,
    detect_board,
    find_board_urls,
    find_careers_link,
    find_known_board,
    known_boards,
    tag_rank,
)

FIXTURES = Path(__file__).parent / "fixtures" / "boards"
COMPANIES = "/api/v1/companies"

GH_API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
LEVER_API = "https://api.lever.co/v0/postings/{token}"
ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/{token}"
SR_API = "https://api.smartrecruiters.com/v1/companies/{token}/postings"

#: One recorded board per vendor (three open postings each).
VENDOR_BOARDS: dict[JobSourceType, tuple[str, str]] = {
    JobSourceType.GREENHOUSE: (GH_API, "greenhouse_stripe.json"),
    JobSourceType.LEVER: (LEVER_API, "lever_zoox.json"),
    JobSourceType.ASHBY: (ASHBY_API, "ashby_ramp.json"),
    JobSourceType.SMARTRECRUITERS: (SR_API, "smartrecruiters_servicenow.json"),
}


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeWeb:
    """Board APIs, web pages and robots.txt files keyed by ``scheme://host/path``; counts every request.

    Unknown URLs answer 404 (for a robots.txt that means "everything allowed").
    """

    def __init__(self) -> None:
        self.routes: dict[str, httpx.Response | Any] = {}
        self.requests: list[httpx.Request] = []

    def board(self, vendor: JobSourceType, token: str) -> "FakeWeb":
        api, fixture = VENDOR_BOARDS[vendor]
        self.routes[api.format(token=token)] = ("json", 200, load(fixture), {})
        return self

    def json(self, url: str, body: Any, status: int = 200) -> "FakeWeb":
        self.routes[url] = ("json", status, body, {})
        return self

    def page(self, url: str, body: str, *, status: int = 200, content_type: str = "text/html; charset=utf-8") -> "FakeWeb":
        self.routes[url] = ("text", status, body, {"content-type": content_type})
        return self

    def redirect(self, url: str, location: str, status: int = 302) -> "FakeWeb":
        self.routes[url] = ("text", status, "", {"location": location})
        return self

    def urls(self) -> list[str]:
        return [f"{r.url.scheme}://{r.url.host}{r.url.path}" for r in self.requests]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.url.scheme}://{request.url.host}{request.url.path}"
        if key not in self.routes:
            return httpx.Response(404, json={"error": "not found"})
        kind, status, body, headers = self.routes[key]
        if kind == "json":
            return httpx.Response(status, json=body, headers=headers)
        return httpx.Response(status, text=body, headers=headers)


@pytest.fixture
def web() -> FakeWeb:
    fake = FakeWeb()
    transport = httpx.MockTransport(fake)
    board_http.set_transport(transport)
    board_detect.set_transport(transport)
    board_http.clear_cache()
    return fake


@pytest.fixture
def user(db: Session):
    from app.modules.auth.service import create_user

    created = create_user(db, "detect@example.com", "StrongPass123", "Detect Tester")
    db.commit()
    return created


def _home(*links: tuple[str, str], extra: str = "") -> str:
    anchors = "".join(f'<a href="{href}">{text}</a>' for href, text in links)
    return f"<html><body><nav><a href='/about'>About</a>{anchors}</nav>{extra}</body></html>"


# --------------------------------------------------------------------------- the known list


def test_the_known_list_is_large_valid_and_uses_only_readable_vendors():
    boards = known_boards()
    assert len(boards) >= 150
    assert {b.ats_type for b in boards} <= {
        JobSourceType.GREENHOUSE,
        JobSourceType.LEVER,
        JobSourceType.ASHBY,
        JobSourceType.SMARTRECRUITERS,
    }
    names = [companies_service.normalize_company_name(b.name) for b in boards]
    assert len(names) == len(set(names)), "duplicate company in known_boards.json"
    # The Step 2 starter boards are all still there.
    for name, token in (("Stripe", "stripe"), ("Spotify", "spotify"), ("Ramp", "ramp"), ("Bosch", "BoschGroup")):
        assert find_known_board(name, None).token == token


def test_known_boards_match_by_domain_subdomain_alias_and_name():
    assert find_known_board(None, "https://careers.stripe.com/jobs").token == "stripe"
    assert find_known_board(None, "www.notion.so").token == "notion"
    assert find_known_board("Stripe, Inc.", None).token == "stripe"
    assert find_known_board("Anysphere", None).name == "Cursor"
    assert find_known_board("Acme Robotics", "https://acme.example") is None


def test_candidate_tokens_come_from_the_domain_and_the_name():
    assert candidate_tokens("Stripe Inc", None) == ["stripe", "stripeinc", "stripe-inc"]
    assert candidate_tokens("Acme Robotics", "https://www.acme.co.in/about") == ["acme", "acmerobotics", "acme-robotics"]
    assert candidate_tokens(None, None) == []


def test_tag_rank_orders_faang_unicorn_product_startup():
    assert [tag_rank([t]) for t in ("FAANG", "unicorn", "product", "startup", "india")] == [0, 1, 2, 3, 4]
    assert tag_rank(["startup", "unicorn"]) == 1


def test_known_hit_is_verified_with_one_fetch(web: FakeWeb):
    web.board(JobSourceType.GREENHOUSE, "stripe")
    result = detect_board("Stripe", None)
    assert result.method == "KNOWN"
    assert (result.ats_type, result.token, result.open_jobs, result.supported) == ("GREENHOUSE", "stripe", 3, True)
    assert result.board_url == "https://job-boards.greenhouse.io/stripe"
    assert result.board_company == "Stripe"  # read from the cached answer, no second request
    assert result.requests == 1 and len(web.requests) == 1
    assert web.requests[0].headers["user-agent"].startswith("JobPilot/")


def test_a_known_board_that_is_gone_falls_through_to_the_guess(web: FakeWeb):
    # Stripe's known GREENHOUSE board answers 404 here; the guess finds it on Lever instead.
    web.board(JobSourceType.LEVER, "stripe")
    result = detect_board("Stripe", None)
    assert result.method == "GUESS" and result.ats_type == "LEVER"
    assert GH_API.format(token="stripe") in web.urls()
    assert web.urls().count(GH_API.format(token="stripe")) == 1  # the known board is not probed twice


# --------------------------------------------------------------------------- token guess


@pytest.mark.parametrize("vendor", list(VENDOR_BOARDS))
def test_guess_hit_for_each_vendor(web: FakeWeb, vendor: JobSourceType):
    web.board(vendor, "acmerobotics")
    if vendor is not JobSourceType.SMARTRECRUITERS:
        # SmartRecruiters answers 200 with an empty list for an unknown company.
        web.json(SR_API.format(token="acmerobotics"), {"totalFound": 0, "content": []})
    result = detect_board("Acme Robotics", None)
    assert result.method == "GUESS"
    assert (result.ats_type, result.token, result.open_jobs) == (vendor.value, "acmerobotics", 3)
    assert any("3 open jobs" in line for line in result.tried)
    # Greenhouse and SmartRecruiters name the board's company, so a namesake's board shows.
    expected = {JobSourceType.GREENHOUSE: "Stripe", JobSourceType.SMARTRECRUITERS: "ServiceNow"}.get(vendor)
    assert result.board_company == expected


def test_an_empty_smartrecruiters_answer_is_not_a_hit(web: FakeWeb):
    web.json(SR_API.format(token="acmerobotics"), {"totalFound": 0, "content": []})
    result = detect_board("Acme Robotics", None)
    assert result.method == "NONE" and result.ats_type is None
    assert any("SMARTRECRUITERS/acmerobotics - no open jobs" in line for line in result.tried)


# --------------------------------------------------------------------------- careers page scan

SCAN_PATTERNS = [
    ("https://boards.greenhouse.io/acmecareers", JobSourceType.GREENHOUSE, "acmecareers"),
    ("https://jobs.lever.co/acmecareers/0b1c2d3e-apply", JobSourceType.LEVER, "acmecareers"),
    ("https://jobs.ashbyhq.com/acmecareers", JobSourceType.ASHBY, "acmecareers"),
    ("https://careers.smartrecruiters.com/AcmeCareers", JobSourceType.SMARTRECRUITERS, "AcmeCareers"),
]


@pytest.mark.parametrize("board_url, vendor, token", SCAN_PATTERNS)
def test_scan_hit_for_each_pattern(web: FakeWeb, board_url: str, vendor: JobSourceType, token: str):
    web.page("https://acme.example/", _home(("/careers", "Careers")))
    web.page("https://acme.example/careers", f"<h1>Join us</h1><a href='{board_url}'>See open roles</a>")
    web.board(vendor, token)
    result = detect_board("Acme Robotics", "acme.example")
    assert result.method == "SCAN", result.tried
    assert (result.ats_type, result.token, result.open_jobs) == (vendor.value, token, 3)
    assert result.careers_url == "https://acme.example/careers"
    assert result.requests <= MAX_REQUESTS and len(web.requests) == result.requests
    assert "https://acme.example/robots.txt" in web.urls()


def test_scan_finds_a_greenhouse_embed_on_the_home_page(web: FakeWeb):
    script = '<script src="https://boards.greenhouse.io/embed/job_board/js?for=acmecareers"></script>'
    web.page("https://acme.example/", _home(extra=script))
    web.board(JobSourceType.GREENHOUSE, "acmecareers")
    result = detect_board("Acme Robotics", "https://acme.example")
    assert (result.method, result.token) == ("SCAN", "acmecareers")
    assert "https://acme.example/careers" not in web.urls()


def test_scan_follows_a_careers_link_that_redirects_to_a_hosted_board(web: FakeWeb):
    web.page("https://acme.example/", _home(("/jobs", "Jobs")))
    web.redirect("https://acme.example/jobs", "https://jobs.ashbyhq.com/acmecareers")
    web.board(JobSourceType.ASHBY, "acmecareers")
    result = detect_board("Acme Robotics", "acme.example")
    assert (result.method, result.ats_type, result.token) == ("SCAN", "ASHBY", "acmecareers")
    assert "https://jobs.ashbyhq.com/acmecareers" not in web.urls()  # the hosted page itself is never fetched


def test_scan_recognises_workday_but_does_not_claim_to_read_it(web: FakeWeb):
    web.page("https://acme.example/", _home(("/careers", "Careers")))
    web.page("https://acme.example/careers", "<a href='https://acme.wd5.myworkdayjobs.com/en-US/External'>Apply</a>")
    result = detect_board("Acme Robotics", "acme.example")
    assert result.method == "SCAN"
    assert (result.ats_type, result.token, result.supported, result.open_jobs) == ("WORKDAY", "acme", False, None)
    assert result.board_url == "https://acme.wd5.myworkdayjobs.com/en-US/External"


def test_robots_disallow_skips_the_scan(web: FakeWeb):
    web.page("https://acme.example/robots.txt", "User-agent: *\nDisallow: /\n", content_type="text/plain")
    web.page("https://acme.example/", _home(extra="https://boards.greenhouse.io/acmecareers"))
    web.board(JobSourceType.GREENHOUSE, "acmecareers")
    result = detect_board("Acme Robotics", "acme.example")
    assert result.method == "NONE"
    assert any("robots.txt disallows" in line for line in result.tried)
    assert "https://acme.example/" not in web.urls()


def test_robots_rules_for_jobpilot_are_honoured_on_the_careers_host(web: FakeWeb):
    web.page("https://acme.example/", _home(("https://careers.acme.example/", "Careers")))
    web.page("https://careers.acme.example/robots.txt", "User-agent: JobPilot\nDisallow: /\n", content_type="text/plain")
    web.page("https://careers.acme.example/", "https://jobs.lever.co/acmecareers")
    web.board(JobSourceType.LEVER, "acmecareers")
    result = detect_board("Acme Robotics", "acme.example")
    assert result.method == "NONE"
    assert "https://careers.acme.example/" not in web.urls()
    assert result.careers_url == "https://careers.acme.example/"


def test_an_unreadable_robots_txt_skips_the_scan(web: FakeWeb):
    web.page("https://acme.example/robots.txt", "oops", status=503)
    web.page("https://acme.example/", _home(extra="https://jobs.lever.co/acmecareers"))
    result = detect_board(None, "acme.example")
    assert result.method == "NONE"
    assert any("robots.txt could not be read" in line for line in result.tried)


def test_login_links_and_login_redirects_are_never_followed(web: FakeWeb):
    assert find_careers_link(_home(("/login?next=/careers", "Careers portal sign in"), ("/jobs", "Jobs")), "https://a.example/") == (
        "https://a.example/jobs"
    )
    web.page("https://acme.example/", _home(("/careers", "Careers")))
    web.redirect("https://acme.example/careers", "https://acme.example/account/login?return=/careers")
    result = detect_board(None, "acme.example")
    assert result.method == "NONE"
    assert any("leads to a login" in line for line in result.tried)
    assert "https://acme.example/account/login" not in web.urls()


def test_private_addresses_are_never_fetched(web: FakeWeb):
    for website in ("http://127.0.0.1/", "http://localhost:8000/", "http://169.254.169.254/latest/meta-data"):
        result = detect_board(None, website)
        assert result.method == "NONE"
    board_detect.set_resolver(lambda host: ["10.0.0.7"])
    result = detect_board(None, "https://intranet.acme.example")
    assert any("public address" in line for line in result.tried)
    assert not [u for u in web.urls() if "127.0.0.1" in u or "localhost" in u or "169.254" in u or "acme.example" in u]


def test_request_cap_of_eight_is_respected_with_a_website(web: FakeWeb):
    # Everything misses and every page redirects once: an uncapped detector would go far past 8.
    web.redirect("https://acme.example/robots.txt", "https://www.acme.example/robots.txt")
    web.redirect("https://acme.example/", "https://www.acme.example/")
    web.page("https://www.acme.example/", _home(("/careers", "Careers"), ("/jobs", "Jobs")))
    web.redirect("https://www.acme.example/careers", "https://www.acme.example/careers/")
    web.page("https://www.acme.example/careers/", "<a href='https://jobs.lever.co/a1'>x</a><a href='https://jobs.ashbyhq.com/a2'>y</a>")
    result = detect_board("Acme Robotics Platform Group", "acme.example")
    assert len(web.requests) <= MAX_REQUESTS
    assert result.requests == len(web.requests)
    assert result.method == "NONE"


def test_request_cap_of_eight_is_respected_with_a_long_name(web: FakeWeb):
    result = detect_board("Very Long Example Name Holdings Worldwide", None)
    assert result.method == "NONE"
    assert len(web.requests) == result.requests == MAX_REQUESTS


def test_no_result_lists_what_was_tried(web: FakeWeb):
    result = detect_board("Acme Robotics", None)
    assert result.method == "NONE" and result.ats_type is None and result.token is None
    assert "known: not on the known-board list" in result.tried
    assert any(line.startswith("guess: GREENHOUSE/acmerobotics") for line in result.tried)
    assert "scan: no website given" in result.tried


def test_nothing_to_look_up():
    result = detect_board("  ", None)
    assert result.method == "NONE" and result.requests == 0


def test_the_conftest_guard_blocks_detection_pages_too():
    result = detect_board("Acme Robotics", "https://acme.example")
    assert result.method == "NONE"
    assert any("could not fetch https://acme.example/robots.txt" in line for line in result.tried)


def test_find_board_urls_handles_escaped_and_scheme_less_urls():
    text = 'x = "https:\\/\\/jobs.lever.co\\/acme\\/123"; jobs.ashbyhq.com/acme2. <a href="//boards.greenhouse.io/acme3?t=1">'
    assert find_board_urls(text) == [
        (JobSourceType.LEVER, "acme"),
        (JobSourceType.ASHBY, "acme2"),
        (JobSourceType.GREENHOUSE, "acme3"),
    ]
    assert find_board_urls("https://www.greenhouse.io/privacy https://boards.greenhouse.io/embed/job_board") == []


# --------------------------------------------------------------------------- API


def test_detect_board_endpoint_does_not_persist(auth_client, db: Session, web: FakeWeb):
    web.board(JobSourceType.GREENHOUSE, "stripe")
    response = auth_client.post(f"{COMPANIES}/detect-board", json={"name": "Stripe", "website": "https://stripe.com"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["method"] == "KNOWN" and body["ats_type"] == "GREENHOUSE" and body["open_jobs"] == 3
    assert db.scalar(select(func.count(Company.id))) == 0

    empty = auth_client.post(f"{COMPANIES}/detect-board", json={"name": " ", "website": ""})
    assert empty.status_code == 422 and empty.json()["error"]["code"] == "detect_input_required"


def test_post_companies_auto_detects_and_stores_the_board(auth_client, db: Session, web: FakeWeb):
    web.board(JobSourceType.ASHBY, "ramp")
    created = auth_client.post(COMPANIES, json={"name": "Ramp"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["detection"]["method"] == "KNOWN" and body["detection_saved"] is True
    assert (body["ats_type"], body["ats_board_token"], body["ats_board_url"]) == ("ASHBY", "ramp", "https://jobs.ashbyhq.com/ramp")
    assert body["domain"] == "ramp.com"  # a known hit also fills the domain

    # Already configured: re-adding runs no detection and makes no request.
    before = len(web.requests)
    again = auth_client.post(COMPANIES, json={"name": "Ramp"})
    assert again.status_code == 201 and again.json()["detection"] is None
    assert len(web.requests) == before


def test_post_companies_without_auto_detect_or_without_a_result(auth_client, db: Session, web: FakeWeb):
    off = auth_client.post(COMPANIES, json={"name": "Stripe", "auto_detect": False})
    assert off.status_code == 201 and off.json()["detection"] is None and off.json()["ats_board_token"] is None
    assert web.requests == []

    nothing = auth_client.post(COMPANIES, json={"name": "Acme Robotics"})
    assert nothing.status_code == 201
    body = nothing.json()
    assert body["detection"]["method"] == "NONE" and body["detection_saved"] is False
    assert body["ats_board_token"] is None and body["detection"]["tried"]


def test_detect_for_an_existing_company_stores_a_found_board(auth_client, db: Session, web: FakeWeb):
    company = companies_service.get_or_create_company(db, "Acme Robotics", website="https://acme.example")
    db.commit()
    missing = auth_client.post(f"{COMPANIES}/{company.id}/detect-board")
    assert missing.status_code == 200
    assert missing.json()["detection"]["method"] == "NONE" and missing.json()["ats_board_token"] is None

    web.page("https://acme.example/", _home(("/careers", "Careers")))
    web.page("https://acme.example/careers", "<a href='https://jobs.lever.co/acmecareers'>Open roles</a>")
    web.board(JobSourceType.LEVER, "acmecareers")
    found = auth_client.post(f"{COMPANIES}/{company.id}/detect-board")
    assert found.status_code == 200, found.text
    body = found.json()
    assert body["detection"]["method"] == "SCAN" and body["detection_saved"] is True
    assert (body["ats_type"], body["ats_board_token"]) == ("LEVER", "acmecareers")
    assert body["careers_url"] == "https://acme.example/careers"

    assert auth_client.post(f"{COMPANIES}/00000000-0000-0000-0000-000000000000/detect-board").status_code == 404


def test_a_workday_result_is_recorded_without_a_board_token(auth_client, db: Session, web: FakeWeb):
    company = companies_service.get_or_create_company(db, "Acme Robotics", website="https://acme.example")
    db.commit()
    web.page("https://acme.example/", _home(("https://acme.wd1.myworkdayjobs.com/Careers", "Careers")))
    body = auth_client.post(f"{COMPANIES}/{company.id}/detect-board").json()
    assert body["detection"]["ats_type"] == "WORKDAY" and body["detection"]["supported"] is False
    assert body["ats_type"] == "WORKDAY" and body["ats_board_token"] is None
    assert body["careers_url"] == "https://acme.wd1.myworkdayjobs.com/Careers"


def test_detection_endpoints_are_rate_limited_per_user(auth_client, db: Session, web: FakeWeb):
    company = companies_service.get_or_create_company(db, "Acme Robotics")
    db.commit()
    calls = [
        lambda: auth_client.post(f"{COMPANIES}/detect-board", json={"name": "Acme Robotics"}),
        lambda: auth_client.post(f"{COMPANIES}/{company.id}/detect-board"),
        lambda: auth_client.post(COMPANIES, json={"name": "Acme Robotics"}),
    ]
    for i in range(10):
        assert calls[i % 3]().status_code in (200, 201)
    for call in calls:
        limited = call()
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
    # A company added without detection does not touch third-party sites and is not limited.
    assert auth_client.post(COMPANIES, json={"name": "Quiet Co", "auto_detect": False}).status_code == 201


def test_the_detection_limit_is_per_user(client, db: Session, web: FakeWeb):
    tokens = []
    for email in ("one@example.com", "two@example.com"):
        r = client.post("/api/v1/auth/register", json={"email": email, "password": "StrongPass123!", "full_name": "U"})
        tokens.append(r.json()["access_token"])
    for _ in range(10):
        client.post(f"{COMPANIES}/detect-board", json={"name": "Acme"}, headers={"Authorization": f"Bearer {tokens[0]}"})
    assert client.post(f"{COMPANIES}/detect-board", json={"name": "Acme"}, headers={"Authorization": f"Bearer {tokens[0]}"}).status_code == 429
    assert client.post(f"{COMPANIES}/detect-board", json={"name": "Acme"}, headers={"Authorization": f"Bearer {tokens[1]}"}).status_code == 200


# --------------------------------------------------------------------------- seed + quick start


def _no_network(monkeypatch) -> list[str]:
    calls: list[str] = []

    def refuse_send(self, request, *args, **kwargs):  # noqa: ANN001
        calls.append(str(request.url))
        raise AssertionError(f"unexpected HTTP request to {request.url}")

    def refuse_resolve(host: str) -> list[str]:
        calls.append(f"dns:{host}")
        raise AssertionError("unexpected DNS lookup")

    monkeypatch.setattr(httpx.Client, "send", refuse_send)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse_send)
    board_detect.set_resolver(refuse_resolve)
    return calls


def test_seed_inserts_the_known_companies_without_network(db: Session, monkeypatch):
    from app.seed import configure_company_boards

    calls = _no_network(monkeypatch)
    # A board a user configured earlier is kept.
    custom = companies_service.get_or_create_company(db, "Stripe")
    custom.ats_type, custom.ats_board_token = "LEVER", "stripe-custom"
    db.flush()

    configured = configure_company_boards(db)
    db.commit()
    assert calls == []
    assert configured == len(known_boards()) - 1
    rows = {c.normalized_name: c for c in db.scalars(select(Company))}
    assert len(rows) == len(known_boards())
    assert (rows["stripe"].ats_type, rows["stripe"].ats_board_token) == ("LEVER", "stripe-custom")
    ramp = rows["ramp"]
    assert (ramp.ats_type, ramp.ats_board_token, ramp.domain) == ("ASHBY", "ramp", "ramp.com")
    assert ramp.ats_board_url == "https://jobs.ashbyhq.com/ramp" and "unicorn" in ramp.tags
    assert configure_company_boards(db) == 0  # idempotent
    assert calls == []


def test_suggestions_exclude_the_users_list_and_are_ordered_by_tag_then_name(auth_client, db: Session):
    from app.seed import configure_company_boards

    configure_company_boards(db)
    db.commit()
    first = auth_client.get(f"{COMPANIES}/suggestions", params={"limit": 20})
    assert first.status_code == 200, first.text
    body = first.json()
    assert len(body["items"]) == 20
    assert body["board_companies"] == 0 and body["show_quick_start"] is True
    ranks = [(tag_rank(item["tags"]), item["name"].lower()) for item in body["items"]]
    assert ranks == sorted(ranks)
    assert all(item["board_configured"] and item["company_id"] for item in body["items"])

    # One-click add = a P2 preference; three of them hide the panel.
    picked = [item["name"] for item in body["items"][:3]]
    for name in picked:
        assert auth_client.post(f"{COMPANIES}/preferences", json={"company_name": name, "priority": "P2"}).status_code == 200
    after = auth_client.get(f"{COMPANIES}/suggestions").json()
    assert not {item["name"] for item in after["items"]} & set(picked)
    assert after["board_companies"] == 3 and after["show_quick_start"] is False


def test_suggestions_without_seeded_rows_and_avoid_does_not_count(auth_client, db: Session):
    body = auth_client.get(f"{COMPANIES}/suggestions", params={"limit": 5}).json()
    assert len(body["items"]) == 5
    assert all(item["company_id"] is None and item["board_configured"] is False for item in body["items"])
    name = body["items"][0]["name"]
    auth_client.post(f"{COMPANIES}/preferences", json={"company_name": name, "priority": "AVOID"})
    again = auth_client.get(f"{COMPANIES}/suggestions", params={"limit": 5}).json()
    assert name not in {item["name"] for item in again["items"]}
    assert again["board_companies"] == 0
    assert auth_client.get(f"{COMPANIES}/suggestions", params={"limit": 0}).status_code == 422


def test_discovery_reads_at_most_forty_boards_and_the_users_list_first(db: Session, user):
    from app.modules.jobs.service import MAX_BOARDS_PER_RUN, load_board_tokens

    for i in range(MAX_BOARDS_PER_RUN + 5):
        company = companies_service.get_or_create_company(db, f"Board Co {i:02d}")
        company.ats_type, company.ats_board_token = "GREENHOUSE", f"boardco{i:02d}"
    last = companies_service.get_or_create_company(db, "Zzz Last Corp")
    last.ats_type, last.ats_board_token = "LEVER", "zzzlast"
    db.flush()
    companies_service.upsert_preference(db, user.id, "Zzz Last Corp", CompanyPriority.P1)
    companies_service.upsert_preference(db, user.id, "Board Co 00", CompanyPriority.AVOID)
    db.commit()

    tokens = load_board_tokens(db, user.id)
    assert len(tokens) == MAX_BOARDS_PER_RUN
    assert tokens[0].token == "zzzlast"
    assert "boardco00" not in {t.token for t in tokens}
    assert db.scalar(select(func.count(CompanyPreference.id))) == 2


# --------------------------------------------------------------------------- live (opt-in)


@pytest.mark.skipif(os.getenv("JOBPILOT_LIVE_BOARDS") != "1", reason="set JOBPILOT_LIVE_BOARDS=1 to hit the real sites")
def test_live_detects_a_real_greenhouse_company_from_its_website(monkeypatch):
    board_http.set_transport(None)  # undo the conftest network guard for this one test
    board_detect.set_transport(None)
    board_detect.set_resolver(None)
    board_http.clear_cache()
    # Skip the known list so the website itself has to lead to the board.
    monkeypatch.setattr(board_detect, "find_known_board", lambda name, website: None)
    result = detect_board(None, "https://www.cloudflare.com")
    assert result.method in ("GUESS", "SCAN"), result.tried
    assert result.ats_type == "GREENHOUSE" and result.token == "cloudflare"
    assert result.open_jobs and result.open_jobs >= 1
    assert result.requests <= MAX_REQUESTS
