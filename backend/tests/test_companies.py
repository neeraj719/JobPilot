"""Company normalisation, priority resolution and preference tests (contract §4)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application, ApplicationEvent
from app.models.company import Company
from app.models.enums import ApplicationStatus, CompanyPriority
from app.models.job import Job
from app.models.user import User
from app.modules.companies import service

COMPANIES = "/api/v1/companies"
PREFERENCES = "/api/v1/companies/preferences"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.core.rate_limit import rate_limiter

    hits = getattr(rate_limiter._backend, "_hits", None)
    if hits is not None:
        hits.clear()
    yield


@pytest.fixture
def user(db: Session):
    from app.modules.auth.service import create_user

    created = create_user(db, "recruit@example.com", "StrongPass123", "Recruit Tester")
    db.commit()
    return created


def _make_job(db: Session, company: Company, title: str = "Software Engineer", *, is_active: bool = True) -> Job:
    job = Job(
        company_id=company.id,
        title=title,
        normalized_title=title.lower(),
        description="",
        dedupe_hash=uuid.uuid4().hex,
        is_active=is_active,
    )
    db.add(job)
    db.flush()
    return job


def _make_application(db: Session, user_id: uuid.UUID, job: Job, status: ApplicationStatus) -> Application:
    application = Application(user_id=user_id, job_id=job.id, status=status)
    db.add(application)
    db.flush()
    return application


# --------------------------------------------------------------------------- normalisation


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Google", "google"),
        ("Google India Pvt. Ltd.", "google"),
        ("GOOGLE INC", "google"),
        ("  google   ", "google"),
        ("Microsoft Corporation", "microsoft"),
        ("Infosys Technologies Limited", "infosys"),
        ("Tata Consultancy Services", "tata consultancy"),
        ("Acme Cloud Labs", "acme cloud"),
        ("Zoho Corp.", "zoho"),
        ("Flipkart Internet Private Limited", "flipkart internet"),
        ("H&M Group", "h and m"),
        ("Technologies", "technologies"),
        ("", ""),
    ],
)
def test_normalize_company_name(raw: str, expected: str) -> None:
    assert service.normalize_company_name(raw) == expected


def test_google_variants_normalise_to_the_same_key() -> None:
    assert service.normalize_company_name("Google India Pvt. Ltd.") == service.normalize_company_name("Google")


def test_get_or_create_company_is_idempotent_and_never_guesses_a_domain(db: Session) -> None:
    first = service.get_or_create_company(db, "Google India Pvt. Ltd.")
    assert first.domain is None

    second = service.get_or_create_company(db, "Google", domain="google.com", industry="Technology")
    db.commit()

    assert second.id == first.id
    assert second.normalized_name == "google"
    assert second.domain == "google.com"  # only because it was supplied
    assert second.industry == "Technology"
    assert len(db.scalars(select(Company)).all()) == 1


def test_get_or_create_company_rejects_blank_names(db: Session) -> None:
    from app.core.exceptions import ValidationFailed

    with pytest.raises(ValidationFailed):
        service.get_or_create_company(db, "   ")


# --------------------------------------------------------------------------- priorities


def test_priority_defaults_to_p2(db: Session, user) -> None:
    company = service.get_or_create_company(db, "Unknown Startup")
    db.commit()
    assert service.get_priority(db, user.id, company) == CompanyPriority.P2


def test_priority_matches_exact_normalized_name(db: Session, user) -> None:
    company = service.get_or_create_company(db, "Google India Pvt Ltd")
    service.upsert_preference(db, user.id, "Google", CompanyPriority.P1)
    db.commit()
    assert service.get_priority(db, user.id, company) == CompanyPriority.P1


def test_priority_matches_whole_word_prefix(db: Session, user) -> None:
    cloud = service.get_or_create_company(db, "Google Cloud")
    googly = service.get_or_create_company(db, "Googly Toys")
    service.upsert_preference(db, user.id, "Google", CompanyPriority.P1)
    db.commit()

    assert service.get_priority(db, user.id, cloud) == CompanyPriority.P1
    assert service.get_priority(db, user.id, googly) == CompanyPriority.P2  # not a whole-word prefix


def test_priority_prefers_the_more_specific_preference(db: Session, user) -> None:
    cloud = service.get_or_create_company(db, "Google Cloud")
    service.upsert_preference(db, user.id, "Google", CompanyPriority.AVOID)
    service.upsert_preference(db, user.id, "Google Cloud", CompanyPriority.P1)
    db.commit()
    assert service.get_priority(db, user.id, cloud) == CompanyPriority.P1


def test_priority_resolves_avoid(db: Session, user) -> None:
    company = service.get_or_create_company(db, "Shady Consulting Services")
    service.upsert_preference(db, user.id, "Shady Consulting", CompanyPriority.AVOID)
    db.commit()
    assert service.get_priority(db, user.id, company) == CompanyPriority.AVOID


def test_priority_map_bulk(db: Session, user) -> None:
    google = service.get_or_create_company(db, "Google")
    other = service.get_or_create_company(db, "Other Corp")
    service.upsert_preference(db, user.id, "Google", CompanyPriority.P1)
    db.commit()

    mapping = service.get_priority_map(db, user.id, [google, other])
    assert mapping == {google.id: CompanyPriority.P1, other.id: CompanyPriority.P2}


# --------------------------------------------------------------------------- blacklist


def test_blacklist_company_skips_open_applications(db: Session, user) -> None:
    company = service.get_or_create_company(db, "Shady Corp")
    queued = _make_application(db, user.id, _make_job(db, company, "Backend Engineer"), ApplicationStatus.QUEUED)
    discovered = _make_application(db, user.id, _make_job(db, company, "Frontend Engineer"), ApplicationStatus.DISCOVERED)
    running = _make_application(db, user.id, _make_job(db, company, "Platform Engineer"), ApplicationStatus.IN_PROGRESS)
    applied = _make_application(db, user.id, _make_job(db, company, "Staff Engineer"), ApplicationStatus.APPLIED)

    other_company = service.get_or_create_company(db, "Nice Corp")
    untouched = _make_application(db, user.id, _make_job(db, other_company), ApplicationStatus.QUEUED)
    db.commit()

    preference = service.blacklist_company(db, user.id, company.id)
    db.commit()

    assert preference.priority == CompanyPriority.AVOID
    assert service.get_priority(db, user.id, company) == CompanyPriority.AVOID

    db.expire_all()
    for application in (queued, discovered, running):
        db.refresh(application)
        assert application.status == ApplicationStatus.SKIPPED
        assert application.skipped_reason == "Company blacklisted"

    db.refresh(applied)
    assert applied.status == ApplicationStatus.APPLIED  # already sent, left alone
    db.refresh(untouched)
    assert untouched.status == ApplicationStatus.QUEUED

    events = db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == queued.id)).all()
    assert len(events) == 1
    assert events[0].to_status == ApplicationStatus.SKIPPED
    assert events[0].actor.value == "USER"


def test_blacklist_unknown_company_is_404(db: Session, user) -> None:
    from app.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        service.blacklist_company(db, user.id, uuid.uuid4())


# --------------------------------------------------------------------------- endpoints


def test_list_companies_with_counts_and_filters(auth_client: TestClient, db: Session) -> None:
    me = db.scalars(select(User)).one()
    google = service.get_or_create_company(db, "Google")
    zoho = service.get_or_create_company(db, "Zoho Corp")
    _make_job(db, google, "Software Engineer")
    _make_job(db, google, "Backend Engineer")
    inactive = _make_job(db, google, "Closed Role", is_active=False)
    zoho_job = _make_job(db, zoho, "Support Engineer")
    _make_application(db, me.id, inactive, ApplicationStatus.APPLIED)
    _make_application(db, me.id, zoho_job, ApplicationStatus.QUEUED)
    db.commit()

    auth_client.post(PREFERENCES, json={"company_name": "Google", "priority": "P1"})

    response = auth_client.get(COMPANIES)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    by_name = {item["name"]: item for item in body["items"]}
    assert by_name["Google"]["priority"] == "P1"
    assert by_name["Google"]["open_jobs"] == 2
    assert by_name["Google"]["applications"] == 1
    assert by_name["Zoho Corp"]["priority"] == "P2"
    assert by_name["Zoho Corp"]["open_jobs"] == 1

    assert auth_client.get(COMPANIES, params={"q": "zoho"}).json()["total"] == 1
    assert auth_client.get(COMPANIES, params={"priority": "P1"}).json()["total"] == 1
    assert auth_client.get(COMPANIES, params={"priority": "AVOID"}).json()["total"] == 0

    detail = auth_client.get(f"{COMPANIES}/{google.id}")
    assert detail.status_code == 200
    assert detail.json()["priority"] == "P1"
    assert detail.json()["open_jobs"] == 2


def test_company_detail_404(auth_client: TestClient) -> None:
    assert auth_client.get(f"{COMPANIES}/{uuid.uuid4()}").status_code == 404


def test_preferences_crud(auth_client: TestClient) -> None:
    assert auth_client.get(PREFERENCES).json() == []

    replaced = auth_client.put(
        PREFERENCES,
        json={
            "items": [
                {"company_name": "Google", "priority": "P1"},
                {"company_name": "Microsoft Corporation", "priority": "P1", "notes": "Bangalore team"},
                {"company_name": "Shady Corp", "priority": "AVOID"},
            ]
        },
    )
    assert replaced.status_code == 200, replaced.text
    assert len(replaced.json()) == 3
    normalized = {item["normalized_name"] for item in replaced.json()}
    assert normalized == {"google", "microsoft", "shady"}

    # PUT replaces the whole list
    second = auth_client.put(PREFERENCES, json={"items": [{"company_name": "Google", "priority": "P3"}]})
    assert [item["priority"] for item in second.json()] == ["P3"]

    # POST upserts a single row
    created = auth_client.post(PREFERENCES, json={"company_name": "Amazon", "priority": "P1"})
    assert created.status_code == 200, created.text
    assert created.json()["priority"] == "P1"
    updated = auth_client.post(PREFERENCES, json={"company_name": "amazon ltd", "priority": "P3", "notes": "maybe"})
    assert updated.json()["id"] == created.json()["id"]
    assert updated.json()["priority"] == "P3"
    assert updated.json()["notes"] == "maybe"

    assert len(auth_client.get(PREFERENCES).json()) == 2
    deleted = auth_client.delete(f"{PREFERENCES}/{created.json()['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert len(auth_client.get(PREFERENCES).json()) == 1
    assert auth_client.delete(f"{PREFERENCES}/{uuid.uuid4()}").status_code == 404


def test_preferences_validation(auth_client: TestClient) -> None:
    assert auth_client.post(PREFERENCES, json={"company_name": "", "priority": "P1"}).status_code == 422
    assert auth_client.post(PREFERENCES, json={"company_name": "A" * 256, "priority": "P1"}).status_code == 422
    assert auth_client.post(PREFERENCES, json={"company_name": "Google", "priority": "P9"}).status_code == 422
    assert auth_client.post(PREFERENCES, json={"company_name": "   ", "priority": "P1"}).status_code == 422


def test_preferences_are_scoped_to_the_user(auth_client: TestClient, db: Session, user) -> None:
    auth_client.post(PREFERENCES, json={"company_name": "Google", "priority": "P1"})
    assert service.list_user_preferences(db, user.id) == []


def test_companies_endpoints_require_auth(client: TestClient) -> None:
    assert client.get(COMPANIES).status_code == 401
    assert client.get(PREFERENCES).status_code == 401
    assert client.post(PREFERENCES, json={"company_name": "Google", "priority": "P1"}).status_code == 401


def test_blacklist_endpoint(auth_client: TestClient, db: Session) -> None:
    company = service.get_or_create_company(db, "Shady Corp")
    db.commit()

    response = auth_client.post(f"{COMPANIES}/{company.id}/blacklist")
    assert response.status_code == 200, response.text
    assert response.json()["priority"] == "AVOID"
    assert auth_client.get(f"{COMPANIES}/{company.id}").json()["priority"] == "AVOID"
