"""ATS optimizer - reading job postings: URL guards, redirects, size cap, page parsing,
vendor URLs through the board APIs, and the company look-up (several roles, never guessed)."""
from __future__ import annotations

import html
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationFailed
from app.models.company import Company
from app.models.enums import JdSource, JobSourceType
from app.modules.adapters.boards import http as board_http
from app.modules.ats import fetch
from app.modules.ats import lookup

try:
    from helpers.ats import BACKEND_JD, TEST_PUBLIC_IP, headers, make_user, no_page_network  # noqa: F401
except ImportError:  # pragma: no cover
    from tests.helpers.ats import BACKEND_JD, TEST_PUBLIC_IP, headers, make_user, no_page_network  # type: ignore[no-redef]  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_page_network")

ATS = "/api/v1/ats"
LONG_TEXT = "Responsibilities: build APIs in Python. Requirements: 3 years of experience with PostgreSQL. " * 12


def _pages(routes: dict[str, httpx.Response | callable], hits: list[str] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.url.scheme}://{request.url.host}{request.url.path}"
        if hits is not None:
            hits.append(key)
            assert "cookie" not in {k.lower() for k in request.headers}  # never send cookies
        route = routes.get(key)
        if route is None:
            return httpx.Response(404, text="not here")
        return route(request) if callable(route) else route

    return httpx.MockTransport(handler)


def _html(body: str, head: str = "") -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=f"<html><head>{head}</head><body>{body}</body></html>")


# --------------------------------------------------------------------------- URL guard


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/jobs/1",
        "http://10.0.0.5/careers",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://localhost:80/job",
        "https://intranet/job",
        "https://jobs.example.local/1",
        "http://192.168.1.10/",
    ],
)
def test_private_and_local_addresses_are_refused(url):
    with pytest.raises(ValidationFailed) as err:
        fetch.check_url(url)
    assert err.value.code == "url_not_allowed"


def test_a_public_name_resolving_inward_is_refused():
    fetch.set_resolver(lambda host: ["10.1.2.3"] if host == "evil.example.com" else [TEST_PUBLIC_IP])
    with pytest.raises(ValidationFailed) as err:
        fetch.check_url("https://evil.example.com/job")
    assert err.value.code == "url_not_allowed"
    assert fetch.check_url("https://good.example.com/job") == "https://good.example.com/job"


@pytest.mark.parametrize(
    "url,code",
    [
        ("ftp://example.com/job", "url_not_allowed"),
        ("file:///etc/passwd", "url_not_allowed"),
        ("https://example.com:8443/job", "url_not_allowed"),
        ("https://user:pass@example.com/job", "url_not_allowed"),
        ("", "invalid_url"),
    ],
)
def test_schemes_ports_and_credentials(url, code):
    with pytest.raises(ValidationFailed) as err:
        fetch.check_url(url)
    assert err.value.code == code


def test_every_redirect_is_checked_again():
    fetch.set_transport(
        _pages({"https://jobs.example.com/opening": httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})})
    )
    with pytest.raises(ValidationFailed) as err:
        fetch.fetch_page("https://jobs.example.com/opening")
    assert err.value.code == "url_not_allowed"


def test_redirects_are_capped():
    routes = {f"https://jobs.example.com/r{i}": httpx.Response(302, headers={"location": f"/r{i + 1}"}) for i in range(6)}
    fetch.set_transport(_pages(routes))
    with pytest.raises(ValidationFailed) as err:
        fetch.fetch_page("https://jobs.example.com/r0")
    assert err.value.code == "url_not_allowed"


def test_a_redirect_within_the_cap_is_followed_without_cookies():
    hits: list[str] = []
    fetch.set_transport(
        _pages(
            {
                "https://jobs.example.com/a": httpx.Response(301, headers={"location": "/b", "set-cookie": "sid=1"}),
                "https://jobs.example.com/b": _html(f"<main><h1>Backend Engineer</h1><p>{LONG_TEXT}</p></main>"),
            },
            hits,
        )
    )
    final, text, content_type = fetch.fetch_page("https://jobs.example.com/a")
    assert final == "https://jobs.example.com/b" and "Backend Engineer" in text and content_type == "text/html"
    assert hits == ["https://jobs.example.com/a", "https://jobs.example.com/b"]


