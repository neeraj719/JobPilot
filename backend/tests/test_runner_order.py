"""``ApplicationRunner`` answers a form *before* the adapter fills it (Step 1b, Gap A).

A stubbed browser adapter and a stubbed ``detect_form`` make the order observable
without Chromium: ``start -> detect -> record questions -> generate answers -> fill``.
The adapter's fill only "succeeds" when every answer it is handed is answered, which is
exactly how ``browser.autofill`` + ``GenericAtsFormAdapter`` behave: an answer row that is
still ``NEEDS_USER_INPUT`` is reported back and pauses the run.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.application import Application
from app.models.automation import AutomationConfig
from app.models.company import Company
from app.models.enums import (
    AnswerSource,
    AnswerStatus,
    ApplicationType,
    AutomationState,
    FieldType,
    JobSourceType,
    PauseReason,
    WorkMode,
)
from app.models.job import Job, JobSource
from app.models.profile import JobPreference, StandingAnswer, UserProfile
from app.models.user import User
from app.modules.adapters.base import ApplyStepResult, JobSourceAdapter
from app.modules.applications import answers as answers_engine
from app.modules.applications import executor, service
from app.modules.browser.mapper import default_mapper
from app.modules.browser.runner import ApplicationRunner
from app.modules.browser.schemas import Blocker, DetectedField, DetectedForm

APPLY_URL = "https://careers.example.test/apply/1"


# --------------------------------------------------------------------------- stubs


class FakeHandle:
    """Stands in for ``BrowserSessionHandle``: a page object and no screenshots."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.page = object()

    def __enter__(self) -> "FakeHandle":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def screenshot(self, *args: Any, **kwargs: Any) -> None:
        return None


class StubAdapter(JobSourceAdapter):
    """A browser adapter whose fill behaves like autofill: gaps in what it is handed pause."""

    source = JobSourceType.LINKEDIN
    display_name = "Stub ATS"
    is_mock = True
    uses_browser = True
    supports_auto_apply = True

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.fill_ctx: Any = None

    def search_jobs(self, query: Any) -> list[Any]:
        return []

    def start_application(self, ctx: Any) -> ApplyStepResult:
        self.calls.append("start")
        return ApplyStepResult(state=AutomationState.SUCCESS, message="opened", form_snapshot={"url": APPLY_URL})

    def fill_application(self, ctx: Any) -> ApplyStepResult:
        self.calls.append("fill")
        self.fill_ctx = ctx
        detected = ctx.detected_form
        by_key = {a.question_key: a for a in ctx.answers}
        fields, filled, needs_user = [], [], []
        for field in detected.fields:
            key = default_mapper.map(field).canonical_key
            answer = by_key.get(key)
            fields.append({"key": key, "label": field.label, "selector": field.selector, "required": field.required})
            if answer is None:
                continue  # autofill: no answer -> skipped (needs the user only when required)
            if answer.status != AnswerStatus.ANSWERED:
                needs_user.append({"key": key, "required": field.required})
                continue
            filled.append({"key": key, "selector": field.selector})
        missing = [f["key"] for f in fields if f["required"] and f["key"] not in {r["key"] for r in filled}]
        snapshot = {"url": APPLY_URL, "fields": fields, "filled": filled, "needs_user": needs_user, "missing": missing}
        if missing or needs_user:
            return ApplyStepResult(
                state=AutomationState.REQUIRES_USER,
                message="Some fields still need your input",
                pause_reason=PauseReason.UNKNOWN_QUESTION,
                form_snapshot=snapshot,
            )
        return ApplyStepResult(state=AutomationState.SUCCESS, message="filled", form_snapshot=snapshot)

    def submit_application(self, ctx: Any) -> ApplyStepResult:  # pragma: no cover - auto-submit is off
        self.calls.append("submit")
        return ApplyStepResult(state=AutomationState.FAILED, message="not in these tests")


def field(name: str, label: str, *, required: bool, field_type: FieldType = FieldType.TEXT) -> DetectedField:
    return DetectedField(selector=f"#{name}", label=label, name=name, id=name, field_type=field_type, required=required)


