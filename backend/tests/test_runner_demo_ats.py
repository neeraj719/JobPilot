"""End-to-end Playwright run against the bundled demo ATS (CONTRACTS.md sections 8/12).

This is the only test that drives a real browser against a real HTTP server: uvicorn
serves the FastAPI app (including ``/demo-ats``) on a free port in a background thread,
and ``ApplicationRunner`` fills the Greenhouse-style form with Chromium.

Marked ``browser`` and skipped automatically when Chromium is not installed.
"""
from __future__ import annotations

import socket
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.demo_ats.catalog import get_demo_job
from app.models.application import Application
from app.models.automation import AutomationConfig
from app.models.company import Company
from app.models.enums import (
    AnswerStatus,
    ApplicationStatus,
    ApplicationType,
    AutomationState,
    JobSourceType,
    PauseReason,
    ResumeParseStatus,
    WorkMode,
)
from app.models.job import Job, JobSource
from app.models.profile import JobPreference, UserProfile
from app.models.resume import Resume
from app.models.user import User
from app.modules.applications import executor, service
from app.modules.browser.session import is_browser_available

pytestmark = pytest.mark.browser

DEMO_SLUG = "northwind-labs-full-stack-engineer"
#: The profile email deliberately differs from the account email so the demo ATS does
#: not try to write a simulated confirmation email from the server thread.
APPLICANT_EMAIL = "aarav.applicant@example.test"


# --------------------------------------------------------------------------- server


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class BackgroundServer:
    """uvicorn running the test app in a thread, so Chromium can reach it."""

    def __init__(self, port: int) -> None:
        import uvicorn

        from app.main import app

        self.port = port
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, name="demo-ats-server", daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout: float = 30.0) -> None:
        self.thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if getattr(self.server, "started", False):
                return
            time.sleep(0.05)
        raise AssertionError("the demo ATS server did not start in time")  # pragma: no cover

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=15)


@pytest.fixture(scope="module")
def demo_server():
    if not is_browser_available():
        pytest.skip("Chromium is not installed (run: python -m playwright install chromium)")
    server = BackgroundServer(free_port())
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture(autouse=True)
def _browser_settings(monkeypatch, demo_server):
    monkeypatch.setattr(settings, "DEMO_ATS_BASE_URL", demo_server.base_url)
    monkeypatch.setattr(settings, "BROWSER_ACTION_DELAY_MS", 0)
    monkeypatch.setattr(settings, "PLAYWRIGHT_HEADLESS", True)
    executor.reset()
    yield
    executor.reset()


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def user(db: Session) -> User:
    row = User(email="demo-ats-runner@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Aarav Sharma")
    db.add(row)
    db.flush()
    db.add(
        UserProfile(
            user_id=row.id,
            full_name="Aarav Sharma",
            first_name="Aarav",
            last_name="Sharma",
            email=APPLICANT_EMAIL,
            phone="+91 98765 43210",
            city="Bangalore",
            country="India",
            linkedin_url="https://linkedin.com/in/aaravsharma",
            github_url="https://github.com/aaravsharma",
            portfolio_url="https://aarav.dev",
            current_company="Northwind Labs",
            current_designation="Software Engineer",
            years_of_experience=2.0,
            current_salary=800000,
            skills=["React", "Node.js", "TypeScript", "PostgreSQL"],
            skill_experience={"React": 2},
            work_authorization={"IN": True},
            requires_sponsorship=False,
        )
    )
    db.add(JobPreference(user_id=row.id, currency="INR", notice_period_days=30, desired_salary=1400000, min_match_score=0))
    db.add(AutomationConfig(user_id=row.id, retry_limit=1, auto_submit_enabled=False, auto_generate_cover_letters=False))

    folder = Path(settings.UPLOAD_DIR) / "resumes" / str(row.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}.pdf"
    from tests.helpers import SAMPLE_RESUME_TEXT, build_pdf

    payload = build_pdf(SAMPLE_RESUME_TEXT)
    path.write_bytes(payload)
    db.add(
        Resume(
            user_id=row.id,
            name="Full Stack",
            is_default=True,
            file_path=str(path),
            original_filename="aarav.pdf",
            mime_type="application/pdf",
            size_bytes=len(payload),
            parse_status=ResumeParseStatus.PARSED,
            parsed_data={"skills": ["React", "Node.js"], "total_experience_years": 2.0},
        )
    )
    db.commit()
    return row


