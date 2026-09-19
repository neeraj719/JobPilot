"""``ApplicationRunner`` against the mock (browser-free) adapters - CONTRACTS.md section 12.

These cover the four ways a run can end without needing Chromium: pause for the user,
pause for review, auto-submit where it is explicitly enabled, and failure.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.automation import AutomationConfig
from app.models.company import Company
from app.models.enums import (
    AnswerSource,
    AnswerStatus,
    ApplicationStatus,
    ApplicationType,
    AutomationState,
    JobSourceType,
    NotificationType,
    PauseReason,
    ResumeParseStatus,
    WorkMode,
)
from app.models.job import Job, JobSource
from app.models.notification import Notification
from app.models.resume import Resume
from app.models.profile import JobPreference, UserProfile
from app.models.user import User
from app.core.config import settings
from app.core.security import hash_password
from app.modules.adapters.base import ApplyStepResult
from app.modules.adapters.mock.base_mock import BaseMockAdapter, stable_int
from app.modules.applications import executor, service
from app.modules.browser.runner import ApplicationRunner, snapshot_summary


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _reset_executor():
    executor.reset()
    yield
    executor.reset()


@pytest.fixture
def user(db: Session) -> User:
    row = User(email="runner@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Runner Tester")
    db.add(row)
    db.flush()
    db.add(
        UserProfile(
            user_id=row.id,
            full_name="Runner Tester",
            first_name="Runner",
            last_name="Tester",
            email="runner@example.com",
            phone="+91 90000 00000",
            city="Bangalore",
            country="India",
            linkedin_url="https://linkedin.com/in/runner",
            current_company="Northwind Labs",
            current_designation="Software Engineer",
            years_of_experience=2.0,
            current_salary=800000,
            skills=["React", "Node.js", "TypeScript"],
            skill_experience={"React": 2},
            work_authorization={"IN": True},
            requires_sponsorship=False,
        )
    )
    db.add(JobPreference(user_id=row.id, currency="INR", notice_period_days=30, desired_salary=1400000, min_match_score=0))
    db.add(_resume_for(row))
    db.add(
        AutomationConfig(
            user_id=row.id,
            retry_limit=2,
            auto_submit_enabled=False,
            auto_submit_sources=[],
            auto_generate_cover_letters=False,
        )
    )
    db.commit()
    return row


def _resume_for(row: User) -> Resume:
    """A real (tiny) PDF on disk so the resume upload field can actually be answered."""
    from tests.helpers import SAMPLE_RESUME_TEXT, build_pdf

    folder = Path(settings.UPLOAD_DIR) / "resumes" / str(row.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}.pdf"
    payload = build_pdf(SAMPLE_RESUME_TEXT)
    path.write_bytes(payload)
    return Resume(
        user_id=row.id,
        name="Full Stack",
        is_default=True,
        file_path=str(path),
        original_filename="runner.pdf",
        mime_type="application/pdf",
        size_bytes=len(payload),
        parse_status=ResumeParseStatus.PARSED,
        parsed_data={"skills": ["React", "Node.js"], "total_experience_years": 2.0},
    )


def external_id(requires_user: bool, seed: str = "mock") -> str:
    """A deterministic mock id in (or out of) the "asks a custom question" subset."""
    for _ in range(500):
        candidate = f"{seed}-{uuid.uuid4().hex[:10]}"
        if (stable_int(candidate) % 7 == 0) is requires_user:
            return candidate
    raise AssertionError("no matching deterministic id found")  # pragma: no cover


def make_job(db: Session, *, source: JobSourceType = JobSourceType.LINKEDIN, requires_user: bool = False, title: str = "Full Stack Engineer") -> Job:
    company = db.scalars(select(Company).where(Company.name == "Northwind Labs")).first()
    if company is None:
        company = Company(name="Northwind Labs", normalized_name="northwind", domain="northwindlabs.dev")
        db.add(company)
        db.flush()
    now = datetime.now(timezone.utc)
    job = Job(
        company_id=company.id,
        title=title,
        normalized_title=title.lower(),
        description="React and Node.js work.",
        location="Bangalore, India",
        work_mode=WorkMode.HYBRID,
        required_skills=["React", "Node.js"],
        posted_at=now - timedelta(hours=2),
        canonical_url=f"https://example.test/jobs/{uuid.uuid4().hex[:8]}",
        apply_url=f"https://example.test/apply/{uuid.uuid4().hex[:8]}",
        application_type=ApplicationType.EASY_APPLY,
        dedupe_hash=uuid.uuid4().hex,
    )
    db.add(job)
    db.flush()
    db.add(
        JobSource(
            job_id=job.id,
            source=source,
            external_id=external_id(requires_user),
            url=job.canonical_url,
            apply_url=job.apply_url,
            application_type=ApplicationType.EASY_APPLY,
            discovered_at=now,
            last_seen_at=now,
        )
    )
    db.commit()
    return job


def notifications(db: Session, user: User) -> list[Notification]:
    return list(db.scalars(select(Notification).where(Notification.user_id == user.id)).all())


# --------------------------------------------------------------------------- happy path


def test_runner_pauses_for_review_when_the_form_is_complete(db: Session, user: User):
    job = make_job(db)
    application = service.queue_job(db, user.id, job.id)
    db.commit()

    service.start_application(db, application.id, user.id, run_in_background=False)
    db.expire_all()
    application = db.get(Application, application.id)

    assert application.automation_state == AutomationState.PAUSED
    assert application.pause_reason == PauseReason.USER_REVIEW
    assert application.status == ApplicationStatus.IN_PROGRESS
    assert application.form_snapshot["fields"]
    assert application.applied_at is None

    detected, filled = snapshot_summary(application.form_snapshot)
    assert "full_name" in detected
    assert "email" in filled

    titles = {n.title for n in notifications(db, user)}
    assert "Application ready for review" in titles
    assert NotificationType.SYSTEM in {n.type for n in notifications(db, user)}


def test_runner_never_submits_without_approval_or_auto_submit(db: Session, user: User):
    job = make_job(db)
    application = service.queue_job(db, user.id, job.id)
    db.commit()
    service.start_application(db, application.id, user.id, run_in_background=False)
    db.expire_all()

    application = db.get(Application, application.id)
    assert application.status != ApplicationStatus.APPLIED
    assert application.external_application_id is None


# --------------------------------------------------------------------------- pausing


def test_runner_pauses_on_an_unanswerable_question_and_records_it(db: Session, user: User):
    job = make_job(db, requires_user=True, title="Site Reliability Engineer")
    application = service.queue_job(db, user.id, job.id)
    db.commit()

    service.start_application(db, application.id, user.id, run_in_background=False)
    db.expire_all()
    application = db.get(Application, application.id)

    assert application.automation_state == AutomationState.REQUIRES_USER
    assert application.pause_reason == PauseReason.UNKNOWN_QUESTION
    assert application.pause_message

    custom = [a for a in application.answers if a.question_key.startswith("custom:")]
    assert custom, "the paused question must become an answer row the user can fill in"
    assert all(a.status == AnswerStatus.NEEDS_USER_INPUT for a in custom)
    assert all(a.answer_source != AnswerSource.AI_GENERATED for a in custom)

    assert NotificationType.INPUT_REQUIRED in {n.type for n in notifications(db, user)}

    # The user answers it and resumes - now the form is complete.
    service.resume_automation(
        db,
        application,
        [{"id": custom[0].id, "answer": "1 December 2026"}],
        run_in_background=False,
    )
    db.expire_all()
    application = db.get(Application, application.id)
    assert application.automation_state == AutomationState.PAUSED
    assert application.pause_reason == PauseReason.USER_REVIEW


# --------------------------------------------------------------------------- auto-submit


def test_auto_submit_only_when_enabled_for_that_source(db: Session, user: User):
    job = make_job(db, title="Auto Submit Engineer")
    config = db.scalars(select(AutomationConfig).where(AutomationConfig.user_id == user.id)).first()
    config.auto_submit_enabled = True
    config.auto_submit_sources = ["LINKEDIN"]
    application = service.queue_job(db, user.id, job.id, auto_submit=True)
    db.commit()

    service.start_application(db, application.id, user.id, run_in_background=False)
    db.expire_all()
    application = db.get(Application, application.id)

    assert application.status == ApplicationStatus.APPLIED
    assert application.automation_state == AutomationState.SUCCESS
    assert application.applied_at is not None
    assert application.external_application_id
    assert application.submitted_via == "AUTOMATION"
    assert NotificationType.APPLICATION_SUBMITTED in {n.type for n in notifications(db, user)}


def test_auto_submit_is_refused_for_an_unlisted_source(db: Session, user: User):
    job = make_job(db, title="Unlisted Source Engineer")
    config = db.scalars(select(AutomationConfig).where(AutomationConfig.user_id == user.id)).first()
    config.auto_submit_enabled = True
    config.auto_submit_sources = ["NAUKRI"]  # not this job's source
    application = service.queue_job(db, user.id, job.id, auto_submit=True)
    db.commit()

    service.start_application(db, application.id, user.id, run_in_background=False)
    db.expire_all()
    application = db.get(Application, application.id)
    assert application.status == ApplicationStatus.IN_PROGRESS
    assert application.automation_state == AutomationState.PAUSED


def test_auto_submit_is_refused_while_a_sensitive_answer_is_missing(db: Session, user: User, monkeypatch):
    job = make_job(db, title="Sensitive Question Engineer")
    config = db.scalars(select(AutomationConfig).where(AutomationConfig.user_id == user.id)).first()
    config.auto_submit_enabled = True
    config.auto_submit_sources = ["LINKEDIN"]
    application = service.queue_job(db, user.id, job.id, auto_submit=True)
    db.commit()

    from app.modules.applications.questions import standard_questions

    def _with_sensitive(application_type, *, company_name=None):
        from app.models.enums import FieldType
        from app.modules.applications.questions import FormQuestion

        questions = standard_questions(application_type, company_name=company_name)
        questions.append(
            FormQuestion(
                key="work_authorization",
                text="Are you legally authorized to work in Germany?",
                field_type=FieldType.RADIO,
                options=["Yes", "No"],
            )
        )
        return questions

    monkeypatch.setattr("app.modules.applications.questions.standard_questions", _with_sensitive)
    monkeypatch.setattr("app.modules.applications.answers.questions_for_job", lambda job: _with_sensitive(job.application_type, company_name=job.company.name))

    service.start_application(db, application.id, user.id, run_in_background=False)
    db.expire_all()
    application = db.get(Application, application.id)

    authorization = next(a for a in application.answers if a.question_key == "work_authorization")
    assert authorization.status == AnswerStatus.NEEDS_USER_INPUT
    assert authorization.is_sensitive is True
    assert application.status != ApplicationStatus.APPLIED
    assert application.automation_state in {AutomationState.PAUSED, AutomationState.REQUIRES_USER}


# --------------------------------------------------------------------------- failures


def test_runner_records_a_failed_step_without_raising(db: Session, user: User, monkeypatch):
    job = make_job(db, title="Broken Adapter Engineer")
    application = service.queue_job(db, user.id, job.id)
    db.commit()

    monkeypatch.setattr(
        BaseMockAdapter,
        "start_application",
        lambda self, ctx: ApplyStepResult(state=AutomationState.FAILED, message="The platform is down"),
    )
    service.start_application(db, application.id, user.id, run_in_background=False)
    db.expire_all()
    application = db.get(Application, application.id)

    assert application.automation_state in {AutomationState.FAILED, AutomationState.RETRYING}
    assert "platform is down" in (application.last_error or "")
    assert application.retry_count == 1


def test_runner_absorbs_an_exception_and_audits_it(db: Session, user: User, monkeypatch):
    job = make_job(db, title="Exploding Adapter Engineer")
    application = service.queue_job(db, user.id, job.id)
    db.commit()

    def _boom(self, ctx):
        raise RuntimeError("adapter exploded")

    monkeypatch.setattr(BaseMockAdapter, "fill_application", _boom)
    service.start_application(db, application.id, user.id, run_in_background=False)
    db.expire_all()
    application = db.get(Application, application.id)

    assert application.automation_state == AutomationState.FAILED
    assert "adapter exploded" in (application.last_error or "")

    from app.models.audit import AuditLog

    actions = {
        row.action
        for row in db.scalars(select(AuditLog).where(AuditLog.application_id == application.id)).all()
    }
    assert "application.failed" in actions


def test_temporary_errors_are_retried(db: Session, user: User, monkeypatch):
    job = make_job(db, title="Flaky Network Engineer")
    application = service.queue_job(db, user.id, job.id)
    db.commit()

    calls = {"n": 0}
    original = BaseMockAdapter.fill_application

    def _flaky(self, ctx):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("temporary network blip")
        return original(self, ctx)

    monkeypatch.setattr(BaseMockAdapter, "fill_application", _flaky)
    monkeypatch.setattr("app.modules.browser.runner.RETRY_BACKOFF_SECONDS", 0.0)

    service.start_application(db, application.id, user.id, run_in_background=False)
    db.expire_all()
    application = db.get(Application, application.id)

    assert calls["n"] == 2
    assert application.automation_state == AutomationState.PAUSED
    assert application.retry_count == 1


# --------------------------------------------------------------------------- executor


def test_background_execution_updates_the_application(db: Session, user: User):
    job = make_job(db, title="Background Engineer")
    application = service.queue_job(db, user.id, job.id)
    application_id = application.id
    db.commit()

    service.start_application(db, application_id, user.id, run_in_background=True)
    assert executor.wait_for(application_id, timeout=60) is True

    db.expire_all()
    application = db.get(Application, application_id)
    assert application.automation_state in {AutomationState.PAUSED, AutomationState.SUCCESS}
    assert application.answers


def test_a_second_run_is_refused_while_one_is_in_flight(db: Session, user: User):
    from app.core.exceptions import ConflictError

    job = make_job(db, title="Single Run Engineer")
    application = service.queue_job(db, user.id, job.id)
    db.commit()

    executor._claim(application.id, threading.current_thread())
    try:
        assert executor.is_running(application.id) is True
        with pytest.raises(ConflictError):
            executor.run_now(application.id, db=db)
    finally:
        executor.reset()


def test_missing_application_is_a_no_op(db: Session):
    assert ApplicationRunner(uuid.uuid4(), db=db).run() is None