def test_the_body_is_capped():
    fetch.set_transport(_pages({"https://jobs.example.com/huge": httpx.Response(200, headers={"content-type": "text/html"}, content=b"a" * (fetch.MAX_BYTES + 10))}))
    with pytest.raises(ValidationFailed) as err:
        fetch.fetch_page("https://jobs.example.com/huge")
    assert err.value.code == "jd_too_large"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, text="forbidden"),
        httpx.Response(404, text="gone"),
        httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4"),
        _html("<p>Too short.</p>"),
    ],
)
def test_unreadable_pages_ask_for_the_text(response):
    fetch.set_transport(_pages({"https://jobs.example.com/x": response}))
    with pytest.raises(ValidationFailed) as err:
        fetch.fetch_posting("https://jobs.example.com/x")
    assert err.value.code == "jd_unreadable"
    assert "Paste" in err.value.message


# --------------------------------------------------------------------------- page parsing


def test_json_ld_job_posting_is_preferred():
    posting = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "name": "Acme"},
            {
                "@type": "JobPosting",
                "title": "Senior Backend Engineer",
                "description": "<p>" + html.escape(BACKEND_JD).replace("\n", "<br>") + "</p>",
                "hiringOrganization": {"@type": "Organization", "name": "Acme Payments"},
                "jobLocation": {"@type": "Place", "address": {"addressLocality": "Bengaluru", "addressCountry": "IN"}},
                "validThrough": "2026-12-01T00:00:00Z",
            },
        ],
    }
    page = f'<nav>Home Careers</nav><script type="application/ld+json">{json.dumps(posting)}</script><main>Apply now</main>'
    result = fetch.parse_page("https://acme.example.com/jobs/1", f"<html><body>{page}</body></html>", "text/html")
    assert result.confidence == "high" and result.source == JdSource.URL
    assert result.title == "Senior Backend Engineer" and result.company == "Acme Payments"
    assert result.location == "Bengaluru, IN"
    assert result.deadline is not None and result.deadline.year == 2026
    assert "PostgreSQL" in result.text and "Home Careers" not in result.text


def test_main_text_without_chrome_or_scripts():
    page = (
        "<header>Acme Careers Login</header><nav>Jobs Teams</nav>"
        f"<main><h1>Backend Engineer</h1><p>{LONG_TEXT}</p><script>var secret = 1;</script></main>"
        "<footer>Cookie settings</footer><form>Subscribe</form>"
    )
    result = fetch.parse_page("https://acme.example.com/jobs/2", f"<html><head><title>Backend Engineer | Acme</title></head><body>{page}</body></html>", "text/html")
    assert result.confidence == "medium"
    assert result.title == "Backend Engineer"
    for chrome in ("Login", "Cookie settings", "Subscribe", "secret"):
        assert chrome not in result.text


# --------------------------------------------------------------------------- vendors


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://job-boards.greenhouse.io/acme/jobs/4001", (JobSourceType.GREENHOUSE, "acme", "4001")),
        ("https://boards.greenhouse.io/embed/job_app?for=acme&token=4001", (JobSourceType.GREENHOUSE, "acme", "4001")),
        ("https://boards-api.greenhouse.io/v1/boards/acme/jobs/4001", (JobSourceType.GREENHOUSE, "acme", "4001")),
        ("https://jobs.lever.co/zoox/2b7c-11aa", (JobSourceType.LEVER, "zoox", "2b7c-11aa")),
        ("https://jobs.ashbyhq.com/ramp/7f9e-aa01", (JobSourceType.ASHBY, "ramp", "7f9e-aa01")),
        ("https://jobs.smartrecruiters.com/ServiceNow/744000153333219-senior-engineer", (JobSourceType.SMARTRECRUITERS, "ServiceNow", "744000153333219")),
        ("https://job-boards.greenhouse.io/acme", None),
        ("https://careers.acme.example.com/jobs/4001", None),
    ],
)
def test_vendor_posting_urls_are_detected(url, expected):
    assert fetch.board_posting_from_url(url) == expected


def _greenhouse_board(*titles: str) -> dict:
    jobs = []
    for index, title in enumerate(titles, start=1):
        jobs.append(
            {
                "id": 4000 + index,
                "title": title,
                "location": {"name": "Bengaluru"},
                "absolute_url": f"https://job-boards.greenhouse.io/acme/jobs/{4000 + index}",
                "updated_at": "2026-10-01T10:00:00Z",
                "company_name": "Acme",
                "content": html.escape("<p>" + BACKEND_JD.replace("\n", "<br>") + "</p>"),
            }
        )
    return {"jobs": jobs}