@pytest.fixture
def demo_job(db: Session, demo_server: BackgroundServer) -> Job:
    posting = get_demo_job(DEMO_SLUG)
    assert posting is not None
    company = db.scalars(select(Company).where(Company.name == posting["company"])).first()
    if company is None:
        company = Company(name=posting["company"], normalized_name="northwind", domain=posting["company_domain"])
        db.add(company)
        db.flush()
    now = datetime.now(timezone.utc)
    job = Job(
        company_id=company.id,
        title=posting["title"],
        normalized_title=posting["title"].lower(),
        description=posting["description"],
        location=posting["location"],
        work_mode=WorkMode(posting["work_mode"]),
        salary_min=posting.get("salary_min"),
        salary_max=posting.get("salary_max"),
        salary_currency="INR",
        experience_min=posting.get("experience_min"),
        experience_max=posting.get("experience_max"),
        required_skills=list(posting.get("required_skills") or []),
        preferred_skills=list(posting.get("preferred_skills") or []),
        posted_at=now - timedelta(hours=4),
        canonical_url=f"{demo_server.base_url}/demo-ats/jobs/{DEMO_SLUG}",
        apply_url=f"{demo_server.base_url}/demo-ats/jobs/{DEMO_SLUG}/apply",
        application_type=ApplicationType.ATS_FORM,
        dedupe_hash=uuid.uuid4().hex,
    )
    db.add(job)
    db.flush()
    db.add(
        JobSource(
            job_id=job.id,
            source=JobSourceType.DEMO_ATS,
            external_id=DEMO_SLUG,
            url=job.canonical_url,
            apply_url=job.apply_url,
            application_type=ApplicationType.ATS_FORM,
            discovered_at=now,
            last_seen_at=now,
        )
    )
    db.commit()
    return job


# --------------------------------------------------------------------------- the test


