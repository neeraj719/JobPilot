"""Tests for the job source adapters (``docs/CONTRACTS.md`` §8)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.enums import (
    ApplicationType,
    AutomationState,
    JobSourceType,
    PauseReason,
    WorkMode,
)
from app.modules.adapters.base import (
    ApplyContext,
    DiscoveredJob,
    SearchQuery,
    detect_application_type,
)
from app.modules.adapters.demo_ats import DemoAtsAdapter
from app.modules.adapters.greenhouse import GreenhouseAdapter
from app.modules.adapters.lever import LeverAdapter
from app.modules.adapters.mock.base_mock import CROSS_POST_SOURCES, SHARED_POSTINGS, build_catalogue, stable_int
from app.modules.adapters.registry import ADAPTERS, MOCK_SOURCES, get_adapter, get_enabled_adapters, list_adapters

ALL_QUERY = SearchQuery(limit=200)


# --------------------------------------------------------------------------- registry


def test_registry_lists_every_expected_source():
    sources = {info.source for info in list_adapters()}
    expected = {
        JobSourceType.NAUKRI,
        JobSourceType.LINKEDIN,
        JobSourceType.INDEED,
        JobSourceType.HIRIST,
        JobSourceType.WELLFOUND,
        JobSourceType.INTERNSHALA,
        JobSourceType.GLASSDOOR,
        JobSourceType.FOUNDIT,
        JobSourceType.COMPANY_CAREERS,
        JobSourceType.DEMO_ATS,
        JobSourceType.GREENHOUSE,
        JobSourceType.LEVER,
    }
    assert expected <= sources


def test_every_adapter_declares_a_terms_note_and_is_cached():
    for info in list_adapters():
        assert info.terms_note and len(info.terms_note) > 40, info.source
        assert info.display_name
    assert get_adapter(JobSourceType.LINKEDIN) is get_adapter("LINKEDIN")


def test_get_adapter_rejects_unknown_source():
    from app.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        get_adapter("MYSPACE_JOBS")


def test_get_enabled_adapters_defaults_and_filters():
    default = {a.source for a in get_enabled_adapters(None)}
    assert JobSourceType.DEMO_ATS in default
    assert set(MOCK_SOURCES) <= default
    # the public job board adapters discover real jobs (for the configured companies)
    assert {JobSourceType.GREENHOUSE, JobSourceType.LEVER, JobSourceType.ASHBY, JobSourceType.SMARTRECRUITERS} <= default

    picked = get_enabled_adapters([JobSourceType.LINKEDIN, "NAUKRI", "NOT_A_SOURCE", JobSourceType.LINKEDIN])
    assert [a.source for a in picked] == [JobSourceType.LINKEDIN, JobSourceType.NAUKRI]


# --------------------------------------------------------------------------- catalogues


@pytest.mark.parametrize("source", list(MOCK_SOURCES))
def test_mock_catalogue_size_and_shape(source: JobSourceType):
    jobs = get_adapter(source).search_jobs(ALL_QUERY)
    assert 18 <= len(jobs) <= 25, f"{source} returned {len(jobs)} jobs"
    external_ids = [j.external_id for j in jobs]
    assert len(set(external_ids)) == len(external_ids)
    for job in jobs:
        assert job.source == source
        assert job.title and job.company_name and job.url
        assert job.salary_currency == "INR"
        assert 300000 <= (job.salary_min or 0) <= 4500000
        assert (job.salary_max or 0) >= (job.salary_min or 0)
        assert job.description.count("\n") >= 5, "descriptions must be multi-paragraph"
        assert job.required_skills and job.preferred_skills
        assert job.posted_at is not None
        assert job.apply_url


def test_mock_catalogue_is_deterministic():
    first = get_adapter(JobSourceType.NAUKRI).search_jobs(ALL_QUERY)
    second = get_adapter(JobSourceType.NAUKRI).search_jobs(ALL_QUERY)
    assert [j.external_id for j in first] == [j.external_id for j in second]
    assert [j.title for j in first] == [j.title for j in second]
    assert [j.salary_max for j in first] == [j.salary_max for j in second]


def test_posted_at_is_within_72_hours_of_the_supplied_now():
    now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    jobs = build_catalogue(JobSourceType.LINKEDIN, now)
    for job in jobs:
        assert now - timedelta(hours=73) <= job.posted_at <= now


def test_cross_platform_duplicates_exist():
    by_source = {source: get_adapter(source).search_jobs(ALL_QUERY) for source in CROSS_POST_SOURCES}
    keyed = {
        source: {(j.company_name, j.title, j.location): j for j in jobs} for source, jobs in by_source.items()
    }
    shared_keys = set.intersection(*(set(k) for k in keyed.values()))
    assert len(shared_keys) >= 6, f"expected >= 6 cross-platform duplicates, got {len(shared_keys)}"
    assert len(SHARED_POSTINGS) >= 6

    # same posting, different ids/urls and slightly different wording
    key = sorted(shared_keys)[0]
    variants = [keyed[source][key] for source in CROSS_POST_SOURCES]
    assert len({v.external_id for v in variants}) == len(variants)
    assert len({v.url for v in variants}) == len(variants)
    assert len({v.description for v in variants}) > 1


def test_company_careers_duplicates_are_marked_as_external_forms():
    jobs = get_adapter(JobSourceType.COMPANY_CAREERS).search_jobs(ALL_QUERY)
    assert all(j.application_type == ApplicationType.EXTERNAL_FORM for j in jobs)
    assert all("careers." in j.apply_url for j in jobs)


def test_catalogue_covers_the_indian_market():
    companies, locations = set(), set()
    for source in MOCK_SOURCES:
        for job in get_adapter(source).search_jobs(ALL_QUERY):
            companies.add(job.company_name)
            locations.add(job.location)
    assert {"Google", "Microsoft", "Amazon", "Flipkart", "Razorpay", "Infosys"} <= companies
    assert {"Northwind Labs", "Acme Cloud", "Bluefin Analytics"} <= companies
    assert {"Bangalore", "Hyderabad", "Pune", "Remote"} <= locations


# --------------------------------------------------------------------------- search filters


def test_search_honours_titles():
    jobs = get_adapter(JobSourceType.LINKEDIN).search_jobs(SearchQuery(titles=["Data Engineer"], limit=50))
    assert jobs
    assert all("data engineer" in j.title.lower() for j in jobs)


def test_search_honours_keywords_when_no_title_matches():
    jobs = get_adapter(JobSourceType.HIRIST).search_jobs(SearchQuery(keywords=["Kubernetes"], limit=50))
    assert jobs
    for job in jobs:
        haystack = (job.description + " ".join(job.required_skills + job.preferred_skills)).lower()
        assert "kubernetes" in haystack


def test_search_honours_locations_including_remote():
    remote = get_adapter(JobSourceType.WELLFOUND).search_jobs(SearchQuery(locations=["Remote"], limit=50))
    assert remote
    assert all(j.work_mode == WorkMode.REMOTE or "remote" in (j.location or "").lower() for j in remote)

    # "Bengaluru" and "Bangalore" are the same city
    blr = get_adapter(JobSourceType.NAUKRI).search_jobs(SearchQuery(locations=["Bengaluru"], limit=50))
    assert blr
    assert all((j.location or "").lower().startswith(("bangalore", "bengaluru")) for j in blr)


def test_search_honours_posted_within_hours_and_limit():
    adapter = get_adapter(JobSourceType.INDEED)
    recent = adapter.search_jobs(SearchQuery(posted_within_hours=12, limit=50))
    everything = adapter.search_jobs(SearchQuery(limit=50))
    assert len(recent) < len(everything)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=12, minutes=1)
    assert all(j.posted_at >= cutoff for j in recent)
    assert len(adapter.search_jobs(SearchQuery(limit=3))) == 3


def test_get_job_details_round_trips():
    adapter = get_adapter(JobSourceType.FOUNDIT)
    job = adapter.search_jobs(ALL_QUERY)[0]
    assert adapter.get_job_details(job.external_id).title == job.title
    assert adapter.get_job_details("does-not-exist") is None


# --------------------------------------------------------------------------- application type


def test_detect_application_type_defaults():
    assert detect_application_type(None, JobSourceType.LINKEDIN) == ApplicationType.EASY_APPLY
    assert (
        detect_application_type("https://www.linkedin.com/jobs/view/1/apply", JobSourceType.LINKEDIN)
        == ApplicationType.EASY_APPLY
    )
    assert detect_application_type("https://acme.com/careers/1", JobSourceType.LINKEDIN) == ApplicationType.EXTERNAL_FORM
    assert detect_application_type("https://boards.greenhouse.io/acme/jobs/1", JobSourceType.OTHER) == ApplicationType.ATS_FORM
    assert detect_application_type("https://jobs.lever.co/acme/1", JobSourceType.OTHER) == ApplicationType.ATS_FORM
    assert detect_application_type("http://x/demo-ats/jobs/a/apply", JobSourceType.DEMO_ATS) == ApplicationType.ATS_FORM
    assert detect_application_type(None, JobSourceType.WORKDAY) == ApplicationType.ATS_FORM
    assert detect_application_type("https://careers.acme.com/1", JobSourceType.COMPANY_CAREERS) == ApplicationType.EXTERNAL_FORM


def test_adapter_detect_application_type_uses_the_job():
    adapter = get_adapter(JobSourceType.LINKEDIN)
    job = DiscoveredJob(
        source=JobSourceType.LINKEDIN,
        external_id="x",
        url="https://www.linkedin.com/jobs/view/x",
        title="Software Engineer",
        company_name="Acme",
        apply_url="https://boards.greenhouse.io/acme/jobs/1",
    )
    assert adapter.detect_application_type(job) == ApplicationType.ATS_FORM


# --------------------------------------------------------------------------- authentication


def test_mock_authenticate_never_touches_credentials():
    class Exploding(dict):
        def __getitem__(self, key):  # pragma: no cover - must never run
            raise AssertionError("adapter read a credential")

        def get(self, *args, **kwargs):  # pragma: no cover - must never run
            raise AssertionError("adapter read a credential")

    for source in MOCK_SOURCES:
        result = get_adapter(source).authenticate(None, Exploding())
        assert result.ok is True
        assert result.is_mock is True


def test_demo_ats_authenticate_is_not_mock():
    result = DemoAtsAdapter().authenticate(None, None)
    assert result.ok is True and result.is_mock is False


# --------------------------------------------------------------------------- mock apply flow


def _ctx(external_id: str, *, answers=None) -> ApplyContext:
    job = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        title="Software Engineer",
        apply_url="https://www.linkedin.com/jobs/view/x/apply",
        company=SimpleNamespace(name="Acme Cloud"),
        sources=[SimpleNamespace(source=JobSourceType.LINKEDIN, external_id=external_id)],
    )
    return ApplyContext(application=SimpleNamespace(id="app-1", form_snapshot={}), job=job, answers=answers or [])


def _pick_external_id(requires_user: bool) -> str:
    for n in range(1000):
        candidate = f"LI-{n}"
        if (stable_int(candidate) % 7 == 0) is requires_user:
            return candidate
    raise AssertionError("no suitable external id found")


def test_mock_apply_flow_succeeds():
    adapter = get_adapter(JobSourceType.LINKEDIN)
    external_id = _pick_external_id(requires_user=False)
    ctx = _ctx(external_id)

    start = adapter.start_application(ctx)
    assert start.state == AutomationState.SUCCESS

    filled = adapter.fill_application(ctx)
    assert filled.state == AutomationState.SUCCESS
    fields = filled.form_snapshot["fields"]
    assert {f["key"] for f in fields} >= {"full_name", "email", "phone", "resume_file"}
    assert all(f["status"] == "filled" for f in fields)

    submitted = adapter.submit_application(ctx)
    assert submitted.state == AutomationState.SUCCESS
    assert submitted.external_application_id.startswith("LI-")
    assert "Acme Cloud" in submitted.confirmation_message
    assert adapter.get_application_status(submitted.external_application_id) is None


def test_mock_apply_pauses_for_a_deterministic_subset():
    adapter = get_adapter(JobSourceType.LINKEDIN)
    external_id = _pick_external_id(requires_user=True)
    result = adapter.fill_application(_ctx(external_id))
    assert result.state == AutomationState.REQUIRES_USER
    assert result.pause_reason == PauseReason.UNKNOWN_QUESTION
    custom = [f for f in result.form_snapshot["fields"] if f["key"].startswith("custom:")]
    assert custom and custom[0]["status"] == "needs_user_input"

    # once the user answers it, the same posting fills cleanly
    answered = SimpleNamespace(question_key=custom[0]["key"], answer="Two weeks from the offer date")
    assert adapter.fill_application(_ctx(external_id, answers=[answered])).state == AutomationState.SUCCESS


def test_pausing_subset_is_a_small_minority():
    adapter = get_adapter(JobSourceType.LINKEDIN)
    jobs = adapter.search_jobs(ALL_QUERY)
    paused = sum(1 for j in jobs if adapter._requires_user(j.external_id))
    assert 0 < paused < len(jobs) / 2


# --------------------------------------------------------------------------- demo ATS / ATS stubs


def test_demo_ats_falls_back_when_the_endpoint_is_down(monkeypatch):
    import httpx

    def boom(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", boom)
    jobs = DemoAtsAdapter().search_jobs(ALL_QUERY)
    for job in jobs:  # the local catalogue may or may not exist yet — both are valid
        assert job.source == JobSourceType.DEMO_ATS
        assert job.application_type == ApplicationType.ATS_FORM
        assert job.apply_url.endswith("/apply")
        assert "/demo-ats/jobs/" in job.url


def test_demo_ats_returns_empty_list_when_nothing_is_available(monkeypatch):
    adapter = DemoAtsAdapter()
    monkeypatch.setattr(adapter, "_fetch_payload", lambda: [])
    assert adapter.search_jobs(ALL_QUERY) == []


def test_demo_ats_maps_a_catalogue_row(monkeypatch):
    adapter = DemoAtsAdapter()
    row = {
        "slug": "northwind-backend-engineer",
        "title": "Backend Engineer",
        "company": "Northwind Labs",
        "company_domain": "northwindlabs.io",
        "location": "Bangalore",
        "work_mode": "HYBRID",
        "employment_type": "FULL_TIME",
        "salary_min": 1800000,
        "salary_max": 2800000,
        "salary_currency": "INR",
        "experience_min": 2,
        "experience_max": 5,
        "required_skills": ["Node.js", "PostgreSQL"],
        "preferred_skills": ["Docker"],
        "description": "Build APIs.",
        "posted_hours_ago": 6,
        "logo_url": "https://logo.example/nw.png",
    }
    monkeypatch.setattr(adapter, "_fetch_payload", lambda: [row])
    job = adapter.search_jobs(ALL_QUERY)[0]
    assert job.external_id == "northwind-backend-engineer"
    assert job.url.endswith("/demo-ats/jobs/northwind-backend-engineer")
    assert job.apply_url.endswith("/demo-ats/jobs/northwind-backend-engineer/apply")
    assert job.work_mode == WorkMode.HYBRID
    assert job.salary_max == 2800000
    assert job.application_type == ApplicationType.ATS_FORM


def test_browser_adapters_require_a_page():
    for adapter in (DemoAtsAdapter(), GreenhouseAdapter(), LeverAdapter()):
        ctx = ApplyContext(application=SimpleNamespace(form_snapshot={}), job=SimpleNamespace(apply_url="http://x"), page=None)
        for step in (adapter.start_application, adapter.fill_application, adapter.submit_application):
            result = step(ctx)
            assert result.state == AutomationState.FAILED
            assert result.message == "browser page required"


def test_board_adapters_find_nothing_without_a_board_and_support_applying():
    for adapter in (GreenhouseAdapter(), LeverAdapter()):
        assert adapter.search_jobs(ALL_QUERY) == []  # no board configured -> no request, no jobs
        info = adapter.info()
        assert info.is_mock is False
        assert info.supports_auto_apply is True
        assert info.requires_account is False
        assert info.uses_browser is True
        assert "API" in info.terms_note


def test_importing_adapters_does_not_require_playwright():
    import sys

    assert "playwright" not in sys.modules


def test_adapters_map_matches_registered_instances():
    for source, cls in ADAPTERS.items():
        assert isinstance(get_adapter(source), cls)
        assert get_adapter(source).source == source


# --------------------------------------------------------------------------- demo ATS browser flow


class FakePage:
    """The few Playwright ``Page`` calls the hosted-form flow makes."""

    def __init__(self, html: str = "") -> None:
        self.html = html
        self.goto_url: str | None = None
        self.clicked: str | None = None

    def goto(self, url, **kwargs):
        self.goto_url = url

    def wait_for_selector(self, selector, **kwargs):
        return None

    def wait_for_load_state(self, state, **kwargs):
        return None

    def click(self, selector, **kwargs):
        self.clicked = selector

    def content(self) -> str:
        return self.html


BROWSER_SKIP = "the browser module (CONTRACTS.md 12) is not available in this checkout"


def _require_browser():
    """These tests drive the shared hosted-form flow, which needs the browser module."""
    schemas = pytest.importorskip("app.modules.browser.schemas", reason=BROWSER_SKIP)
    detector = pytest.importorskip("app.modules.browser.detector", reason=BROWSER_SKIP)
    autofill = pytest.importorskip("app.modules.browser.autofill", reason=BROWSER_SKIP)
    return schemas, detector, autofill


def _detected(fields, *, blockers=(), submit_selector="#submit_app"):
    from app.modules.browser.schemas import DetectedForm

    return DetectedForm(
        url="http://localhost:8000/demo-ats/jobs/x/apply",
        fields=list(fields),
        submit_selector=submit_selector,
        blockers=list(blockers),
    )


def _field(label, selector, *, required=True):
    from app.models.enums import FieldType
    from app.modules.browser.schemas import DetectedField

    return DetectedField(selector=selector, label=label, field_type=FieldType.TEXT, required=required)


def _browser_ctx(page):
    job = SimpleNamespace(id="job-1", apply_url="http://localhost:8000/demo-ats/jobs/x/apply", title="Backend Engineer")
    return ApplyContext(application=SimpleNamespace(id="app-1", form_snapshot={}), job=job, page=page)


def test_demo_ats_start_application_navigates(monkeypatch):
    page = FakePage()
    result = DemoAtsAdapter().start_application(_browser_ctx(page))
    assert result.state == AutomationState.SUCCESS
    assert page.goto_url.endswith("/demo-ats/jobs/x/apply")


def test_demo_ats_fill_pauses_on_a_blocker(monkeypatch):
    schemas, detector, _ = _require_browser()

    blocker = schemas.Blocker(kind=PauseReason.CAPTCHA, selector=".g-recaptcha", message="CAPTCHA detected")
    monkeypatch.setattr(detector, "detect_form", lambda page: _detected([], blockers=[blocker]))

    result = DemoAtsAdapter().fill_application(_browser_ctx(FakePage()))
    assert result.state == AutomationState.REQUIRES_USER
    assert result.pause_reason == PauseReason.CAPTCHA
    assert result.form_snapshot["blockers"][0]["message"] == "CAPTCHA detected"


def test_demo_ats_fill_pauses_when_a_required_answer_is_missing(monkeypatch):
    _, detector, _ = _require_browser()

    monkeypatch.setattr(
        detector, "detect_form", lambda page: _detected([_field("Email", "#email"), _field("Phone", "#phone")])
    )
    result = DemoAtsAdapter().fill_application(_browser_ctx(FakePage()))
    assert result.state == AutomationState.REQUIRES_USER
    assert result.pause_reason == PauseReason.UNKNOWN_QUESTION
    assert "Email" in result.message


def test_demo_ats_fill_succeeds_with_answers(monkeypatch):
    schemas, detector, autofill = _require_browser()

    monkeypatch.setattr(detector, "detect_form", lambda page: _detected([_field("Email", "#email")]))
    monkeypatch.setattr(
        autofill,
        "fill_form",
        lambda page, detected, answers, **kwargs: schemas.FillResult(filled=[], skipped=[], needs_user=[]),
    )
    ctx = _browser_ctx(FakePage())
    ctx.answers = [SimpleNamespace(question_key="email", answer="demo@jobpilot.ai")]

    result = DemoAtsAdapter().fill_application(ctx)
    assert result.state == AutomationState.SUCCESS
    assert result.form_snapshot["submit_selector"] == "#submit_app"
    assert result.form_snapshot["fields"][0]["mapped_to"] == "email"


def test_demo_ats_submit_extracts_the_application_id():
    page = FakePage("<h1>Thank you for applying</h1><p>Application ID: DEMO-7QX4K2</p>")
    result = DemoAtsAdapter().submit_application(_browser_ctx(page))
    assert result.state == AutomationState.SUCCESS
    assert result.external_application_id == "DEMO-7QX4K2"
    assert "DEMO-7QX4K2" in result.confirmation_message
    assert page.clicked == "button[type=submit]"  # the demo ATS form's own submit button


def test_demo_ats_submit_fails_without_a_confirmation():
    result = DemoAtsAdapter().submit_application(_browser_ctx(FakePage("<h1>Something went wrong</h1>")))
    assert result.state == AutomationState.FAILED


def test_submit_prefers_the_detected_submit_selector():
    page = FakePage("<p>Thank you for applying. Application ID: DEMO-ABC123</p>")
    ctx = _browser_ctx(page)
    ctx.application = SimpleNamespace(id="app-1", form_snapshot={"submit_selector": "#apply-now"})
    assert DemoAtsAdapter().submit_application(ctx).external_application_id == "DEMO-ABC123"
    assert page.clicked == "#apply-now"
