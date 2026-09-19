"""Tests for the jobs module: normalisation, dedupe/ingest and the API (§9)."""
from __future__ import annotations

import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token, hash_password
from app.models.application import Application
from app.models.company import Company
from app.models.enums import (
    ApplicationStatus,
    ApplicationType,
    CompanyPriority,
    EmploymentType,
    JobSourceType,
    WorkMode,
)
from app.models.job import Job, JobMatch, JobSource
from app.models.profile import CompanyPreference, JobPreference, UserProfile
from app.models.user import User
from app.modules.adapters.base import DiscoveredJob
from app.modules.jobs import service
from app.modules.jobs.dedupe import compute_dedupe_hash, description_similarity, title_similarity
from app.modules.jobs.normalize import normalize_company_name, normalize_location, normalize_title

API = "/api/v1/jobs"

#: Captured before the autouse fixture below swaps in the local fallback.
REAL_GET_OR_CREATE_COMPANY = service.get_or_create_company


def _utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _local_companies(monkeypatch):
    """Pin company creation to the local fallback.

    The companies module is written by another agent in parallel; these tests assert on
    dedupe behaviour, so they must not depend on whichever implementation is on disk.
    """
    monkeypatch.setattr(service, "get_or_create_company", service._local_get_or_create_company)


@pytest.fixture
def user(db) -> User:
    row = User(
        email="jobs-tester@example.com",
        hashed_password=hash_password("StrongPass123!"),
        full_name="Jobs Tester",
    )
    db.add(row)
    db.flush()
    db.add(
        UserProfile(
            user_id=row.id,
            skills=["React", "Node.js", "TypeScript", "PostgreSQL", "Docker"],
            technologies=["AWS"],
            years_of_experience=3.0,
            city="Bangalore",
        )
    )
    db.add(
        JobPreference(
            user_id=row.id,
            desired_titles=["Software Engineer", "Full Stack Developer", "Backend Engineer"],
            preferred_locations=["Bangalore", "Remote"],
            preferred_technologies=["React", "Node.js"],
            min_salary=1200000,
            desired_salary=2000000,
            min_match_score=75,
            only_posted_within_hours=72,
        )
    )
    db.commit()
    return row


@pytest.fixture
def api(client, user):
    """TestClient authenticated as ``user`` (independent of the auth module)."""
    token = create_access_token(user.id, user.role.value)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_job(
    source: JobSourceType,
    *,
    external_id: str,
    title: str = "Software Engineer",
    company: str = "Acme Cloud",
    location: str | None = "Bangalore",
    description: str = "We are hiring a backend engineer to build APIs with Node.js and PostgreSQL.",
    url: str | None = None,
    apply_url: str | None = None,
    application_type: ApplicationType = ApplicationType.EASY_APPLY,
    posted_at: datetime | None = None,
    required_skills: list[str] | None = None,
    **kwargs,
) -> DiscoveredJob:
    return DiscoveredJob(
        source=source,
        external_id=external_id,
        url=url or f"https://{source.value.lower()}.example/jobs/{external_id}",
        title=title,
        company_name=company,
        location=location,
        work_mode=kwargs.pop("work_mode", WorkMode.HYBRID),
        employment_type=kwargs.pop("employment_type", EmploymentType.FULL_TIME),
        description=description,
        required_skills=required_skills if required_skills is not None else ["Node.js", "PostgreSQL"],
        preferred_skills=kwargs.pop("preferred_skills", ["Docker"]),
        experience_min=kwargs.pop("experience_min", 2.0),
        experience_max=kwargs.pop("experience_max", 5.0),
        salary_min=kwargs.pop("salary_min", 1500000),
        salary_max=kwargs.pop("salary_max", 2500000),
        salary_currency="INR",
        posted_at=posted_at or datetime.now(timezone.utc) - timedelta(hours=3),
        apply_url=apply_url or f"https://{source.value.lower()}.example/jobs/{external_id}/apply",
        application_type=application_type,
        **kwargs,
    )