def test_demo_ats_end_to_end(db: Session, user: User, demo_job: Job):
    """Fill the real form, pause for the questions the profile cannot answer, approve."""
    application = service.queue_job(db, user.id, demo_job.id)
    assert application.source == JobSourceType.DEMO_ATS
    db.commit()

    service.start_application(db, application.id, user.id, run_in_background=False)
    db.expire_all()
    application = db.get(Application, application.id)

    # The automation stops instead of guessing.
    assert application.automation_state in {AutomationState.REQUIRES_USER, AutomationState.PAUSED}
    if application.automation_state == AutomationState.REQUIRES_USER:
        assert application.pause_reason == PauseReason.UNKNOWN_QUESTION
    else:
        assert application.pause_reason == PauseReason.USER_REVIEW

    snapshot = application.form_snapshot or {}
    keys = {str(row.get("key")) for row in snapshot.get("fields") or []}
    assert {"first_name", "last_name", "email", "resume_file"} <= keys, sorted(keys)
    assert snapshot.get("url", "").endswith(f"/demo-ats/jobs/{DEMO_SLUG}/apply")

    # Regression: the adapter used to bail out *before* typing anything when a required
    # question had no answer, leaving the reviewer an empty snapshot. Everything the
    # profile knows must already be on the page when the automation pauses.
    filled_keys = {str(row.get("key")) for row in snapshot.get("filled") or []}
    assert {"first_name", "last_name", "email", "phone", "resume_file"} <= filled_keys, sorted(filled_keys)
    assert snapshot.get("screenshot_path"), "the paused form must come with a screenshot"

    # Everything the profile knows is already answered from the profile.
    answers = {a.question_key: a for a in application.answers}
    assert answers["first_name"].answer == "Aarav"
    assert answers["email"].answer == APPLICANT_EMAIL
    assert answers["resume_file"].answer.endswith(".pdf")
    assert answers["work_authorization"].answer == "Yes"

    # ... and everything it does not is handed back to the user.
    missing = [a for a in application.answers if a.required and a.status == AnswerStatus.NEEDS_USER_INPUT]
    assert missing, "the demo form asks at least one question the profile cannot answer"
    assert any(a.question_key.startswith("custom:") for a in missing)

    from app.modules.applications.answers import save_user_answers

    save_user_answers(
        db,
        application,
        [{"id": row.id, "answer": _answer_for(row.question_key)} for row in missing],
    )
    db.flush()

    review = service.build_review(db, application)
    assert review.can_submit is True, review.blockers

    service.approve(db, application, user)
    db.expire_all()
    application = db.get(Application, application.id)

    assert application.status == ApplicationStatus.APPLIED
    assert application.automation_state == AutomationState.SUCCESS
    assert application.applied_at is not None
    assert application.approved_at is not None
    assert (application.external_application_id or "").startswith("DEMO-"), application.external_application_id
    assert "Thank you for applying" in (application.confirmation_message or "")

    # The submission really reached the demo ATS.
    submissions = (Path(settings.UPLOAD_DIR) / "demo_ats_submissions.jsonl").read_text(encoding="utf-8")
    assert application.external_application_id in submissions


def _answer_for(question_key: str) -> str:
    """A plausible human answer for whatever the form asked that we could not know."""
    if "consent" in question_key:
        return "Yes"
    if "start_date" in question_key:
        return "1 December 2026"
    if "kubernetes" in question_key:
        return "I ran a three-node EKS cluster for our staging workloads for a year."
    return "Yes"


def test_captcha_pauses_instead_of_being_solved(db: Session, user: User, demo_job: Job):
    """``?captcha=1`` renders a CAPTCHA widget: the automation must stop, never solve it."""
    demo_job.apply_url = f"{demo_job.apply_url}?captcha=1"
    application = service.queue_job(db, user.id, demo_job.id)
    db.commit()

    service.start_application(db, application.id, user.id, run_in_background=False)
    db.expire_all()
    application = db.get(Application, application.id)

    assert application.automation_state == AutomationState.REQUIRES_USER
    assert application.pause_reason == PauseReason.CAPTCHA
    assert application.status != ApplicationStatus.APPLIED
    assert application.external_application_id is None


# --------------------------------------------------------------------------- the pipeline, end to end