BASE_FIELDS = [
    field("first_name", "First Name *", required=True),
    field("email", "Email *", required=True, field_type=FieldType.EMAIL),
    field("portfolio_url", "Portfolio (optional)", required=False, field_type=FieldType.URL),
]
START_DATE = field("start_date", "What is your preferred start date? *", required=True)


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _reset_executor():
    executor.reset()
    yield
    executor.reset()


@pytest.fixture
def user(db: Session) -> User:
    row = User(email="order@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Order Tester")
    db.add(row)
    db.flush()
    db.add(
        UserProfile(
            user_id=row.id,
            full_name="Order Tester",
            first_name="Order",
            last_name="Tester",
            email="order@example.com",
            city="Bangalore",
            country="India",
            years_of_experience=2.0,
            skills=["React"],
        )
    )
    db.add(JobPreference(user_id=row.id, currency="INR", notice_period_days=30, min_match_score=0))
    db.add(AutomationConfig(user_id=row.id, retry_limit=1, auto_submit_enabled=False, auto_generate_cover_letters=False))
    db.commit()
    return row


@pytest.fixture
def application(db: Session, user: User) -> Application:
    company = Company(name="Northwind Labs", normalized_name="northwind", domain="northwindlabs.dev")
    db.add(company)
    db.flush()
    now = datetime.now(timezone.utc)
    job = Job(
        company_id=company.id,
        title="Full Stack Engineer",
        normalized_title="full stack engineer",
        description="React.",
        location="Bangalore, India",
        work_mode=WorkMode.HYBRID,
        posted_at=now - timedelta(hours=1),
        canonical_url="https://careers.example.test/jobs/1",
        apply_url=APPLY_URL,
        application_type=ApplicationType.ATS_FORM,
        dedupe_hash=uuid.uuid4().hex,
    )
    db.add(job)
    db.flush()
    db.add(
        JobSource(
            job_id=job.id,
            source=JobSourceType.LINKEDIN,
            external_id="order-1",
            url=job.canonical_url,
            apply_url=APPLY_URL,
            application_type=ApplicationType.ATS_FORM,
            discovered_at=now,
            last_seen_at=now,
        )
    )
    db.commit()
    row = service.queue_job(db, user.id, job.id)
    db.commit()
    return row


@pytest.fixture
def calls() -> list[str]:
    return []


@pytest.fixture
def stub(monkeypatch, calls: list[str]) -> StubAdapter:
    """Wire the stub adapter, a fake browser and call-recording wrappers into the runner."""
    from app.modules.adapters import registry
    from app.modules.browser import session as browser_session

    adapter = StubAdapter(calls)
    monkeypatch.setattr(registry, "get_adapter", lambda source: adapter)
    monkeypatch.setattr(browser_session, "is_browser_available", lambda: True)
    monkeypatch.setattr(browser_session, "BrowserSessionHandle", FakeHandle)

    record = service.record_form_questions

    def recording_record(*args: Any, **kwargs: Any) -> Any:
        calls.append("record")
        return record(*args, **kwargs)

    generate = answers_engine.generate_answers

    def recording_generate(*args: Any, **kwargs: Any) -> Any:
        calls.append("generate")
        return generate(*args, **kwargs)

    monkeypatch.setattr(service, "record_form_questions", recording_record)
    monkeypatch.setattr(answers_engine, "generate_answers", recording_generate)
    return adapter


def use_form(monkeypatch, calls: list[str], form: DetectedForm) -> None:
    from app.modules.browser import detector

    def fake_detect(page: Any) -> DetectedForm:
        calls.append("detect")
        return form

    monkeypatch.setattr(detector, "detect_form", fake_detect)


def run(db: Session, application: Application) -> Application:
    ApplicationRunner(application.id, db=db).run()
    db.commit()
    db.expire_all()
    return db.get(Application, application.id)


# --------------------------------------------------------------------------- tests