# --------------------------------------------------------------------------- normalisation


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Software Engineer", "software engineer"),
        ("Sr. Software Engineer", "senior software engineer"),
        ("Senior Software Engineer (Backend)", "senior software engineer"),
        ("SDE II", "software development engineer 2"),
        ("SDE-2", "software development engineer 2"),
        ("SDE I", "software development engineer 1"),
        ("Full-Stack Developer [Remote]", "full stack developer"),
        ("Jr. React Developer - Urgent Hiring!", "junior react developer"),
        ("Back-End Engineer / Node.js", "backend engineer node js"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_title(raw, expected):
    assert normalize_title(raw) == expected


def test_normalize_title_collapses_variants():
    assert normalize_title("SDE II") == normalize_title("Software Development Engineer 2")
    assert normalize_title("Sr. Software Engineer") == normalize_title("Senior Software Engineer")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Bangalore", "bangalore"),
        ("Bengaluru", "bangalore"),
        ("Bengaluru, Karnataka, India", "bangalore"),
        ("Gurgaon", "gurugram"),
        ("Gurugram", "gurugram"),
        ("Noida", "delhi ncr"),
        ("New Delhi", "delhi ncr"),
        ("Delhi NCR", "delhi ncr"),
        ("Remote", "remote"),
        ("Remote (India)", "remote"),
        ("Work From Home", "remote"),
        ("Hybrid - Pune", "pune"),
        (None, None),
    ],
)
def test_normalize_location(raw, expected):
    assert normalize_location(raw) == expected


def test_normalize_company_name_strips_legal_suffixes():
    assert normalize_company_name("Acme Cloud Pvt. Ltd.") == normalize_company_name("ACME Cloud")
    assert normalize_company_name("Northwind Labs") == "northwind"
    assert normalize_company_name("Infosys Limited") == "infosys"


# --------------------------------------------------------------------------- dedupe primitives


def test_dedupe_hash_is_stable_and_discriminating():
    a = compute_dedupe_hash("google", "software engineer", "bangalore")
    assert a == compute_dedupe_hash("google", "software engineer", "bangalore")
    assert len(a) == 32
    assert a != compute_dedupe_hash("google", "software engineer", "hyderabad")
    assert a != compute_dedupe_hash("microsoft", "software engineer", "bangalore")


def test_similarity_helpers():
    assert title_similarity("Sr. Software Engineer", "Senior Software Engineer") >= 90
    assert title_similarity("Data Engineer", "DevOps Engineer") < 90
    assert description_similarity("build apis with node", "build apis with node and redis") >= 0.8
    assert description_similarity("", "anything") == 0.0


# --------------------------------------------------------------------------- ingestion


def test_ingest_creates_one_job_per_posting(db, user):
    result = service.ingest_discovered(
        db,
        user.id,
        [
            make_job(JobSourceType.LINKEDIN, external_id="li-1"),
            make_job(JobSourceType.NAUKRI, external_id="nk-1", title="Data Engineer", company="Bluefin Analytics"),
        ],
    )
    db.commit()
    assert result.jobs_found == 2
    assert result.jobs_new == 2
    assert result.duplicates_merged == 0
    assert len(result.job_ids_new) == 2
    assert db.scalar(select(func.count(Job.id))) == 2


def test_ingest_merges_cross_platform_duplicates(db, user):
    """Same company+title+location on four platforms → one Job, four JobSource rows."""
    postings = [
        make_job(JobSourceType.LINKEDIN, external_id="li-9", title="Sr. Software Engineer"),
        make_job(JobSourceType.NAUKRI, external_id="nk-9", title="Senior Software Engineer"),
        make_job(JobSourceType.INDEED, external_id="in-9", title="Senior Software Engineer (Backend)", location="Bengaluru"),
        make_job(
            JobSourceType.COMPANY_CAREERS,
            external_id="cc-9",
            title="Senior Software Engineer",
            application_type=ApplicationType.EXTERNAL_FORM,
            apply_url="https://careers.acmecloud.io/jobs/cc-9/apply",
        ),
    ]
    result = service.ingest_discovered(db, user.id, postings)
    db.commit()

    assert result.jobs_found == 4
    assert result.jobs_new == 1
    assert result.duplicates_merged == 3
    assert len(result.job_ids_all) == 1

    job = db.scalars(select(Job)).unique().one()
    assert {s.source for s in job.sources} == {
        JobSourceType.LINKEDIN,
        JobSourceType.NAUKRI,
        JobSourceType.INDEED,
        JobSourceType.COMPANY_CAREERS,
    }
    assert db.scalar(select(func.count(JobSource.id))) == 4
    assert db.scalar(select(func.count(Company.id))) == 1
    # company careers outranks the aggregators as the place to apply
    assert job.apply_url == "https://careers.acmecloud.io/jobs/cc-9/apply"
    assert job.application_type == ApplicationType.EXTERNAL_FORM
    assert job.raw["apply_source"] == JobSourceType.COMPANY_CAREERS.value