def test_pipeline_auto_applies_to_the_demo_ats_end_to_end(db: Session, user: User, demo_server: BackgroundServer):
    """Manual run, DEMO_ATS in AUTO_APPLY, auto-submit on for DEMO_ATS → APPLIED, unattended.

    The demo form asks two things the answer engine deliberately never decides for a
    human - the data-processing consent checkbox and a preferred start date - so those
    two are stored up front as answers the user typed (the only way the product lets
    them in). Everything else - discovery, scoring, queueing, answers, Chromium autofill
    and the submission - is the pipeline's own work.
    """
    from app.models.application import ApplicationAnswer
    from app.models.enums import AnswerSource, AutomationRunStatus, AutomationRunTrigger, CompanyPriority, FieldType
    from app.modules.adapters.registry import get_adapter
    from app.modules.automation import locks
    from app.modules.automation import service as automation_service
    from app.modules.automation.pipeline import run_pipeline
    from app.modules.jobs.service import build_search_query, ingest_discovered

    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == user.id)).first()
    preference.desired_titles = ["Full Stack Engineer"]  # matches exactly one demo posting
    preference.preferred_locations = []
    preference.only_posted_within_hours = 24 * 30

    config = automation_service.get_config(db, user.id)
    config.enabled_sources = ["DEMO_ATS"]
    config.source_modes = {"DEMO_ATS": "AUTO_APPLY"}
    config.auto_submit_enabled = True
    config.auto_submit_sources = ["DEMO_ATS"]
    config.min_match_score = 0
    config.daily_application_limit = 1
    config.only_posted_within_hours = 24 * 30
    config.delay_between_actions_seconds = 0.0
    config.retry_limit = 1
    config.auto_generate_cover_letters = False
    db.flush()

    # The two human-only answers, stored on a DISCOVERED application for every posting the
    # search can return ("Full Stack Engineer" also matches Google's "Software Engineer II,
    # Full Stack"); the budget of 1 means the run re-queues exactly one of them.
    discovered = get_adapter(JobSourceType.DEMO_ATS).search_jobs(build_search_query(preference))
    assert DEMO_SLUG in {job.external_id for job in discovered}
    ingested = ingest_discovered(db, user.id, discovered)
    resume = db.scalars(select(Resume).where(Resume.user_id == user.id)).first()
    seeded: set[uuid.UUID] = set()
    for job_id in ingested.job_ids_all:
        application = Application(
            user_id=user.id,
            job_id=job_id,
            resume_id=resume.id,
            status=ApplicationStatus.DISCOVERED,
            priority=CompanyPriority.P2,
            source=JobSourceType.DEMO_ATS,
            review_required=True,
            form_snapshot={},
        )
        db.add(application)
        db.flush()
        seeded.add(application.id)
        for key, text, field_type, answer in (
            ("custom:consent", "I consent to the processing of my data", FieldType.CHECKBOX, "Yes"),
            ("custom:start_date", "What is your preferred start date?", FieldType.TEXT, "1 December 2026"),
        ):
            db.add(
                ApplicationAnswer(
                    application_id=application.id,
                    question_key=key,
                    question_text=text,
                    field_type=field_type,
                    required=True,
                    answer=answer,
                    answer_source=AnswerSource.USER,
                    status=AnswerStatus.ANSWERED,
                    confidence=1.0,
                    rationale="Provided by you",
                )
            )
    db.commit()

    locks.reset_locks()
    run = run_pipeline(user.id, AutomationRunTrigger.MANUAL, db=db, sleep_fn=lambda seconds: None)
    db.commit()
    steps = {step["step"]: step for step in run.steps}

    assert run.status == AutomationRunStatus.SUCCESS, run.steps
    assert run.config_snapshot["source_modes"] == {"DEMO_ATS": "AUTO_APPLY"}
    queued = steps["queue"]["data"]["applications"]
    assert len(queued) == 1 and queued[0]["source"] == "DEMO_ATS" and queued[0]["auto_submit"] is True
    application_id = uuid.UUID(queued[0]["application_id"])
    assert application_id in seeded, "the run must re-queue the DISCOVERED row that carries the user's answers"
    assert steps["generate_answers"]["data"] == {
        **steps["generate_answers"]["data"],
        "prepared": 1,
        "deferred": [],
        "browser_available": True,
    }
    assert steps["autofill"]["data"]["filled"] == 1
    assert steps["auto_submit"]["status"] == "SUCCESS"
    assert steps["auto_submit"]["data"] == {"submitted": 1, "skipped_needs_input": []}
    assert run.stats["queued"] == 1 and run.stats["submitted"] == 1 and run.stats["requires_user"] == 0

    db.expire_all()
    application = db.get(Application, application_id)
    assert application.status == ApplicationStatus.APPLIED
    assert application.automation_state == AutomationState.SUCCESS
    assert application.auto_submit is True
    assert application.automation_run_id == run.id
    assert application.applied_at is not None and application.approved_at is not None
    assert (application.external_application_id or "").startswith("DEMO-"), application.external_application_id
    assert "Thank you for applying" in (application.confirmation_message or "")
    submissions = (Path(settings.UPLOAD_DIR) / "demo_ats_submissions.jsonl").read_text(encoding="utf-8")
    assert application.external_application_id in submissions