def test_the_runner_answers_the_form_before_filling_it(db, application, stub, calls, monkeypatch):
    form = DetectedForm(url=APPLY_URL, fields=list(BASE_FIELDS), submit_selector="button[type=submit]")
    use_form(monkeypatch, calls, form)

    result = run(db, application)

    assert calls[:5] == ["start", "detect", "record", "generate", "fill"], calls
    assert calls.count("detect") == 1, "the adapter must reuse the runner's detected form"
    assert stub.fill_ctx.detected_form is form

    answers = {a.question_key: a for a in result.answers}
    assert answers["first_name"].answer == "Order"
    assert answers["first_name"].field_selector == "#first_name"
    # The form's questions come first, in page order.
    assert [a.question_key for a in sorted(result.answers, key=lambda a: a.order)][:3] == [
        "first_name",
        "email",
        "portfolio_url",
    ]


def test_an_optional_unanswered_question_does_not_pause(db, application, stub, calls, monkeypatch):
    use_form(monkeypatch, calls, DetectedForm(url=APPLY_URL, fields=list(BASE_FIELDS)))

    result = run(db, application)

    portfolio = next(a for a in result.answers if a.question_key == "portfolio_url")
    assert portfolio.status == AnswerStatus.NEEDS_USER_INPUT and portfolio.required is False
    # ... it is not handed to the filler, so it cannot come back as "needs the user".
    assert "portfolio_url" not in {a.question_key for a in stub.fill_ctx.answers}
    assert result.automation_state == AutomationState.PAUSED
    assert result.pause_reason == PauseReason.USER_REVIEW


def test_a_required_unanswered_question_still_pauses(db, application, stub, calls, monkeypatch):
    use_form(monkeypatch, calls, DetectedForm(url=APPLY_URL, fields=[*BASE_FIELDS, START_DATE]))

    result = run(db, application)

    assert "fill" in calls  # everything known is still typed before the pause
    assert result.automation_state == AutomationState.REQUIRES_USER
    assert result.pause_reason == PauseReason.UNKNOWN_QUESTION
    start = next(a for a in result.answers if a.question_key == "custom:start_date")
    assert start.required and start.status == AnswerStatus.NEEDS_USER_INPUT


def test_a_standing_answer_lets_the_same_form_through(db, user, application, stub, calls, monkeypatch):
    db.add(
        StandingAnswer(
            user_id=user.id,
            question_key="custom:start_date",
            question_text="What is your preferred start date?",
            field_type=FieldType.TEXT,
            answer="1 December 2026",
            applies_to="ALL",
            is_active=True,
        )
    )
    db.commit()
    use_form(monkeypatch, calls, DetectedForm(url=APPLY_URL, fields=[*BASE_FIELDS, START_DATE]))

    result = run(db, application)

    start = next(a for a in result.answers if a.question_key == "custom:start_date")
    assert start.answer == "1 December 2026"
    assert start.answer_source == AnswerSource.USER
    assert start.rationale == "Standing answer you saved"
    assert result.automation_state == AutomationState.PAUSED
    assert result.pause_reason == PauseReason.USER_REVIEW


def test_a_blocker_pauses_with_the_mapped_fields_and_nothing_typed(db, application, stub, calls, monkeypatch):
    form = DetectedForm(
        url=APPLY_URL,
        fields=[*BASE_FIELDS, START_DATE],
        blockers=[Blocker(kind=PauseReason.CAPTCHA, selector=".g-recaptcha", message="Complete the CAPTCHA yourself")],
    )
    use_form(monkeypatch, calls, form)

    result = run(db, application)

    assert calls[:4] == ["start", "detect", "record", "generate"], calls
    assert "fill" not in calls, "nothing may be typed into a form behind a CAPTCHA"
    assert result.automation_state == AutomationState.REQUIRES_USER
    assert result.pause_reason == PauseReason.CAPTCHA
    snapshot = result.form_snapshot
    assert [row["key"] for row in snapshot["fields"]] == ["first_name", "email", "portfolio_url", "custom:start_date"]
    assert snapshot["filled"] == []
    assert snapshot["blockers"][0]["kind"] == "CAPTCHA"
    # The questions are answered already, so the user only has to clear the CAPTCHA.
    assert next(a for a in result.answers if a.question_key == "first_name").answer == "Order"