def test_ingest_is_idempotent_for_the_same_listing(db, user):
    posting = make_job(JobSourceType.LINKEDIN, external_id="li-same")
    service.ingest_discovered(db, user.id, [posting])
    db.commit()
    second = service.ingest_discovered(db, user.id, [posting])
    db.commit()

    assert second.jobs_new == 0
    assert second.duplicates_merged == 0
    assert second.per_source[JobSourceType.LINKEDIN.value]["seen"] == 1
    assert db.scalar(select(func.count(Job.id))) == 1
    assert db.scalar(select(func.count(JobSource.id))) == 1


def test_ingest_keeps_earliest_posted_at_and_merges_skills(db, user):
    older = datetime.now(timezone.utc) - timedelta(hours=40)
    newer = datetime.now(timezone.utc) - timedelta(hours=2)
    service.ingest_discovered(
        db,
        user.id,
        [
            make_job(JobSourceType.LINKEDIN, external_id="li-a", posted_at=newer, required_skills=["Node.js"]),
            make_job(JobSourceType.NAUKRI, external_id="nk-a", posted_at=older, required_skills=["PostgreSQL", "Redis"]),
        ],
    )
    db.commit()
    job = db.scalars(select(Job)).unique().one()
    assert abs((_utc(job.posted_at) - older).total_seconds()) < 2
    assert set(job.required_skills) == {"Node.js", "PostgreSQL", "Redis"}


def test_ingest_matches_by_canonical_url(db, user):
    shared_url = "https://example.com/jobs/1"
    service.ingest_discovered(db, user.id, [make_job(JobSourceType.LINKEDIN, external_id="u-1", url=shared_url)])
    db.commit()
    result = service.ingest_discovered(
        db,
        user.id,
        [make_job(JobSourceType.INDEED, external_id="u-2", url=shared_url, title="Totally Different Title")],
    )
    db.commit()
    assert result.duplicates_merged == 1
    assert db.scalar(select(func.count(Job.id))) == 1


def test_ingest_matches_by_fuzzy_title_and_description(db, user):
    body = (
        "We are looking for an engineer to build and scale our payments APIs. "
        "You will work with Node.js, PostgreSQL and Docker in a small team."
    )
    service.ingest_discovered(
        db,
        user.id,
        [make_job(JobSourceType.LINKEDIN, external_id="f-1", title="Backend Engineer", description=body)],
    )
    db.commit()
    result = service.ingest_discovered(
        db,
        user.id,
        [
            make_job(
                JobSourceType.HIRIST,
                external_id="f-2",
                title="Backend Engineer",
                location="Bangalore, Karnataka",  # hashes differently only if normalisation fails
                description=body + " Immediate joiners preferred.",
            )
        ],
    )
    db.commit()
    assert result.duplicates_merged == 1
    assert db.scalar(select(func.count(Job.id))) == 1


def test_ingest_reports_per_source_counts(db, user):
    result = service.ingest_discovered(
        db,
        user.id,
        [
            make_job(JobSourceType.LINKEDIN, external_id="p-1"),
            make_job(JobSourceType.NAUKRI, external_id="p-2"),
            make_job(JobSourceType.NAUKRI, external_id="p-3", title="Data Engineer"),
        ],
    )
    db.commit()
    assert result.per_source[JobSourceType.LINKEDIN.value]["found"] == 1
    assert result.per_source[JobSourceType.NAUKRI.value]["found"] == 2
    assert result.per_source[JobSourceType.NAUKRI.value]["new"] == 1
    assert result.per_source[JobSourceType.NAUKRI.value]["duplicates"] == 1


def test_get_or_create_company_delegates_to_the_companies_module(db, monkeypatch):
    """When ``companies.service`` exists, jobs must use it rather than its own fallback."""
    calls: list[str] = []
    module = types.ModuleType("app.modules.companies.service")

    def fake_get_or_create_company(session, name, **attrs):
        calls.append(name)
        company = Company(name=name, normalized_name=name.lower().replace(" ", ""))
        session.add(company)
        session.flush()
        return company

    module.get_or_create_company = fake_get_or_create_company
    monkeypatch.setitem(sys.modules, "app.modules.companies.service", module)

    company = REAL_GET_OR_CREATE_COMPANY(db, "Peakform Systems", domain="peakform.dev")
    assert calls == ["Peakform Systems"]
    assert company.name == "Peakform Systems"


# --------------------------------------------------------------------------- list API