def _board_transport(payload: dict, hits: list[str] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if hits is not None:
            hits.append(str(request.url))
        if request.url.host == "boards-api.greenhouse.io" and request.url.path == "/v1/boards/acme/jobs":
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def test_a_greenhouse_posting_is_read_from_the_board_api_not_the_page():
    hits: list[str] = []
    board_http.set_transport(_board_transport(_greenhouse_board("Senior Backend Engineer", "Product Designer"), hits))
    posting = fetch.fetch_posting("https://job-boards.greenhouse.io/acme/jobs/4001")
    assert posting.source == JdSource.BOARD and posting.confidence == "high"
    assert posting.title == "Senior Backend Engineer" and posting.company == "Acme"
    assert "PostgreSQL" in posting.text
    assert all("boards-api.greenhouse.io" in hit for hit in hits)  # the page itself is never fetched


def test_a_closed_posting_asks_for_the_text():
    board_http.set_transport(_board_transport(_greenhouse_board("Product Designer")))
    with pytest.raises(ValidationFailed) as err:
        fetch.fetch_posting("https://job-boards.greenhouse.io/acme/jobs/9999")
    assert err.value.code == "jd_unreadable"


# --------------------------------------------------------------------------- company look-up


def test_lookup_returns_every_matching_role_and_picks_none(db: Session):
    db.add(Company(name="Acme", normalized_name="acme", ats_type="GREENHOUSE", ats_board_token="acme"))
    db.flush()
    board_http.set_transport(
        _board_transport(_greenhouse_board("Senior Backend Engineer", "Backend Engineer, Payments", "Product Designer", "Frontend Engineer"))
    )
    result = lookup.lookup_company(db, None, "Acme Pvt Ltd", "Backend Engineer")  # type: ignore[arg-type]
    assert result.method == "REGISTRY" and result.supported and result.total_open == 4
    assert sorted(r.title for r in result.matching_roles) == ["Backend Engineer, Payments", "Senior Backend Engineer"]
    assert "Choose" in result.message
    assert all(r.vendor == "GREENHOUSE" and r.token == "acme" and r.external_id.startswith("acme:") for r in result.open_roles)


def test_lookup_without_a_readable_board_asks_for_the_jd(db: Session):
    result = lookup.lookup_company(db, None, "Totally Unknown Startup Xyz", "Engineer")  # type: ignore[arg-type]
    assert result.method == "NONE" and not result.open_roles and "Paste" in result.message


# --------------------------------------------------------------------------- endpoints


def test_fetch_endpoint_structures_the_page_and_is_rate_limited(client: TestClient, db: Session):
    user = make_user(db, "fetch@example.com")
    db.commit()
    fetch.set_transport(_pages({"https://jobs.example.com/backend": _html(f"<main>{html.escape(BACKEND_JD).replace(chr(10), '<br>')}</main>")}))
    r = client.post(f"{ATS}/jd/fetch", json={"url": "https://jobs.example.com/backend"}, headers=headers(user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "URL" and "Python" in body["structured"]["required_skills"]
    r = client.post(f"{ATS}/jd/fetch", json={"url": "http://127.0.0.1:8000/api/v1/auth/me"}, headers=headers(user))
    assert r.status_code == 422 and r.json()["error"]["code"] == "url_not_allowed"
    codes = [client.post(f"{ATS}/jd/fetch", json={"url": "https://jobs.example.com/backend"}, headers=headers(user)).status_code for _ in range(10)]
    assert 429 in codes


def test_parse_and_upload_endpoints(client: TestClient, db: Session):
    user = make_user(db, "parse@example.com")
    db.commit()
    r = client.post(f"{ATS}/jd/parse", json={"text": BACKEND_JD, "company": "Acme"}, headers=headers(user))
    assert r.status_code == 200, r.text
    assert r.json()["structured"]["years_min"] == 5.0
    r = client.post(
        f"{ATS}/jd/upload",
        files={"file": ("jd.txt", BACKEND_JD.encode(), "text/plain")},
        data={"company": "Acme"},
        headers=headers(user),
    )
    assert r.status_code == 200 and r.json()["source"] == "UPLOADED"
    r = client.post(f"{ATS}/jd/upload", files={"file": ("jd.exe", b"MZ....", "application/octet-stream")}, headers=headers(user))
    assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_file_type"
    r = client.post(f"{ATS}/jd/parse", json={"text": "too short"}, headers=headers(user))
    assert r.status_code == 422 and r.json()["error"]["code"] == "jd_too_short"
    assert client.post(f"{ATS}/jd/parse", json={"text": BACKEND_JD}).status_code == 401
