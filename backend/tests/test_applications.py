"""Applications module tests (CONTRACTS.md section 11).

The full human-in-the-loop journey on SQLite + the mock LLM + a mock EASY_APPLY
adapter: queue -> start -> answers -> blocked approval -> user answer -> approve ->
APPLIED, plus the safety rails (AVOID companies, sensitive questions) and the manual
status path that creates an interview.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.company import Company
from app.models.enums import (
    AnswerSource,
    AnswerStatus,
    ApplicationStatus,
    ApplicationType,
    AutomationState,
    JobSourceType,
    PauseReason,
    WorkMode,
)
from app.models.interview import Interview
from app.models.job import Job, JobSource
from app.models.user import User
from app.modules.adapters.mock.base_mock import stable_int

API = "/api/v1/applications"
JOBS_API = "/api/v1/jobs"

PROFILE = {
    "full_name": "Aarav Sharma",
    "first_name": "Aarav",
    "last_name": "Sharma",
    "email": "aarav.sharma@example.com",
    "phone": "+91 98765 43210",
    "city": "Bangalore",
    "country": "India",
    "linkedin_url": "https://linkedin.com/in/aaravsharma",
    "github_url": "https://github.com/aaravsharma",
    "portfolio_url": "https://aarav.dev",
    "headline": "Full Stack Engineer",
    "current_designation": "Software Engineer",
    "current_company": "Northwind Labs",
    "years_of_experience": 2.0,
    "current_salary": 800000,
    "skills": ["React", "Node.js", "TypeScript", "PostgreSQL", "Docker"],
    "skill_experience": {"React": 2, "Node.js": 2},
    "work_authorization": {"IN": True},
    "requires_sponsorship": False,
}


# --------------------------------------------------------------------------- helpers


def current_user(client: TestClient, db: Session) -> User:
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    return db.get(User, uuid.UUID(me.json()["id"]))


def easy_apply_external_id(seed: str = "li-easy") -> str:
    """A unique mock external id whose deterministic subset asks no custom question."""
    for _ in range(200):
        candidate = f"{seed}-{uuid.uuid4().hex[:10]}"
        if stable_int(candidate) % 7 != 0:
            return candidate
    raise AssertionError("no deterministic easy-apply id found")  # pragma: no cover


def make_job(
    db: Session,
    *,
    company_name: str = "Northwind Labs",
    title: str = "Full Stack Engineer",
    source: JobSourceType = JobSourceType.LINKEDIN,
    application_type: ApplicationType = ApplicationType.EASY_APPLY,
    external_id: str | None = None,
) -> Job:
    from app.modules.companies.service import normalize_company_name

    company = db.scalars(select(Company).where(Company.name == company_name)).first()
    if company is None:
        company = Company(
            name=company_name,
            normalized_name=normalize_company_name(company_name),
            domain=f"{company_name.lower().replace(' ', '')}.dev",
        )
        db.add(company)
        db.flush()
    now = datetime.now(timezone.utc)
    job = Job(
        company_id=company.id,
        title=title,
        normalized_title=title.lower(),
        description="Build React and Node.js products on AWS with PostgreSQL.",
        location="Bangalore, India",
        normalized_location="bangalore",
        work_mode=WorkMode.HYBRID,
        salary_min=1200000,
        salary_max=1800000,
        salary_currency="INR",
        experience_min=1.0,
        experience_max=4.0,
        required_skills=["React", "Node.js", "TypeScript"],
        preferred_skills=["Docker"],
        posted_at=now - timedelta(hours=5),
        canonical_url=f"https://example.test/jobs/{uuid.uuid4().hex[:8]}",
        apply_url=f"https://example.test/apply/{uuid.uuid4().hex[:8]}",
        application_type=application_type,
        dedupe_hash=uuid.uuid4().hex,
    )
    db.add(job)
    db.flush()
    db.add(
        JobSource(
            job_id=job.id,
            source=source,
            external_id=external_id or easy_apply_external_id(),
            url=job.canonical_url,
            apply_url=job.apply_url,
            application_type=application_type,
            posted_at=job.posted_at,
            discovered_at=now,
            last_seen_at=now,
        )
    )
    db.commit()
    return job


def set_profile(client: TestClient, **overrides) -> None:
    payload = dict(PROFILE)
    payload.update(overrides)
    r = client.put("/api/v1/profile", json=payload)
    assert r.status_code == 200, r.text


def set_preferences(client: TestClient, **payload) -> None:
    r = client.put("/api/v1/preferences/job", json=payload)
    assert r.status_code == 200, r.text


def upload_resume(client: TestClient) -> str:
    from tests.helpers import SAMPLE_RESUME_TEXT, build_pdf

    r = client.post(
        "/api/v1/resumes",
        files={"file": ("aarav.pdf", build_pdf(SAMPLE_RESUME_TEXT), "application/pdf")},
        data={"name": "Full Stack", "set_default": "true"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def answers_by_key(client: TestClient, application_id: str) -> dict[str, dict]:
    r = client.get(f"{API}/{application_id}")
    assert r.status_code == 200, r.text
    return {a["question_key"]: a for a in r.json()["answers"]}


@pytest.fixture(autouse=True)
def _reset_executor():
    from app.modules.applications import executor

    executor.reset()
    yield
    executor.reset()


@pytest.fixture
def ready_client(auth_client: TestClient) -> TestClient:
    """Logged-in client with a complete profile, preferences and a default resume."""
    set_profile(auth_client)
    set_preferences(auth_client, notice_period_days=30, currency="INR", min_match_score=40)
    upload_resume(auth_client)
    return auth_client


# --------------------------------------------------------------------------- queueing


def test_queue_job_is_idempotent_and_sets_source(ready_client: TestClient, db: Session):
    job = make_job(db)
    first = ready_client.post(f"{JOBS_API}/{job.id}/queue")
    assert first.status_code in (200, 201), first.text
    second = ready_client.post(f"{JOBS_API}/{job.id}/queue")
    assert second.status_code in (200, 201), second.text
    assert first.json()["id"] == second.json()["id"]

    db.expire_all()
    rows = db.scalars(select(Application).where(Application.job_id == job.id)).all()
    assert len(rows) == 1
    application = rows[0]
    assert application.status == ApplicationStatus.QUEUED
    assert application.source == JobSourceType.LINKEDIN
    assert application.queue_position == 1
    assert application.match_score is not None


def test_avoid_company_cannot_be_queued(ready_client: TestClient, db: Session):
    job = make_job(db, company_name="Avoidco Systems")
    r = ready_client.post("/api/v1/companies/preferences", json={"company_name": "Avoidco Systems", "priority": "AVOID"})
    assert r.status_code in (200, 201), r.text

    queued = ready_client.post(f"{JOBS_API}/{job.id}/queue")
    assert queued.status_code == 409, queued.text
    assert queued.json()["error"]["message"] == "Company is on your avoid list"

    db.expire_all()
    assert db.scalars(select(Application).where(Application.job_id == job.id)).first() is None


def test_queue_endpoint_orders_by_priority_then_score(ready_client: TestClient, db: Session):
    low = make_job(db, company_name="Small Startup", title="Backend Engineer")
    top = make_job(db, company_name="Google", title="Software Engineer")
    ready_client.put(
        "/api/v1/companies/preferences",
        json={"items": [{"company_name": "Google", "priority": "P1"}, {"company_name": "Small Startup", "priority": "P3"}]},
    )
    for job in (low, top):
        assert ready_client.post(f"{JOBS_API}/{job.id}/queue").status_code in (200, 201)

    r = ready_client.get(f"{API}/queue")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [item["application"]["priority"] for item in items] == ["P1", "P3"]
    assert items[0]["position"] == 1
    assert items[0]["job"]["title"] == "Software Engineer"
    assert items[0]["application"]["company_name"] == "Google"


# --------------------------------------------------------------------------- the journey


def test_full_easy_apply_journey(ready_client: TestClient, db: Session):
    """queue -> start -> answers -> blocked approve -> user answer -> approve -> APPLIED."""
    job = make_job(db)
    queued = ready_client.post(f"{JOBS_API}/{job.id}/queue")
    assert queued.status_code in (200, 201), queued.text
    application_id = queued.json()["id"]

    started = ready_client.post(f"{API}/{application_id}/start", json={"run_in_background": False})
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["status"] == ApplicationStatus.IN_PROGRESS.value

    detail = ready_client.get(f"{API}/{application_id}").json()
    assert detail["automation_state"] == AutomationState.PAUSED.value
    assert detail["pause_reason"] == PauseReason.USER_REVIEW.value
    assert detail["form_snapshot"]["fields"]

    answers = {a["question_key"]: a for a in detail["answers"]}
    # Facts that exist on the profile are answered from it, never by the LLM.
    assert answers["full_name"]["status"] == AnswerStatus.ANSWERED.value
    assert answers["full_name"]["answer_source"] == AnswerSource.PROFILE.value
    assert answers["full_name"]["confidence"] == 1.0
    assert answers["full_name"]["rationale"].startswith("From profile:")
    assert answers["phone"]["answer"] == PROFILE["phone"]
    assert answers["years_of_experience"]["answer"] == "2"
    assert answers["notice_period_days"]["answer_source"] == AnswerSource.PREFERENCE.value
    assert answers["resume_file"]["status"] == AnswerStatus.ANSWERED.value
    assert answers["resume_file"]["answer"].endswith(".pdf")

    # ... and the one nobody told us about is handed back to the user.
    assert answers["expected_salary"]["status"] == AnswerStatus.NEEDS_USER_INPUT.value
    assert answers["expected_salary"]["answer"] is None

    # The review refuses to submit while a required answer is missing.
    review = ready_client.get(f"{API}/{application_id}/review").json()
    assert review["can_submit"] is False
    assert any("Expected" in blocker for blocker in review["blockers"])

    blocked = ready_client.post(f"{API}/{application_id}/approve")
    assert blocked.status_code == 422, blocked.text
    assert blocked.json()["error"]["code"] == "review_blocked"

    # The user answers it.
    saved = ready_client.put(
        f"{API}/{application_id}/answers",
        json={"answers": [{"id": answers["expected_salary"]["id"], "answer": "1400000"}]},
    )
    assert saved.status_code == 200, saved.text
    updated = {a["question_key"]: a for a in saved.json()}
    assert updated["expected_salary"]["status"] == AnswerStatus.ANSWERED.value
    assert updated["expected_salary"]["answer_source"] == AnswerSource.USER.value

    approved = ready_client.post(f"{API}/{application_id}/approve")
    assert approved.status_code == 200, approved.text
    result = approved.json()
    assert result["status"] == ApplicationStatus.APPLIED.value
    assert result["automation_state"] == AutomationState.SUCCESS.value
    assert result["applied_at"] is not None
    assert result["approved_at"] is not None
    assert result["external_application_id"]
    assert result["submitted_via"] == "AUTOMATION"

    # Event trail.
    events = ready_client.get(f"{API}/{application_id}/events").json()
    types = [event["event_type"] for event in events]
    for expected in ("CREATED", "STATUS_CHANGED", "ANSWERS_GENERATED", "FORM_FILLED", "PAUSED", "APPROVED", "SUBMITTED"):
        assert expected in types, f"{expected} missing from {types}"

    # Notifications.
    notifications = ready_client.get("/api/v1/notifications").json()["items"]
    titles = [n["title"] for n in notifications]
    kinds = {n["type"] for n in notifications}
    assert "Application ready for review" in titles
    assert "APPLICATION_SUBMITTED" in kinds

    # Audit trail.
    logs = ready_client.get("/api/v1/audit", params={"application_id": application_id, "page_size": 100}).json()["items"]
    actions = {row["action"] for row in logs}
    for expected in (
        "application.created",
        "application.answers_generated",
        "application.form_detected",
        "application.field_filled",
        "application.approved",
        "application.submitted",
    ):
        assert expected in actions, f"{expected} missing from {sorted(actions)}"


def test_expected_salary_is_answered_once_the_preference_exists(ready_client: TestClient, db: Session):
    set_preferences(ready_client, notice_period_days=30, desired_salary=1500000, currency="INR")
    job = make_job(db, title="Senior Full Stack Engineer")
    application_id = ready_client.post(f"{JOBS_API}/{job.id}/queue").json()["id"]

    regenerated = ready_client.post(f"{API}/{application_id}/answers/generate")
    assert regenerated.status_code == 200, regenerated.text
    rows = {a["question_key"]: a for a in regenerated.json()}
    assert rows["expected_salary"]["status"] == AnswerStatus.ANSWERED.value
    assert rows["expected_salary"]["answer"] == "1500000"
    assert rows["expected_salary"]["answer_source"] == AnswerSource.PREFERENCE.value


def test_user_answers_survive_regeneration(ready_client: TestClient, db: Session):
    job = make_job(db, title="Platform Engineer")
    application_id = ready_client.post(f"{JOBS_API}/{job.id}/queue").json()["id"]
    ready_client.post(f"{API}/{application_id}/answers/generate")

    rows = answers_by_key(ready_client, application_id)
    ready_client.put(
        f"{API}/{application_id}/answers",
        json={"answers": [{"id": rows["expected_salary"]["id"], "answer": "2222222"}]},
    )
    ready_client.post(f"{API}/{application_id}/answers/generate")

    rows = answers_by_key(ready_client, application_id)
    assert rows["expected_salary"]["answer"] == "2222222"
    assert rows["expected_salary"]["answer_source"] == AnswerSource.USER.value


# --------------------------------------------------------------------------- safety rails


def test_sensitive_question_is_never_ai_generated(ready_client: TestClient, db: Session):
    """Work authorization comes from the profile or not at all."""
    set_profile(ready_client, work_authorization={})
    job = make_job(
        db,
        company_name="Acme Cloud",
        title="Backend Engineer",
        source=JobSourceType.GREENHOUSE,
        application_type=ApplicationType.ATS_FORM,
        external_id="gh-ats-1",
    )
    application_id = ready_client.post(f"{JOBS_API}/{job.id}/queue").json()["id"]
    rows = {a["question_key"]: a for a in ready_client.post(f"{API}/{application_id}/answers/generate").json()}

    authorization = rows["work_authorization"]
    assert authorization["is_sensitive"] is True
    assert authorization["status"] == AnswerStatus.NEEDS_USER_INPUT.value
    assert authorization["answer_source"] != AnswerSource.AI_GENERATED.value
    assert authorization["answer"] is None

    # A free-text motivation question, by contrast, may be composed by the AI.
    assert rows["custom:why_us"]["status"] == AnswerStatus.ANSWERED.value
    assert rows["custom:why_us"]["answer_source"] == AnswerSource.AI_GENERATED.value

    # With the fact on file it is answered from the profile - still not by the AI.
    set_profile(ready_client, work_authorization={"IN": True})
    rows = {a["question_key"]: a for a in ready_client.post(f"{API}/{application_id}/answers/generate").json()}
    assert rows["work_authorization"]["status"] == AnswerStatus.ANSWERED.value
    assert rows["work_authorization"]["answer"] == "Yes"
    assert rows["work_authorization"]["answer_source"] == AnswerSource.PROFILE.value


def test_applications_are_scoped_to_their_owner(ready_client: TestClient, db: Session, client: TestClient):
    job = make_job(db, title="Scoped Engineer")
    application_id = ready_client.post(f"{JOBS_API}/{job.id}/queue").json()["id"]

    other = client.post(
        "/api/v1/auth/register",
        json={"email": "intruder@example.com", "password": "StrongPass123!", "full_name": "Intruder"},
    )
    assert other.status_code in (200, 201), other.text
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.get(f"{API}/{application_id}", headers=headers).status_code == 404
    assert client.patch(f"{API}/{application_id}/status", json={"status": "APPLIED"}, headers=headers).status_code == 404


# --------------------------------------------------------------------------- status changes


def test_manual_status_to_interview_creates_an_interview(ready_client: TestClient, db: Session):
    job = make_job(db, title="Data Engineer")
    application_id = ready_client.post(f"{JOBS_API}/{job.id}/queue").json()["id"]

    r = ready_client.patch(f"{API}/{application_id}/status", json={"status": "INTERVIEW", "note": "Recruiter called"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == ApplicationStatus.INTERVIEW.value
    assert r.json()["last_response_at"] is not None

    db.expire_all()
    interviews = db.scalars(select(Interview).where(Interview.application_id == uuid.UUID(application_id))).all()
    assert len(interviews) == 1
    assert interviews[0].status.value == "SCHEDULED"
    assert interviews[0].scheduled_at is None

    notifications = ready_client.get("/api/v1/notifications").json()["items"]
    assert "INTERVIEW_SCHEDULED" in {n["type"] for n in notifications}

    # A second manual change must not create a duplicate round.
    ready_client.patch(f"{API}/{application_id}/status", json={"status": "APPLIED"})
    ready_client.patch(f"{API}/{application_id}/status", json={"status": "INTERVIEW"})
    db.expire_all()
    assert db.scalars(select(Interview).where(Interview.application_id == uuid.UUID(application_id))).all().__len__() == 1


def test_terminal_status_needs_a_manual_actor(ready_client: TestClient, db: Session):
    from app.core.exceptions import ConflictError
    from app.modules.applications import service

    job = make_job(db, title="Rejected Engineer")
    application_id = ready_client.post(f"{JOBS_API}/{job.id}/queue").json()["id"]
    ready_client.patch(f"{API}/{application_id}/status", json={"status": "REJECTED"})

    db.expire_all()
    application = db.get(Application, uuid.UUID(application_id))
    from app.models.enums import Actor

    with pytest.raises(ConflictError):
        service.transition(db, application, ApplicationStatus.INTERVIEW, actor=Actor.AUTOMATION)
    db.rollback()

    # The user may still move it by hand.
    assert ready_client.patch(f"{API}/{application_id}/status", json={"status": "INTERVIEW"}).status_code == 200


def test_submission_never_walks_a_status_backwards(ready_client: TestClient, db: Session):
    """Regression: an ATS confirmation email can land while the submission is still running.

    ``linker.LINKABLE_STATUSES`` deliberately accepts IN_PROGRESS applications, so by the time
    ``mark_submitted`` runs the application may already be APPLICATION_RECEIVED - recording the
    submission must not drag it back to APPLIED.
    """
    from app.modules.applications import service

    job = make_job(db, title="Race Engineer")
    application_id = ready_client.post(f"{JOBS_API}/{job.id}/queue").json()["id"]
    ready_client.patch(f"{API}/{application_id}/status", json={"status": "APPLICATION_RECEIVED"})

    db.expire_all()
    application = db.get(Application, uuid.UUID(application_id))
    assert application.status == ApplicationStatus.APPLICATION_RECEIVED

    service.mark_submitted(
        db,
        application,
        external_application_id="DEMO-ABC123",
        confirmation_message="Thank you for applying",
    )
    db.flush()

    assert application.status == ApplicationStatus.APPLICATION_RECEIVED, "the email's status must win"
    assert application.external_application_id == "DEMO-ABC123"
    assert application.applied_at is not None
    assert application.automation_state == AutomationState.SUCCESS

    # ...while the normal path still moves a queued application to APPLIED.
    other = make_job(db, title="Plain Engineer", external_id="li-plain")
    other_id = ready_client.post(f"{JOBS_API}/{other.id}/queue").json()["id"]
    db.expire_all()
    plain = db.get(Application, uuid.UUID(other_id))
    service.mark_submitted(db, plain, external_application_id="DEMO-XYZ789")
    db.flush()
    assert plain.status == ApplicationStatus.APPLIED


def test_skip_and_withdraw(ready_client: TestClient, db: Session):
    job = make_job(db, title="Skipped Engineer")
    application_id = ready_client.post(f"{JOBS_API}/{job.id}/queue").json()["id"]

    skipped = ready_client.post(f"{API}/{application_id}/skip", json={"reason": "Not interested"})
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["status"] == ApplicationStatus.SKIPPED.value
    assert skipped.json()["skipped_reason"] == "Not interested"
    assert skipped.json()["queue_position"] is None

    withdrawn = ready_client.post(f"{API}/{application_id}/withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == ApplicationStatus.WITHDRAWN.value


# --------------------------------------------------------------------------- misc endpoints


def test_cover_letter_and_patch_and_summaries(ready_client: TestClient, db: Session):
    job = make_job(db, title="Cover Letter Engineer")
    application_id = ready_client.post(f"{JOBS_API}/{job.id}/queue").json()["id"]

    generated = ready_client.post(f"{API}/{application_id}/cover-letter")
    assert generated.status_code == 200, generated.text
    assert len(generated.json()["cover_letter"].split()) <= 250
    assert "Northwind Labs" in generated.json()["cover_letter"]

    saved = ready_client.put(f"{API}/{application_id}/cover-letter", json={"content": "My own words."})
    assert saved.json()["cover_letter"] == "My own words."

    patched = ready_client.patch(f"{API}/{application_id}", json={"notes": "Referred by Meera", "next_action": "Follow up"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["notes"] == "Referred by Meera"

    listed = ready_client.get(API, params={"q": "Cover Letter"}).json()
    assert listed["total"] == 1
    assert listed["items"][0]["job_title"] == "Cover Letter Engineer"
    assert listed["items"][0]["company_name"] == "Northwind Labs"

    ready_client.post(f"{API}/{application_id}/answers/generate")
    summary = ready_client.get(f"{API}/review-summary").json()
    assert summary["requires_input"] >= 1
    assert set(summary) == {"pending_review", "requires_input", "ready_to_submit"}


def test_start_refuses_a_second_concurrent_run(ready_client: TestClient, db: Session):
    from app.core.exceptions import ConflictError
    from app.modules.applications import executor, service

    job = make_job(db, title="Busy Engineer")
    application_id = uuid.UUID(ready_client.post(f"{JOBS_API}/{job.id}/queue").json()["id"])
    user = current_user(ready_client, db)

    executor._claim(application_id, __import__("threading").current_thread())
    try:
        with pytest.raises(ConflictError):
            service.start_application(db, application_id, user.id, run_in_background=False)
    finally:
        executor.reset()