def _seed_jobs(db, user) -> dict[str, Job]:
    service.ingest_discovered(
        db,
        user.id,
        [
            make_job(
                JobSourceType.LINKEDIN,
                external_id="s-1",
                title="Backend Engineer",
                company="Razorpay",
                location="Bangalore",
                salary_min=2000000,
                salary_max=3000000,
                posted_at=datetime.now(timezone.utc) - timedelta(hours=2),
            ),
            make_job(
                JobSourceType.NAUKRI,
                external_id="s-2",
                title="Data Engineer",
                company="Infosys",
                location="Pune",
                work_mode=WorkMode.ONSITE,
                salary_min=900000,
                salary_max=1400000,
                posted_at=datetime.now(timezone.utc) - timedelta(hours=40),
            ),
            make_job(
                JobSourceType.WELLFOUND,
                external_id="s-3",
                title="Frontend Engineer",
                company="Northwind Labs",
                location="Remote",
                work_mode=WorkMode.REMOTE,
                salary_min=1600000,
                salary_max=2200000,
                posted_at=datetime.now(timezone.utc) - timedelta(hours=10),
            ),
        ],
    )
    db.commit()
    return {job.title: job for job in db.scalars(select(Job)).unique()}


def test_list_jobs_requires_authentication(client):
    assert client.get(API).status_code == 401


def test_list_jobs_returns_cards(api, db, user):
    _seed_jobs(db, user)
    body = api.get(API).json()
    assert body["total"] == 3
    assert body["page"] == 1 and body["page_size"] == 20
    card = body["items"][0]
    assert {"id", "title", "company", "sources", "primary_source", "company_priority", "missing_skills"} <= card.keys()
    assert card["company"]["name"]
    assert card["company_priority"] == CompanyPriority.P2.value


@pytest.mark.parametrize(
    "params,expected_titles",
    [
        ({"q": "razorpay"}, {"Backend Engineer"}),
        ({"company": "Infosys"}, {"Data Engineer"}),
        ({"location": "Pune"}, {"Data Engineer"}),
        ({"location": "Bengaluru"}, {"Backend Engineer"}),
        ({"work_mode": "REMOTE"}, {"Frontend Engineer"}),
        ({"salary_min": 2500000}, {"Backend Engineer"}),
        ({"source": "WELLFOUND"}, {"Frontend Engineer"}),
        ({"posted_within_hours": 24}, {"Backend Engineer", "Frontend Engineer"}),
        ({"status": "NONE"}, {"Backend Engineer", "Data Engineer", "Frontend Engineer"}),
    ],
)
def test_list_jobs_filters(api, db, user, params, expected_titles):
    _seed_jobs(db, user)
    body = api.get(API, params=params).json()
    assert {item["title"] for item in body["items"]} == expected_titles


def test_list_jobs_sorting(api, db, user):
    _seed_jobs(db, user)

    by_posted = [i["title"] for i in api.get(API, params={"sort": "posted"}).json()["items"]]
    assert by_posted == ["Backend Engineer", "Frontend Engineer", "Data Engineer"]

    by_salary = [i["title"] for i in api.get(API, params={"sort": "salary"}).json()["items"]]
    assert by_salary == ["Backend Engineer", "Frontend Engineer", "Data Engineer"]

    api.post("/api/v1/matching/analyze-all")
    by_match = api.get(API, params={"sort": "match"}).json()["items"]
    scores = [i["match_score"] for i in by_match]
    assert all(s is not None for s in scores)
    assert scores == sorted(scores, reverse=True)


def test_list_jobs_score_filters_and_pagination(api, db, user):
    _seed_jobs(db, user)
    api.post("/api/v1/matching/analyze-all")

    page = api.get(API, params={"page_size": 2, "page": 2, "sort": "posted"}).json()
    assert page["total"] == 3 and len(page["items"]) == 1

    assert api.get(API, params={"min_score": 101}).status_code == 422
    assert api.get(API, params={"max_score": 0}).json()["total"] == 0
    assert api.get(API, params={"min_score": 0}).json()["total"] == 3
    assert api.get(API, params={"min_score": 90}).json()["total"] >= 1


