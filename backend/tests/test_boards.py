"""Real job discovery from the public ATS job boards (Greenhouse, Lever, Ashby, SmartRecruiters).

Every vendor test replays a real API response recorded on 2026-10-04 and trimmed to three
postings (``tests/fixtures/boards/``) through an ``httpx.MockTransport``; the default
suite never touches the network (see ``_no_job_board_network`` in ``conftest.py``). The
one live test is opt-in: ``JOBPILOT_LIVE_BOARDS=1 pytest -k live_board``.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company, normalize_ats_type
from app.models.enums import (
    ApplicationType,
    AutomationState,
    CompanyPriority,
    EmploymentType,
    JobSourceType,
    PauseReason,
    WorkMode,
)
from app.models.job import Job, JobSource
from app.modules.adapters.base import ApplyContext, BoardToken, SearchQuery
from app.modules.adapters.boards import (
    BOARD_SOURCES,
    AshbyAdapter,
    BoardUrlError,
    GreenhouseAdapter,
    LeverAdapter,
    SmartRecruitersAdapter,
    infer_ats_type,
    parse_board_url,
)
from app.modules.adapters.boards import http as board_http
from app.modules.adapters.boards import smartrecruiters as sr_module
from app.modules.adapters.boards.common import html_to_text
from app.modules.adapters.registry import DISCOVERY_SOURCES, get_adapter, list_adapters
from app.modules.ai.skills import extract_skills
from app.modules.jobs import service as jobs_service

FIXTURES = Path(__file__).parent / "fixtures" / "boards"
COMPANIES = "/api/v1/companies"

GH_API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
LEVER_API = "https://api.lever.co/v0/postings/{token}"
ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/{token}"
SR_API = "https://api.smartrecruiters.com/v1/companies/{token}/postings"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


Route = Callable[[httpx.Request], httpx.Response]


class FakeBoards:
    """A MockTransport keyed by ``scheme://host/path`` (query string ignored) that counts hits."""

    def __init__(self) -> None:
        self.routes: dict[str, Any] = {}
        self.requests: list[httpx.Request] = []

    def add(self, url: str, body: Any = None, *, status: int = 200, raw: bytes | None = None) -> "FakeBoards":
        self.routes[url] = (status, body, raw)
        return self

    def hits(self, url: str) -> int:
        return sum(1 for r in self.requests if f"{r.url.scheme}://{r.url.host}{r.url.path}" == url)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.url.scheme}://{request.url.host}{request.url.path}"
        if key not in self.routes:
            return httpx.Response(404, json={"ok": False, "error": "Document not found"})
        status, body, raw = self.routes[key]
        if callable(body):
            return body(request)
        if raw is not None:
            return httpx.Response(status, content=raw)
        return httpx.Response(status, json=body)


@pytest.fixture
def boards() -> FakeBoards:
    fake = FakeBoards()
    board_http.set_transport(httpx.MockTransport(fake))
    board_http.clear_cache()
    return fake


def _board(token: str, name: str, source: JobSourceType, domain: str | None = None) -> BoardToken:
    return BoardToken(uuid.uuid4(), token, name, domain, source)


def _by_id(jobs, external_id: str):
    return next(job for job in jobs if job.external_id == external_id)


# --------------------------------------------------------------------------- registry


def test_the_four_board_adapters_are_real_discovery_sources():
    infos = {info.source: info for info in list_adapters()}
    for source in (JobSourceType.GREENHOUSE, JobSourceType.LEVER, JobSourceType.ASHBY, JobSourceType.SMARTRECRUITERS):
        info = infos[source]
        assert info.is_mock is False
        assert info.supports_auto_apply is True
        assert info.uses_browser is True
        assert info.requires_account is False
        assert "API" in info.terms_note and "never solved" in info.terms_note
        assert source in DISCOVERY_SOURCES
        assert source in BOARD_SOURCES
    assert isinstance(get_adapter("ASHBY"), AshbyAdapter)
    assert isinstance(get_adapter("SMARTRECRUITERS"), SmartRecruitersAdapter)


def test_board_adapters_return_nothing_without_a_configured_board(boards, caplog):
    caplog.set_level("INFO")
    for adapter in (GreenhouseAdapter(), LeverAdapter(), AshbyAdapter(), SmartRecruitersAdapter()):
        assert adapter.search_jobs(SearchQuery(limit=50)) == []
    assert boards.requests == []
    assert "no company has a Greenhouse board configured" in caplog.text


def test_a_board_of_another_vendor_is_ignored(boards):
    boards.add(GH_API.format(token="stripe"), load("greenhouse_stripe.json"))
    query = SearchQuery(board_tokens=[_board("stripe", "Stripe", JobSourceType.GREENHOUSE)])
    assert LeverAdapter().search_jobs(query) == []
    assert len(GreenhouseAdapter().search_jobs(query)) == 3


# --------------------------------------------------------------------------- Greenhouse