def test_pipeline_auto_applies_with_standing_answers_only(db: Session, user: User, demo_server: BackgroundServer):
    """Same unattended run, but nothing is stored on any application: only the user's two
    standing answers (consent, saved at another company, and a start date). The runner
    answers the form from them before filling, so the run ends APPLIED with no pause."""
    from app.models.enums import AnswerSource, AutomationRunStatus, AutomationRunTrigger, FieldType
    from app.modules.automation import locks
    from app.modules.automation import service as automation_service
    from app.modules.automation.pipeline import run_pipeline
    from app.modules.profiles.service import upsert_standing_answer

    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == user.id)).first()
    preference.desired_titles = ["Full Stack Engineer"]
    preference.preferred_locations = []
    preference.only_posted_within_hours = 24 * 30

    config = automation_service.get_config(db, user.id)
    config.enabled_sources = ["DEMO_ATS"]
    config.source_modes = {"DEMO_ATS": "AUTO_APPLY"}
    config.auto_submit_enabled = True
    config.auto_submit_sources = ["DEMO_ATS"]
    config.min_match_score = 0
    config.daily_application_limit = 1
    config.only_posted_within_hours = 24 * 30
    config.delay_between_actions_seconds = 0.0
    config.retry_limit = 1
    config.auto_generate_cover_letters = False

    # Saved while applying to a *different* company: the employer's name is factored out.
    upsert_standing_answer(
        db,
        user.id,
        question_key="custom:consent",
        question_text=(
            "I consent to Acme Cloud storing the information in this application and contacting me "
            "about this role. *"
        ),
        answer="Yes",
        field_type=FieldType.CHECKBOX,
        company_name="Acme Cloud",
    )
    upsert_standing_answer(
        db,
        user.id,
        question_key="custom:start_date",
        question_text="What is your preferred start date?",
        answer="1 December 2026",
    )
    db.commit()
    assert db.scalars(select(Application).where(Application.user_id == user.id)).first() is None

    locks.reset_locks()
    run = run_pipeline(user.id, AutomationRunTrigger.MANUAL, db=db, sleep_fn=lambda seconds: None)
    db.commit()
    steps = {step["step"]: step for step in run.steps}

    assert run.status == AutomationRunStatus.SUCCESS, run.steps
    queued = steps["queue"]["data"]["applications"]
    assert len(queued) == 1 and queued[0]["source"] == "DEMO_ATS" and queued[0]["auto_submit"] is True
    assert steps["autofill"]["data"]["filled"] == 1 and steps["autofill"]["data"]["requires_user"] == 0
    assert steps["approval_queue"]["data"] == {"ready_for_review": 0, "requires_user": 0}
    assert steps["auto_submit"]["data"] == {"submitted": 1, "skipped_needs_input": []}
    assert run.stats["submitted"] == 1 and run.stats["requires_user"] == 0

    db.expire_all()
    application = db.get(Application, uuid.UUID(queued[0]["application_id"]))
    assert application.status == ApplicationStatus.APPLIED
    assert application.automation_state == AutomationState.SUCCESS
    assert (application.external_application_id or "").startswith("DEMO-"), application.external_application_id
    by_key = {a.question_key: a for a in application.answers}
    for key, expected in (("custom:consent", "Yes"), ("custom:start_date", "1 December 2026")):
        assert by_key[key].answer == expected
        assert by_key[key].answer_source == AnswerSource.USER
        assert by_key[key].rationale == "Standing answer you saved"
    assert not [a for a in application.answers if a.required and a.status == AnswerStatus.NEEDS_USER_INPUT]
    submissions = (Path(settings.UPLOAD_DIR) / "demo_ats_submissions.jsonl").read_text(encoding="utf-8")
    assert application.external_application_id in submissions