def test_list_jobs_priority_filter(api, db, user):
    jobs = _seed_jobs(db, user)
    razorpay = jobs["Backend Engineer"].company
    db.add(
        CompanyPreference(
            user_id=user.id,
            company_id=razorpay.id,
            company_name=razorpay.name,
            normalized_name=razorpay.normalized_name,
            priority=CompanyPriority.P1,
        )
    )
    db.commit()

    p1 = api.get(API, params={"priority": "P1"}).json()
    assert {i["title"] for i in p1["items"]} == {"Backend Engineer"}
    assert p1["items"][0]["company_priority"] == "P1"

    p2 = api.get(API, params={"priority": "P2"}).json()
    assert {i["title"] for i in p2["items"]} == {"Data Engineer", "Frontend Engineer"}


def test_list_and_detail_agree_on_a_prefix_matched_priority(api, db, user):
    """Regression: the list used to match preferences on the exact normalised name only.

    ``companies.service.resolve_priority`` also matches a whole-word *prefix*, so
    "Google" covers "Google (Demo Careers)" - the card and the detail page (and the
    ?priority= filter) must all agree on P1.
    """
    service.ingest_discovered(
        db,
        user.id,
        [
            make_job(
                JobSourceType.DEMO_ATS,
                external_id="demo-google-1",
                title="Software Engineer II, Full Stack",
                company="Google (Demo Careers)",
            )
        ],
    )
    db.add(
        CompanyPreference(
            user_id=user.id,
            company_id=None,
            company_name="Google",
            normalized_name="google",
            priority=CompanyPriority.P1,
        )
    )
    db.commit()

    job = db.scalars(select(Job).join(Company).where(Company.name == "Google (Demo Careers)")).unique().first()
    assert job is not None and job.company.normalized_name == "google demo careers"

    card = next(i for i in api.get(API, params={"company": "Google"}).json()["items"] if i["id"] == str(job.id))
    detail = api.get(f"{API}/{job.id}").json()
    assert card["company_priority"] == detail["company_priority"] == CompanyPriority.P1.value

    p1_ids = {i["id"] for i in api.get(API, params={"priority": "P1"}).json()["items"]}
    p2_ids = {i["id"] for i in api.get(API, params={"priority": "P2"}).json()["items"]}
    assert str(job.id) in p1_ids and str(job.id) not in p2_ids


def test_job_detail_includes_sources_and_match(api, db, user):
    jobs = _seed_jobs(db, user)
    job_id = jobs["Backend Engineer"].id
    api.post(f"{API}/{job_id}/analyze")

    detail = api.get(f"{API}/{job_id}").json()
    assert detail["description"]
    assert detail["job_sources"][0]["source"] == JobSourceType.LINKEDIN.value
    assert detail["match"]["match_score"] == detail["match_score"]
    assert detail["application"] is None


def test_job_detail_404(api):
    assert api.get(f"{API}/{uuid.uuid4()}").status_code == 404


# --------------------------------------------------------------------------- discover


def test_discover_ingests_and_analyzes(api, db, user):
    body = api.post(f"{API}/discover", json={"sources": ["LINKEDIN", "NAUKRI", "INDEED"], "limit": 25}).json()

    assert body["jobs_found"] > 0
    assert body["jobs_new"] > 0
    assert body["duplicates_merged"] > 0, "the mock catalogues must contain cross-platform duplicates"
    assert body["jobs_analyzed"] == body["jobs_new"]
    assert {row["source"] for row in body["sources"]} == {"LINKEDIN", "NAUKRI", "INDEED"}
    assert all(row["error"] is None for row in body["sources"])

    db.expire_all()
    assert db.scalar(select(func.count(JobMatch.id)).where(JobMatch.user_id == user.id)) == body["jobs_new"]

    # every new job is audited as job.found with "<Company> - <Title>"
    from app.models.audit import AuditLog

    found = db.scalars(select(AuditLog).where(AuditLog.action == "job.found")).all()
    assert len(found) == body["jobs_new"]
    assert "—" in found[0].message
    assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "job.analyzed")) == body["jobs_new"]


def test_discover_defaults_to_every_mock_source_plus_demo_ats(api, db, user):
    body = api.post(f"{API}/discover", json={}).json()
    sources = {row["source"] for row in body["sources"]}
    assert "DEMO_ATS" in sources
    assert {"LINKEDIN", "NAUKRI", "INDEED", "GLASSDOOR", "FOUNDIT"} <= sources


def test_discover_uses_connected_accounts_when_present(db, user):
    from app.models.automation import ConnectedAccount

    db.add(ConnectedAccount(user_id=user.id, source=JobSourceType.NAUKRI, is_mock=True))
    db.commit()
    resolved = service.resolve_discovery_sources(db, user.id, None)
    assert resolved == [JobSourceType.NAUKRI, JobSourceType.DEMO_ATS]