def test_greenhouse_maps_every_field(boards):
    boards.add(GH_API.format(token="stripe"), load("greenhouse_stripe.json"))
    query = SearchQuery(limit=50, board_tokens=[_board("stripe", "Stripe", JobSourceType.GREENHOUSE, "stripe.com")])
    jobs = GreenhouseAdapter().search_jobs(query)
    assert [job.external_id for job in jobs] == ["stripe:8172503", "stripe:7118945", "stripe:8241260"]

    remote = _by_id(jobs, "stripe:8172503")
    assert remote.source == JobSourceType.GREENHOUSE
    assert remote.title == "Abuse Research Engineer"
    assert remote.company_name == "Stripe"  # the configured company, not the vendor's spelling
    assert remote.company_domain == "stripe.com"
    assert remote.location == "Remote from the US"
    assert remote.work_mode == WorkMode.REMOTE
    assert remote.url == "https://stripe.com/jobs/search?gh_jid=8172503"
    assert remote.apply_url == "https://job-boards.greenhouse.io/embed/job_app?for=stripe&token=8172503"
    assert remote.application_type == ApplicationType.ATS_FORM
    # first_published wins over updated_at, converted to UTC
    assert remote.posted_at == datetime(2026, 9, 9, 14, 52, 9, tzinfo=timezone.utc)
    assert remote.salary_min is None and remote.salary_max is None and remote.salary_currency is None
    assert remote.employment_type is None
    # HTML to text: Greenhouse sends entity-escaped HTML; no tag or entity survives
    assert remote.description.startswith("Who we are\n")
    assert "About Stripe" in remote.description
    assert "<" not in remote.description and "&lt;" not in remote.description and "&amp;" not in remote.description
    assert remote.raw["content_html"].startswith("<h2>Who we are</h2>")
    assert remote.raw["board_token"] == "stripe" and remote.raw["job_id"] == 8172503
    assert remote.required_skills == extract_skills(remote.description)

    bangalore = _by_id(jobs, "stripe:7118945")
    assert bangalore.location == "Bengaluru"
    assert bangalore.work_mode is None  # not stated - never guessed

    intern = _by_id(jobs, "stripe:8241260")
    assert intern.employment_type == EmploymentType.INTERNSHIP
    assert intern.required_skills  # a software role: the taxonomy finds languages in the text


def test_greenhouse_sends_a_descriptive_user_agent_and_caches_the_board(boards):
    boards.add(GH_API.format(token="stripe"), load("greenhouse_stripe.json"))
    query = SearchQuery(board_tokens=[_board("stripe", "Stripe", JobSourceType.GREENHOUSE)])
    GreenhouseAdapter().search_jobs(query)
    GreenhouseAdapter().search_jobs(query)
    assert boards.hits(GH_API.format(token="stripe")) == 1  # second run served from the cache
    request = boards.requests[0]
    assert request.headers["user-agent"].startswith("JobPilot/")
    assert "+https://github.com/" in request.headers["user-agent"]
    assert request.url.params["content"] == "true"


def test_the_cache_expires_after_its_ttl(boards, monkeypatch):
    boards.add(GH_API.format(token="stripe"), load("greenhouse_stripe.json"))
    query = SearchQuery(board_tokens=[_board("stripe", "Stripe", JobSourceType.GREENHOUSE)])
    clock = [1000.0]
    monkeypatch.setattr(board_http.time, "monotonic", lambda: clock[0])
    GreenhouseAdapter().search_jobs(query)
    clock[0] += board_http.CACHE_TTL_SECONDS + 1
    GreenhouseAdapter().search_jobs(query)
    assert boards.hits(GH_API.format(token="stripe")) == 2