def test_discover_survives_a_broken_adapter(api, db, user, monkeypatch):
    from app.modules.adapters.registry import get_adapter

    adapter = get_adapter(JobSourceType.LINKEDIN)
    monkeypatch.setattr(adapter, "search_jobs", lambda query: (_ for _ in ()).throw(RuntimeError("platform down")))

    body = api.post(f"{API}/discover", json={"sources": ["LINKEDIN", "NAUKRI"]}).json()
    rows = {row["source"]: row for row in body["sources"]}
    assert rows["LINKEDIN"]["error"] == "platform down"
    assert rows["NAUKRI"]["found"] > 0


def test_build_search_query_from_preferences(db, user):
    preference = service.get_job_preference(db, user.id)
    query = service.build_search_query(preference, limit=10)
    assert query.titles == ["Software Engineer", "Full Stack Developer", "Backend Engineer"]
    assert query.locations == ["Bangalore", "Remote"]
    assert query.keywords == ["React", "Node.js"]
    assert query.posted_within_hours == 72
    assert query.limit == 10


def test_build_search_query_without_a_preference_row(db):
    other = User(email="nopref@example.com", hashed_password=hash_password("StrongPass123!"), full_name="No Pref")
    db.add(other)
    db.commit()
    query = service.build_search_query(service.get_job_preference(db, other.id))
    assert query.titles == [] and query.locations == [] and query.keywords == []


# --------------------------------------------------------------------------- queue / skip / sources


def test_queue_job_creates_an_application(api, db, user):
    jobs = _seed_jobs(db, user)
    job = jobs["Backend Engineer"]
    api.post(f"{API}/{job.id}/analyze")

    response = api.post(f"{API}/{job.id}/queue")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == ApplicationStatus.QUEUED.value
    assert body["priority"] == CompanyPriority.P2.value
    assert body["match_score"] is not None

    # idempotent
    assert api.post(f"{API}/{job.id}/queue").json()["id"] == body["id"]
    db.expire_all()
    assert db.scalar(select(func.count(Application.id))) == 1


def test_queue_job_uses_the_company_priority(api, db, user):
    jobs = _seed_jobs(db, user)
    job = jobs["Backend Engineer"]
    db.add(
        CompanyPreference(
            user_id=user.id,
            company_id=job.company_id,
            company_name=job.company.name,
            normalized_name=job.company.normalized_name,
            priority=CompanyPriority.P1,
        )
    )
    db.commit()
    assert api.post(f"{API}/{job.id}/queue").json()["priority"] == "P1"


def test_skip_job_marks_the_application_skipped(api, db, user):
    jobs = _seed_jobs(db, user)
    job = jobs["Data Engineer"]
    body = api.post(f"{API}/{job.id}/skip", json={"reason": "Not interested in data roles"}).json()
    assert body["status"] == ApplicationStatus.SKIPPED.value
    assert body["skipped_reason"] == "Not interested in data roles"

    listed = api.get(API, params={"status": "SKIPPED"}).json()
    assert {i["title"] for i in listed["items"]} == {"Data Engineer"}


def test_sources_endpoint_reports_adapter_info_and_counts(api, db, user):
    _seed_jobs(db, user)
    rows = api.get(f"{API}/sources").json()
    by_source = {row["source"]: row for row in rows}
    assert by_source["LINKEDIN"]["job_count"] == 1
    assert by_source["LINKEDIN"]["is_mock"] is True
    assert by_source["DEMO_ATS"]["is_mock"] is False
    assert by_source["DEMO_ATS"]["uses_browser"] is True
    assert by_source["GREENHOUSE"]["job_count"] == 0
    assert all(row["terms_note"] for row in rows)


def test_jobs_are_scoped_to_the_current_user(api, db, user):
    """Another user's match and application must never leak into this user's cards."""
    jobs = _seed_jobs(db, user)
    other = User(email="other@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Other")
    db.add(other)
    db.flush()
    job = jobs["Backend Engineer"]
    db.add(
        Application(user_id=other.id, job_id=job.id, status=ApplicationStatus.APPLIED, priority=CompanyPriority.P1)
    )
    db.add(
        JobMatch(
            job_id=job.id,
            user_id=other.id,
            match_score=99,
            title_score=99,
            analyzed_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    card = next(i for i in api.get(API).json()["items"] if i["title"] == "Backend Engineer")
    assert card["application_status"] is None
    assert card["match_score"] is None