def test_greenhouse_applies_title_location_and_age_filters_client_side(boards):
    boards.add(GH_API.format(token="stripe"), load("greenhouse_stripe.json"))
    token = [_board("stripe", "Stripe", JobSourceType.GREENHOUSE)]

    by_title = GreenhouseAdapter().search_jobs(SearchQuery(titles=["Research Engineer"], board_tokens=token))
    assert {job.external_id for job in by_title} == {"stripe:8172503"}

    by_location = GreenhouseAdapter().search_jobs(SearchQuery(locations=["Bangalore"], board_tokens=token))
    assert [job.external_id for job in by_location] == ["stripe:7118945"]

    remote_only = GreenhouseAdapter().search_jobs(SearchQuery(locations=["Remote"], board_tokens=token))
    assert [job.external_id for job in remote_only] == ["stripe:8172503"]

    newest = datetime(2026, 9, 30, 15, 38, 9, tzinfo=timezone.utc)  # 8241260's first_published
    hours = int((datetime.now(timezone.utc) - newest).total_seconds() // 3600) + 48
    recent = GreenhouseAdapter().search_jobs(SearchQuery(posted_within_hours=hours, board_tokens=token))
    assert [job.external_id for job in recent] == ["stripe:8241260"]

    limited = GreenhouseAdapter().search_jobs(SearchQuery(limit=2, board_tokens=token))
    assert len(limited) == 2


def test_a_missing_or_broken_board_does_not_drop_the_others(boards, caplog):
    caplog.set_level("WARNING")
    boards.add(GH_API.format(token="stripe"), load("greenhouse_stripe.json"))
    boards.add(GH_API.format(token="gone"), {"status": 404, "error": "Job not found"}, status=404)
    boards.add(GH_API.format(token="weird"), {"unexpected": True})
    boards.add(GH_API.format(token="down"), {"error": "boom"}, status=503)
    query = SearchQuery(
        board_tokens=[
            _board("gone", "Gone Inc", JobSourceType.GREENHOUSE),
            _board("weird", "Weird Co", JobSourceType.GREENHOUSE),
            _board("down", "Down Corp", JobSourceType.GREENHOUSE),
            _board("stripe", "Stripe", JobSourceType.GREENHOUSE),
        ]
    )
    jobs = GreenhouseAdapter().search_jobs(query)
    assert len(jobs) == 3 and {job.company_name for job in jobs} == {"Stripe"}
    assert "Greenhouse board 'gone' failed" in caplog.text
    assert "Greenhouse board 'weird' failed" in caplog.text
    assert "Greenhouse board 'down' failed" in caplog.text


def test_results_are_shared_round_robin_across_companies(boards):
    payload = load("greenhouse_stripe.json")
    boards.add(GH_API.format(token="stripe"), payload)
    boards.add(GH_API.format(token="other"), payload)
    query = SearchQuery(
        limit=4,
        board_tokens=[_board("stripe", "Stripe", JobSourceType.GREENHOUSE), _board("other", "Other", JobSourceType.GREENHOUSE)],
    )
    jobs = GreenhouseAdapter().search_jobs(query)
    assert [job.company_name for job in jobs] == ["Stripe", "Other", "Stripe", "Other"]


def test_plain_company_id_token_tuples_are_accepted(boards):
    boards.add(GH_API.format(token="stripe"), load("greenhouse_stripe.json"))
    jobs = GreenhouseAdapter().search_jobs(SearchQuery(board_tokens=[(uuid.uuid4(), "stripe")]))
    assert len(jobs) == 3
    assert jobs[0].company_name == "stripe"  # no company row given: the token labels it


# --------------------------------------------------------------------------- Lever


def test_lever_maps_every_field_including_salary(boards):
    boards.add(LEVER_API.format(token="zoox"), load("lever_zoox.json"))
    jobs = LeverAdapter().search_jobs(
        SearchQuery(board_tokens=[_board("zoox", "Zoox", JobSourceType.LEVER, "zoox.com")])
    )
    assert len(jobs) == 3

    hybrid = _by_id(jobs, "zoox:f4746da4-8eb8-43e2-b7ce-bf3c7cf9640d")
    assert hybrid.title == "Autonomy System Test Engineer"
    assert hybrid.company_name == "Zoox" and hybrid.company_domain == "zoox.com"
    assert hybrid.location == "Foster City, CA"
    assert hybrid.work_mode == WorkMode.HYBRID
    assert hybrid.employment_type == EmploymentType.FULL_TIME
    assert (hybrid.salary_min, hybrid.salary_max, hybrid.salary_currency) == (144000, 193000, "USD")
    assert hybrid.url == "https://jobs.lever.co/zoox/f4746da4-8eb8-43e2-b7ce-bf3c7cf9640d"
    assert hybrid.apply_url == "https://jobs.lever.co/zoox/f4746da4-8eb8-43e2-b7ce-bf3c7cf9640d/apply"
    assert hybrid.posted_at == datetime.fromtimestamp(1777936261125 / 1000, tz=timezone.utc)
    # intro + titled lists, as text with bullets
    assert hybrid.description.startswith("Autonomous vehicles have some of the largest")
    assert "In this role, you will:" in hybrid.description
    assert "\n- " in hybrid.description
    assert "<" not in hybrid.description
    assert "<div>" in hybrid.raw["description_html"]
    assert hybrid.required_skills == extract_skills(hybrid.description)

    onsite = _by_id(jobs, "zoox:7980e9a3-99f3-4988-ae6d-355c9199d8fb")
    assert onsite.work_mode == WorkMode.ONSITE
    assert (onsite.salary_min, onsite.salary_max) == (170000, 204000)

    contract = _by_id(jobs, "zoox:5e03b357-0cc1-4194-9488-14f85044f4f9")
    assert contract.employment_type == EmploymentType.CONTRACT
    assert contract.salary_min is None and contract.salary_currency is None


def test_lever_remote_flag_and_non_yearly_salary(boards):
    rows = load("lever_zoox.json")[:1]
    rows[0]["workplaceType"] = "remote"
    rows[0]["salaryRange"] = {"currency": "USD", "interval": "per-hour-wage", "min": 40, "max": 60}
    boards.add(LEVER_API.format(token="zoox"), rows)
    (job,) = LeverAdapter().search_jobs(SearchQuery(board_tokens=[_board("zoox", "Zoox", JobSourceType.LEVER)]))
    assert job.work_mode == WorkMode.REMOTE
    assert job.salary_min is None  # hourly pay is not comparable with yearly salaries


# --------------------------------------------------------------------------- Ashby


def test_ashby_maps_every_field_including_compensation(boards):
    payload = load("ashby_ramp.json")
    unlisted = dict(payload["jobs"][0], id="unlisted-1", isListed=False)
    payload["jobs"].append(unlisted)
    boards.add(ASHBY_API.format(token="ramp"), payload)
    jobs = AshbyAdapter().search_jobs(SearchQuery(board_tokens=[_board("ramp", "Ramp", JobSourceType.ASHBY, "ramp.com")]))
    assert len(jobs) == 3  # the unlisted posting is skipped

    remote = _by_id(jobs, "ramp:d1183b00-6590-4fe4-a585-28d84e578fe3")
    assert remote.title == "Software Engineer, Security, Stablecoin"
    assert remote.company_name == "Ramp" and remote.company_domain == "ramp.com"
    assert remote.location == "New York, NY (HQ)"
    assert remote.work_mode == WorkMode.REMOTE  # vendor flag beats the HQ location text
    assert remote.employment_type == EmploymentType.FULL_TIME
    assert (remote.salary_min, remote.salary_max, remote.salary_currency) == (189000, 330000, "USD")
    assert remote.posted_at == datetime(2026, 5, 13, 20, 28, 9, 574000, tzinfo=timezone.utc)
    assert remote.url == "https://jobs.ashbyhq.com/ramp/d1183b00-6590-4fe4-a585-28d84e578fe3"
    assert remote.apply_url.endswith("/d1183b00-6590-4fe4-a585-28d84e578fe3/application")
    assert remote.description.startswith("About Ramp\n")
    assert "<" not in remote.description
    assert remote.raw["description_html"].startswith("<h1>")

    hybrid = _by_id(jobs, "ramp:34413f8d-26bf-4bbc-8ade-eb309a0e2245")
    assert hybrid.title == "Security Engineer, Cloud"  # vendor whitespace trimmed
    assert hybrid.work_mode == WorkMode.HYBRID
    assert (hybrid.salary_min, hybrid.salary_max) == (211400, 290600)

    intern = _by_id(jobs, "ramp:b39ceb08-a0a7-4f8b-a760-2fb88e209956")
    assert intern.employment_type == EmploymentType.INTERNSHIP
    assert intern.salary_min is None  # a monthly stipend is not a yearly salary


# --------------------------------------------------------------------------- SmartRecruiters


def test_smartrecruiters_maps_the_list_and_fetches_details_for_matches_only(boards):
    boards.add(SR_API.format(token="ServiceNow"), load("smartrecruiters_servicenow.json"))
    boards.add(f"{SR_API.format(token='ServiceNow')}/744000153333219", load("smartrecruiters_servicenow_744000153333219.json"))
    adapter = SmartRecruitersAdapter()
    query = SearchQuery(titles=["Software Engineer"], board_tokens=[_board("ServiceNow", "ServiceNow", JobSourceType.SMARTRECRUITERS, "servicenow.com")])
    jobs = adapter.search_jobs(query)
    assert [job.external_id for job in jobs] == ["ServiceNow:744000153333219", "ServiceNow:744000153266480"]
    # the "Director, CRM Sales" posting failed the title filter: its details were never fetched
    assert boards.hits(f"{SR_API.format(token='ServiceNow')}/744000153267939") == 0

    enriched = jobs[0]
    assert enriched.title == "Sr Software Engineer"
    assert enriched.company_name == "ServiceNow" and enriched.company_domain == "servicenow.com"
    assert enriched.location == "Santa Clara, CALIFORNIA, United States"
    assert enriched.work_mode is None
    assert enriched.employment_type == EmploymentType.FULL_TIME
    assert enriched.posted_at == datetime(2026, 10, 3, 16, 2, 30, 623000, tzinfo=timezone.utc)
    assert enriched.url == "https://jobs.smartrecruiters.com/ServiceNow/744000153333219-sr-software-engineer"
    assert enriched.apply_url == "https://jobs.smartrecruiters.com/ServiceNow/744000153333219-sr-software-engineer?oga=true"
    assert enriched.description.startswith("Company Description\n")
    assert "Qualifications" in enriched.description and "<" not in enriched.description
    assert enriched.required_skills == extract_skills(enriched.description)
    assert "<p>" in enriched.raw["description_html"]
    assert enriched.salary_min is None

    # the detail call 404s for this one: the summary is kept as it was
    summary_only = jobs[1]
    assert summary_only.work_mode == WorkMode.REMOTE
    assert summary_only.description == ""
    assert summary_only.url == "https://jobs.smartrecruiters.com/ServiceNow/744000153266480"


def test_smartrecruiters_hybrid_flag_and_pagination(boards, monkeypatch):
    monkeypatch.setattr(sr_module, "PAGE_SIZE", 2)
    content = load("smartrecruiters_servicenow.json")["content"]

    def page(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        assert request.url.params["limit"] == "2"
        return httpx.Response(200, json={"offset": offset, "limit": 2, "totalFound": 3, "content": content[offset : offset + 2]})

    boards.add(SR_API.format(token="ServiceNow"), page)
    jobs = SmartRecruitersAdapter().search_jobs(
        SearchQuery(board_tokens=[_board("ServiceNow", "ServiceNow", JobSourceType.SMARTRECRUITERS)])
    )
    assert len(jobs) == 3
    assert boards.hits(SR_API.format(token="ServiceNow")) == 2
    assert _by_id(jobs, "ServiceNow:744000153267939").work_mode == WorkMode.HYBRID


def test_smartrecruiters_counts_a_board_from_total_found(boards):
    boards.add(SR_API.format(token="ServiceNow"), load("smartrecruiters_servicenow.json"))
    boards.add(SR_API.format(token="Nobody"), {"offset": 0, "limit": 100, "totalFound": 0, "content": []})
    assert SmartRecruitersAdapter().count_board_jobs("ServiceNow") == 3
    assert SmartRecruitersAdapter().count_board_jobs("Nobody") == 0


# --------------------------------------------------------------------------- helpers


def test_html_to_text_keeps_structure_and_drops_markup():
    markup = (
        "<h2>About us</h2><p>We build <b>fast</b>&nbsp;tools &amp; more.</p>"
        "<ul><li>Python</li><li><p>React</p></li><li></li></ul>"
        "<script>alert(1)</script><style>p{}</style><p>Bye<br>now</p>"
    )
    # headings and paragraphs get a blank line, list items become adjacent bullets (an empty
    # one vanishes), <br> is a line break, and script/style content is dropped
    assert html_to_text(markup) == "About us\n\nWe build fast tools & more.\n\n- Python\n- React\n\nBye\nnow"
    assert html_to_text("&lt;p&gt;Escaped &amp;amp; twice&lt;/p&gt;", unescape_first=True) == "Escaped & twice"
    assert html_to_text(None) == "" and html_to_text("") == ""


@pytest.mark.parametrize(
    ("ats_type", "value", "token"),
    [
        ("GREENHOUSE", "https://boards.greenhouse.io/stripe", "stripe"),
        ("GREENHOUSE", "https://job-boards.greenhouse.io/gitlab/jobs/8860302002", "gitlab"),
        ("GREENHOUSE", "https://job-boards.eu.greenhouse.io/acme", "acme"),
        ("GREENHOUSE", "https://boards.greenhouse.io/embed/job_board?for=cloudflare", "cloudflare"),
        ("GREENHOUSE", "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true", "stripe"),
        ("GREENHOUSE", "boards.greenhouse.io/stripe", "stripe"),
        ("GREENHOUSE", "stripe", "stripe"),
        ("LEVER", "https://jobs.lever.co/spotify", "spotify"),
        ("LEVER", "https://jobs.lever.co/spotify/2193db3f-77c5-43b8-b030-8f92c9882bf1/apply", "spotify"),
        ("LEVER", "https://api.lever.co/v0/postings/palantir?mode=json", "palantir"),
        ("LEVER", "palantir", "palantir"),
        ("ASHBY", "https://jobs.ashbyhq.com/ramp", "ramp"),
        ("ASHBY", "https://jobs.ashbyhq.com/notion/34413f8d-26bf-4bbc-8ade-eb309a0e2245/application", "notion"),
        ("ASHBY", "https://api.ashbyhq.com/posting-api/job-board/ramp?includeCompensation=true", "ramp"),
        ("ASHBY", "ramp", "ramp"),
        ("SMARTRECRUITERS", "https://jobs.smartrecruiters.com/BoschGroup", "BoschGroup"),
        ("SMARTRECRUITERS", "https://jobs.smartrecruiters.com/ServiceNow/744000153333219-sr-software-engineer", "ServiceNow"),
        ("SMARTRECRUITERS", "https://careers.smartrecruiters.com/Ubisoft2", "Ubisoft2"),
        ("SMARTRECRUITERS", "https://jobs.smartrecruiters.com/oneclick-ui/company/ServiceNow/publication/b0d8", "ServiceNow"),
        ("SMARTRECRUITERS", "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings", "BoschGroup"),
        ("SMARTRECRUITERS", "BoschGroup", "BoschGroup"),
    ],
)
def test_parse_board_url(ats_type, value, token):
    assert parse_board_url(ats_type, value) == token


@pytest.mark.parametrize(
    ("ats_type", "value"),
    [
        ("GREENHOUSE", "https://jobs.lever.co/spotify"),  # another vendor's URL
        ("LEVER", "https://evil.example.com/lever.co/spotify"),  # vendor name in the path only
        ("ASHBY", "https://jobs.ashbyhq.com/"),  # no token
        ("GREENHOUSE", "https://boards.greenhouse.io/embed/job_board"),  # embed without ?for=
        ("SMARTRECRUITERS", "not a token!"),
        ("GREENHOUSE", ""),
        ("GREENHOUSE", "javascript:alert(1)"),
        ("WORKDAY", "https://acme.wd1.myworkdayjobs.com/careers"),  # no public board API
    ],
)
def test_parse_board_url_rejects_what_it_cannot_use(ats_type, value):
    with pytest.raises(BoardUrlError):
        parse_board_url(ats_type, value)


def test_infer_ats_type_from_the_host():
    assert infer_ats_type("https://boards.greenhouse.io/stripe") == JobSourceType.GREENHOUSE
    assert infer_ats_type("jobs.lever.co/spotify") == JobSourceType.LEVER
    assert infer_ats_type("https://jobs.ashbyhq.com/ramp") == JobSourceType.ASHBY
    assert infer_ats_type("https://jobs.smartrecruiters.com/BoschGroup") == JobSourceType.SMARTRECRUITERS
    assert infer_ats_type("stripe") is None
    assert infer_ats_type("https://example.com/careers") is None


def test_ats_type_is_normalised_to_the_job_source_names(db: Session):
    assert normalize_ats_type(" greenhouse ") == "GREENHOUSE"
    assert normalize_ats_type("Smart Recruiters") == "SMARTRECRUITERS"
    assert normalize_ats_type("demo-ats") == "DEMO_ATS"
    assert normalize_ats_type("") is None
    company = Company(name="Acme", normalized_name="acme", ats_type="lever")
    assert company.ats_type == "LEVER"


# --------------------------------------------------------------------------- jobs service


@pytest.fixture
def user(db: Session):
    from app.modules.auth.service import create_user

    created = create_user(db, "boards@example.com", "StrongPass123", "Board Tester")
    db.commit()
    return created


def _company_with_board(db: Session, name: str, ats_type: JobSourceType, token: str, *, domain: str | None = None) -> Company:
    from app.modules.companies.service import get_or_create_company

    company = get_or_create_company(db, name, domain=domain)
    company.ats_type = ats_type.value
    company.ats_board_token = token
    company.ats_board_url = f"https://example.invalid/{token}"
    db.flush()
    return company


def test_board_sources_are_searched_only_when_a_company_is_configured(db: Session, user):
    resolved = jobs_service.resolve_discovery_sources(db, user.id, None)
    assert not set(BOARD_SOURCES) & set(resolved)
    requested = jobs_service.resolve_discovery_sources(db, user.id, [JobSourceType.GREENHOUSE, JobSourceType.LINKEDIN])
    assert requested == [JobSourceType.LINKEDIN]

    _company_with_board(db, "Stripe", JobSourceType.GREENHOUSE, "stripe")
    resolved = jobs_service.resolve_discovery_sources(db, user.id, None)
    assert JobSourceType.GREENHOUSE in resolved
    assert not {JobSourceType.LEVER, JobSourceType.ASHBY, JobSourceType.SMARTRECRUITERS} & set(resolved)
    assert JobSourceType.DEMO_ATS in resolved

    requested = jobs_service.resolve_discovery_sources(db, user.id, [JobSourceType.GREENHOUSE, JobSourceType.LEVER])
    assert requested == [JobSourceType.GREENHOUSE]


def test_board_tokens_are_loaded_once_and_skip_avoided_companies(db: Session, user):
    from app.modules.companies.service import upsert_preference

    stripe = _company_with_board(db, "Stripe", JobSourceType.GREENHOUSE, "stripe", domain="stripe.com")
    _company_with_board(db, "Ramp", JobSourceType.ASHBY, "ramp")
    wipro = _company_with_board(db, "Wipro", JobSourceType.LEVER, "wipro")
    upsert_preference(db, user.id, "Wipro", CompanyPriority.AVOID, company=wipro)
    no_token = _company_with_board(db, "Half Configured", JobSourceType.LEVER, "x")
    no_token.ats_board_token = None
    db.flush()

    tokens = jobs_service.load_board_tokens(db, user.id)
    assert [(t.token, t.source) for t in tokens] == [("ramp", JobSourceType.ASHBY), ("stripe", JobSourceType.GREENHOUSE)]
    stripe_token = tokens[1]
    assert stripe_token.company_id == stripe.id
    assert stripe_token.company_name == "Stripe" and stripe_token.company_domain == "stripe.com"

    preference = jobs_service.get_job_preference(db, user.id)
    query = jobs_service.build_search_query(preference, db=db)
    assert query.board_tokens == tokens
    assert jobs_service.build_search_query(preference).board_tokens == []  # no db, no boards
    assert jobs_service.resolve_discovery_sources(db, user.id, [JobSourceType.LEVER], board_tokens=tokens) == []


def test_discover_ingests_real_board_postings_for_the_configured_company(auth_client, db: Session, boards):
    from app.models.profile import JobPreference

    boards.add(GH_API.format(token="stripe"), load("greenhouse_stripe.json"))
    stripe = _company_with_board(db, "Stripe", JobSourceType.GREENHOUSE, "stripe", domain="stripe.com")
    # an open search: the fixture's postings are weeks old and spread over three locations
    for preference in db.scalars(select(JobPreference)):
        preference.desired_titles = []
        preference.preferred_locations = []
        preference.preferred_technologies = []
        preference.work_modes = []
        preference.only_posted_within_hours = None
    db.commit()

    response = auth_client.post("/api/v1/jobs/discover", json={"sources": ["GREENHOUSE"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["jobs_found"] == 3 and body["jobs_new"] == 3
    assert [row["source"] for row in body["sources"]] == ["GREENHOUSE"]

    db.expire_all()
    jobs = list(db.scalars(select(Job).where(Job.company_id == stripe.id)))
    assert len(jobs) == 3
    source_rows = list(db.scalars(select(JobSource).where(JobSource.source == JobSourceType.GREENHOUSE)))
    assert {row.external_id for row in source_rows} == {"stripe:8172503", "stripe:7118945", "stripe:8241260"}
    assert all(row.apply_url.startswith("https://job-boards.greenhouse.io/embed/job_app") for row in source_rows)

    listed = auth_client.get("/api/v1/jobs", params={"source": "GREENHOUSE"}).json()
    assert listed["total"] == 3
    assert {card["company"]["name"] for card in listed["items"]} == {"Stripe"}


def test_requesting_only_an_unconfigured_board_searches_nothing(auth_client, boards):
    response = auth_client.post("/api/v1/jobs/discover", json={"sources": ["LEVER"]})
    assert response.status_code == 200, response.text
    body = response.json()
    # not "fall back to every source": no mock catalogue, no demo ATS, no request to Lever
    assert body["jobs_found"] == 0 and body["sources"] == []
    assert boards.requests == []


def test_jobs_sources_lists_the_board_adapters_as_real(auth_client):
    sources = {row["source"]: row for row in auth_client.get("/api/v1/jobs/sources").json()}
    for name in ("GREENHOUSE", "LEVER", "ASHBY", "SMARTRECRUITERS"):
        assert sources[name]["is_mock"] is False
        assert sources[name]["supports_auto_apply"] is True


# --------------------------------------------------------------------------- companies API


def _api_company(db: Session, name: str = "Stripe") -> Company:
    from app.modules.companies.service import get_or_create_company

    company = get_or_create_company(db, name, domain="stripe.com")
    db.commit()
    return company


def test_put_board_verifies_and_saves_it(auth_client, db: Session, boards):
    boards.add(GH_API.format(token="stripe"), load("greenhouse_stripe.json"))
    company = _api_company(db)

    response = auth_client.put(
        f"{COMPANIES}/{company.id}/board",
        json={"ats_type": "GREENHOUSE", "board_url": "https://boards.greenhouse.io/stripe"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["board_job_count"] == 3
    assert body["company"]["ats_type"] == "GREENHOUSE"
    assert body["company"]["ats_board_token"] == "stripe"
    assert body["company"]["ats_board_url"] == "https://boards.greenhouse.io/stripe"

    db.expire_all()
    stored = db.get(Company, company.id)
    assert (stored.ats_type, stored.ats_board_token) == ("GREENHOUSE", "stripe")
    assert auth_client.get(f"{COMPANIES}/{company.id}").json()["ats_board_token"] == "stripe"

    # a bare token is accepted and shown as the vendor's public board page
    boards.add(LEVER_API.format(token="zoox"), load("lever_zoox.json"))
    response = auth_client.put(f"{COMPANIES}/{company.id}/board", json={"ats_type": "LEVER", "board_url": "zoox"})
    assert response.status_code == 200, response.text
    assert response.json()["company"]["ats_board_url"] == "https://jobs.lever.co/zoox"

    cleared = auth_client.delete(f"{COMPANIES}/{company.id}/board")
    assert cleared.status_code == 200
    assert cleared.json()["ats_board_token"] is None


def test_put_board_rejects_a_404_board(auth_client, db: Session, boards):
    company = _api_company(db)
    response = auth_client.put(
        f"{COMPANIES}/{company.id}/board", json={"ats_type": "LEVER", "board_url": "https://jobs.lever.co/netflix"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "board_not_found"
    assert boards.hits(LEVER_API.format(token="netflix")) == 1
    db.expire_all()
    assert db.get(Company, company.id).ats_board_token is None


@pytest.mark.parametrize(
    "body",
    [{"jobs": "nope"}, {"unexpected": True}, {"jobs": [], "meta": {"total": 0}}],
    ids=["jobs-not-a-list", "foreign-shape", "empty-board"],
)
def test_put_board_rejects_a_malformed_or_empty_payload(auth_client, db: Session, boards, body):
    boards.add(GH_API.format(token="stripe"), body)
    company = _api_company(db)
    response = auth_client.put(f"{COMPANIES}/{company.id}/board", json={"ats_type": "GREENHOUSE", "board_url": "stripe"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "board_not_found"


def test_put_board_rejects_html_instead_of_json(auth_client, db: Session, boards):
    boards.add(GH_API.format(token="stripe"), raw=b"<html><body>Not an API</body></html>")
    company = _api_company(db)
    response = auth_client.put(f"{COMPANIES}/{company.id}/board", json={"ats_type": "GREENHOUSE", "board_url": "stripe"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "board_not_found"


def test_put_board_validates_the_url_and_the_vendor(auth_client, db: Session, boards):
    company = _api_company(db)
    wrong_vendor = auth_client.put(
        f"{COMPANIES}/{company.id}/board", json={"ats_type": "GREENHOUSE", "board_url": "https://jobs.lever.co/spotify"}
    )
    assert wrong_vendor.status_code == 422
    assert wrong_vendor.json()["error"]["code"] == "invalid_board_url"
    unsupported = auth_client.put(f"{COMPANIES}/{company.id}/board", json={"ats_type": "WORKDAY", "board_url": "acme"})
    assert unsupported.status_code == 422
    assert boards.requests == []  # nothing invalid ever reaches the network
    missing = auth_client.put(f"{COMPANIES}/{uuid.uuid4()}/board", json={"ats_type": "GREENHOUSE", "board_url": "stripe"})
    assert missing.status_code == 404


def test_put_board_reports_an_unreachable_vendor(auth_client, db: Session):
    company = _api_company(db)  # the conftest transport refuses every connection
    response = auth_client.put(f"{COMPANIES}/{company.id}/board", json={"ats_type": "ASHBY", "board_url": "ramp"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "board_unreachable"


def test_post_companies_creates_a_company_with_an_optional_board(auth_client, db: Session, boards):
    created = auth_client.post(f"{COMPANIES}", json={"name": "Acme Robotics", "website": "https://acme.example"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Acme Robotics" and body["website"] == "https://acme.example"
    assert body["ats_board_token"] is None

    again = auth_client.post(f"{COMPANIES}", json={"name": "Acme Robotics Inc"})
    assert again.status_code == 201 and again.json()["id"] == body["id"]  # same normalised name

    boards.add(ASHBY_API.format(token="ramp"), load("ashby_ramp.json"))
    with_board = auth_client.post(f"{COMPANIES}", json={"name": "Ramp", "board_url": "https://jobs.ashbyhq.com/ramp"})
    assert with_board.status_code == 201, with_board.text
    assert with_board.json()["ats_type"] == "ASHBY" and with_board.json()["ats_board_token"] == "ramp"

    no_vendor = auth_client.post(f"{COMPANIES}", json={"name": "Mystery", "board_url": "mystery"})
    assert no_vendor.status_code == 422
    assert no_vendor.json()["error"]["code"] == "invalid_board_url"
    bad_board = auth_client.post(f"{COMPANIES}", json={"name": "Ghost", "board_url": "https://jobs.lever.co/ghost"})
    assert bad_board.status_code == 422
    db.expire_all()
    assert db.scalars(select(Company).where(Company.normalized_name.in_(["mystery", "ghost"]))).first() is None


# --------------------------------------------------------------------------- the apply side


class _Page:
    """The Playwright ``Page`` calls the hosted-form flow makes, with no form ever appearing."""

    def __init__(self, url: str = "https://jobs.smartrecruiters.com/oneclick-ui/x", *, form: bool = False) -> None:
        self.url = url
        self.form = form
        self.selectors: list[str] = []

    def goto(self, url, **kwargs):
        self.url = url

    def wait_for_selector(self, selector, **kwargs):
        self.selectors.append(selector)
        if not self.form:
            raise TimeoutError(f"waiting for {selector}")

    def query_selector(self, selector):
        return object() if selector == "#btn-submit" else None


def _ctx(page, apply_url="https://jobs.lever.co/zoox/abc/apply"):
    job = SimpleNamespace(id="job-1", apply_url=apply_url, title="Engineer")
    return ApplyContext(application=SimpleNamespace(id="app-1", form_snapshot={}), job=job, page=page)


def _detected(fields, blockers=()):
    from app.modules.browser.schemas import DetectedForm

    return DetectedForm(url="https://jobs.lever.co/zoox/abc/apply", fields=list(fields), submit_selector="#hcaptchaSubmitBtn", blockers=list(blockers))


def _field(label, selector):
    from app.models.enums import FieldType
    from app.modules.browser.schemas import DetectedField

    return DetectedField(selector=selector, label=label, field_type=FieldType.TEXT, required=True)


def test_a_captcha_on_a_board_form_pauses_for_the_user_and_keeps_the_questions(monkeypatch):
    from app.modules.browser import detector
    from app.modules.browser.schemas import Blocker

    captcha = Blocker(kind=PauseReason.CAPTCHA, selector=".h-captcha", message="CAPTCHA challenge detected (.h-captcha)")
    monkeypatch.setattr(
        detector, "detect_form", lambda page: _detected([_field("Email", "#email"), _field("Full name", "#name")], [captcha])
    )

    def _never_fill(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("a CAPTCHA-blocked form must not be filled")

    from app.modules.browser import autofill

    monkeypatch.setattr(autofill, "fill_form", _never_fill)
    for adapter in (GreenhouseAdapter(), LeverAdapter(), AshbyAdapter(), SmartRecruitersAdapter()):
        result = adapter.fill_application(_ctx(_Page(form=True)))
        assert result.state == AutomationState.REQUIRES_USER
        assert result.pause_reason == PauseReason.CAPTCHA
        assert result.form_snapshot["blockers"][0]["selector"] == ".h-captcha"
        assert [f["mapped_to"] for f in result.form_snapshot["fields"]] == ["email", "full_name"]


def test_a_page_behind_bot_protection_is_handed_to_the_detector(monkeypatch):
    from app.modules.browser import detector
    from app.modules.browser.schemas import Blocker

    adapter = SmartRecruitersAdapter()
    page = _Page()
    opened = adapter.start_application(_ctx(page, "https://jobs.smartrecruiters.com/ServiceNow/1?oga=true"))
    assert opened.state == AutomationState.SUCCESS
    assert page.selectors == [adapter.form_ready_selector]

    wall = Blocker(kind=PauseReason.CAPTCHA, selector='iframe[src*="captcha"]', message="CAPTCHA challenge detected")
    monkeypatch.setattr(detector, "detect_form", lambda p: _detected([], [wall]))
    paused = adapter.fill_application(_ctx(page))
    assert (paused.state, paused.pause_reason) == (AutomationState.REQUIRES_USER, PauseReason.CAPTCHA)

    monkeypatch.setattr(detector, "detect_form", lambda p: _detected([]))
    empty = adapter.fill_application(_ctx(page))
    assert empty.state == AutomationState.FAILED
    assert "No application form" in empty.message


def test_board_forms_wait_for_late_widgets_before_detection():
    """Greenhouse injects its invisible reCAPTCHA after the form renders; detecting too early misses it."""

    class _SlowPage(_Page):
        def __init__(self) -> None:
            super().__init__(url="https://job-boards.greenhouse.io/embed/job_app?for=x&token=1", form=True)
            self.load_states: list[tuple[str, int]] = []

        def wait_for_load_state(self, state, timeout=None):
            self.load_states.append((state, timeout))
            raise TimeoutError("analytics keep the network busy")  # bounded and never fatal

    page = _SlowPage()
    result = GreenhouseAdapter().start_application(_ctx(page, page.url))
    assert result.state == AutomationState.SUCCESS
    assert page.load_states == [("networkidle", GreenhouseAdapter.settle_timeout_ms)]


def test_a_page_that_never_loaded_still_fails_to_open():
    page = _Page(url="about:blank")

    def _boom(url, **kwargs):
        raise RuntimeError("net::ERR_NAME_NOT_RESOLVED")

    page.goto = _boom
    result = GreenhouseAdapter().start_application(_ctx(page))
    assert result.state == AutomationState.FAILED


def test_board_adapters_click_the_vendor_submit_button_not_the_captcha_trigger():
    ctx = _ctx(_Page(form=True))
    ctx.application = SimpleNamespace(id="app-1", form_snapshot={"submit_selector": "#hcaptchaSubmitBtn"})
    assert LeverAdapter()._submit_selector(ctx) == "#btn-submit"
    assert AshbyAdapter()._submit_selector(_ctx(SimpleNamespace(url="x"))) == AshbyAdapter.submit_selectors[0]


def test_ashby_waits_for_its_single_page_form_not_a_form_element():
    page = _Page(url="https://jobs.ashbyhq.com/ramp/x/application", form=True)
    result = AshbyAdapter().start_application(_ctx(page, "https://jobs.ashbyhq.com/ramp/x/application"))
    assert result.state == AutomationState.SUCCESS
    assert "ashby-application-form-submit-button" in page.selectors[0]


def test_the_board_adapters_never_import_playwright_at_module_level():
    import importlib

    for module in ("__init__", "common", "greenhouse", "lever", "ashby", "smartrecruiters", "http", "urls"):
        name = "app.modules.adapters.boards" + ("" if module == "__init__" else f".{module}")
        source = Path(importlib.import_module(name).__file__).read_text(encoding="utf-8")
        assert "import playwright" not in source and "from playwright" not in source, name


# --------------------------------------------------------------------------- live (opt-in)


@pytest.mark.skipif(os.getenv("JOBPILOT_LIVE_BOARDS") != "1", reason="set JOBPILOT_LIVE_BOARDS=1 to hit the real Greenhouse API")
def test_live_board_greenhouse_returns_real_jobs():
    board_http.set_transport(None)  # undo the conftest network guard for this one test
    board_http.clear_cache()
    jobs = GreenhouseAdapter().search_jobs(
        SearchQuery(limit=500, board_tokens=[_board("gitlab", "GitLab", JobSourceType.GREENHOUSE, "gitlab.com")])
    )
    assert len(jobs) >= 1
    job = jobs[0]
    assert job.source == JobSourceType.GREENHOUSE and job.company_name == "GitLab"
    assert job.title and job.description and job.external_id.startswith("gitlab:")
    assert job.apply_url.startswith("https://job-boards.greenhouse.io/embed/job_app?for=gitlab&token=")
