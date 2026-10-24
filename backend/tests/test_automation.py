"""Automation module tests (contract §14): config validation, the pipeline, locks and the API."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import ConflictError, ValidationFailed
from app.models.application import Application
from app.models.automation import AutomationConfig, AutomationRun
from app.models.company import Company
from app.models.enums import (
    ApplicationStatus,
    AutomationRunStatus,
    AutomationRunTrigger,
    CompanyPriority,
    JobSourceType,
    NotificationType,
    SourceApplyMode,
)
from app.models.job import Job
from app.models.notification import Notification
from app.models.profile import CompanyPreference, JobPreference, UserProfile
from app.models.user import User
from app.modules.automation import limits, locks, pipeline
from app.modules.automation import service as automation_service
from app.modules.automation.schemas import AutomationConfigUpdate

API = "/api/v1/automation"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _fast_and_offline(monkeypatch):
    """No real browser, no artificial delays — the pipeline must still work end to end."""
    monkeypatch.setattr(settings, "BROWSER_ACTION_DELAY_MS", 0, raising=False)
    monkeypatch.setattr(pipeline, "_browser_available", lambda: False)
    monkeypatch.setattr(pipeline, "_sleep", lambda seconds: None)
    locks.reset_locks()
    yield
    locks.reset_locks()


@pytest.fixture
def user(db) -> User:
    from app.modules.auth.service import create_user

    row = create_user(db, "automation-tester@example.com", "StrongPass123!", "Automation Tester")
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == row.id)).first()
    profile.skills = ["React", "Node.js", "TypeScript", "PostgreSQL", "Docker", "AWS"]
    profile.years_of_experience = 2.0
    profile.city = "Bangalore"
    profile.phone = "+91 90000 00000"
    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == row.id)).first()
    preference.desired_titles = ["Software Engineer", "Full Stack Developer", "Backend Engineer"]
    preference.preferred_locations = ["Bangalore", "Remote"]
    preference.preferred_technologies = ["React", "Node.js"]
    preference.min_salary = 1_000_000
    preference.desired_salary = 1_400_000
    preference.notice_period_days = 30
    preference.min_match_score = 70
    preference.only_posted_within_hours = 24 * 7
    preference.excluded_keywords = ["unpaid internship"]
    db.flush()
    return row


@pytest.fixture
def config(db, user) -> AutomationConfig:
    row = automation_service.get_config(db, user.id)
    row.min_match_score = 70
    row.daily_application_limit = 4
    row.only_posted_within_hours = 24 * 7
    row.delay_between_actions_seconds = 0.0
    row.prioritize_priority_companies = True
    db.flush()
    return row


@pytest.fixture
def priorities(db, user) -> None:
    """Google is P1, Wipro is on the avoid list."""
    from app.modules.companies.service import upsert_preference

    upsert_preference(db, user.id, "Google", CompanyPriority.P1)
    upsert_preference(db, user.id, "Wipro", CompanyPriority.AVOID)
    db.flush()


def _run(db, user, **kwargs) -> AutomationRun:
    return pipeline.run_pipeline(
        user.id, AutomationRunTrigger.MANUAL, db=db, sleep_fn=lambda seconds: None, **kwargs
    )


def _steps(run: AutomationRun) -> dict[str, dict]:
    return {step["step"]: step for step in run.steps}


def _utc(value: datetime) -> datetime:
    """SQLite hands datetimes back naive; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- config validation


def test_config_defaults_are_created_on_demand(db, user):
    config = automation_service.get_config(db, user.id)
    assert config.daily_application_limit == settings.DEFAULT_DAILY_APPLICATION_LIMIT
    assert config.schedule_time == "09:00"
    assert config.timezone == "Asia/Kolkata"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"schedule_time": "9:00"}, "invalid_schedule_time"),
        ({"schedule_time": "25:00"}, "invalid_schedule_time"),
        ({"timezone": "Mars/Olympus"}, "invalid_timezone"),
        ({"daily_application_limit": settings.MAX_DAILY_APPLICATION_LIMIT + 1}, "daily_limit_too_high"),
        ({"per_platform_limit": {"NOT_A_SOURCE": 3}}, "unknown_source"),
        ({"enabled_sources": ["NOPE"]}, "unknown_source"),
        ({"auto_submit_sources": ["GLASSDOOR"]}, "auto_submit_unsupported"),
    ],
)
def test_config_validation_rejects_bad_values(db, user, payload, code):
    with pytest.raises(ValidationFailed) as excinfo:
        automation_service.update_config(db, user.id, AutomationConfigUpdate(**payload))
    assert excinfo.value.code == code


def test_config_update_accepts_valid_values_and_computes_next_run(db, user):
    allowed = sorted(s.value for s in automation_service.auto_apply_sources())
    assert allowed, "at least one adapter must support auto apply"
    updated = automation_service.update_config(
        db,
        user.id,
        AutomationConfigUpdate(
            enabled=True,
            schedule_time="07:30",
            timezone="Asia/Kolkata",
            daily_application_limit=15,
            per_platform_limit={"linkedin": 5},
            auto_submit_enabled=True,
            auto_submit_sources=[allowed[0]],
        ),
    )
    assert updated.schedule_time == "07:30"
    assert updated.per_platform_limit == {"LINKEDIN": 5}
    assert updated.auto_submit_sources == [allowed[0]]
    assert updated.next_run_at is not None and updated.next_run_at > datetime.now(timezone.utc)


def test_next_run_at_respects_the_user_timezone(db, user):
    config = automation_service.get_config(db, user.id)
    config.enabled = True
    config.schedule_time = "09:00"
    config.timezone = "Asia/Kolkata"
    now = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)  # 17:30 IST — today's slot has passed
    next_run = automation_service.compute_next_run_at(config, now)
    assert next_run == datetime(2026, 3, 11, 3, 30, tzinfo=timezone.utc)  # 09:00 IST the next day


# --------------------------------------------------------------------------- limits


def test_budget_counts_todays_submissions(db, user, config):
    company = Company(name="Budget Co", normalized_name="budgetco")
    db.add(company)
    db.flush()
    job = Job(company_id=company.id, title="Engineer", normalized_title="engineer", dedupe_hash="budget-1")
    db.add(job)
    db.flush()
    db.add(
        Application(
            user_id=user.id,
            job_id=job.id,
            status=ApplicationStatus.APPLIED,
            applied_at=datetime.now(timezone.utc),
            source=JobSourceType.LINKEDIN,
        )
    )
    db.flush()

    budget = limits.compute_budget(db, user.id, config)
    assert budget.submitted_today == 1
    assert budget.remaining == config.daily_application_limit - 1


def test_budget_enforces_per_platform_limits(db, user, config):
    config.per_platform_limit = {"LINKEDIN": 1}
    db.flush()
    budget = limits.compute_budget(db, user.id, config)
    assert budget.remaining_for(JobSourceType.LINKEDIN) == 1
    budget.take(JobSourceType.LINKEDIN)
    assert budget.remaining_for(JobSourceType.LINKEDIN) == 0
    # A source without its own cap still has the daily budget available.
    assert budget.remaining_for(JobSourceType.NAUKRI) > 0


def test_day_bounds_follow_the_user_timezone():
    now = datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)  # 01:30 IST on the 11th
    start, end = limits.day_bounds("Asia/Kolkata", now)
    assert start == datetime(2026, 3, 10, 18, 30, tzinfo=timezone.utc)
    assert end - start == timedelta(days=1)


# --------------------------------------------------------------------------- pipeline


def test_dry_run_stops_after_enforce_limits(db, user, config, priorities):
    run = _run(db, user, dry_run=True)
    steps = _steps(run)
    assert run.status == AutomationRunStatus.SUCCESS
    assert run.stats["jobs_found"] > 0
    assert steps["queue"]["status"] == "SKIPPED"
    assert steps["queue"]["data"]["would_queue"], "the dry run must report what it would queue"
    assert "generate_answers" not in steps and "auto_submit" not in steps
    assert db.scalars(select(Application).where(Application.user_id == user.id)).first() is None


def test_full_run_queues_within_the_daily_limit(db, user, config, priorities):
    run = _run(db, user)

    assert run.status in (AutomationRunStatus.SUCCESS, AutomationRunStatus.PARTIAL)
    assert run.finished_at is not None
    assert run.stats["jobs_found"] > 0
    assert run.stats["jobs_new"] > 0
    assert 0 < run.stats["queued"] <= config.daily_application_limit

    applications = list(db.scalars(select(Application).where(Application.user_id == user.id)).unique())
    assert len(applications) == run.stats["queued"]
    assert all(a.automation_run_id == run.id for a in applications)

    # Every step is recorded with timestamps, in pipeline order.
    order = [step["step"] for step in run.steps]
    assert order[:7] == ["search", "collect", "dedupe", "analyze", "filter", "prioritize", "enforce_limits"]
    assert order[-1] == "finish"
    for step in run.steps:
        assert step["started_at"] and step["finished_at"] and step["duration_ms"] is not None


def test_run_prioritizes_p1_companies_first(db, user, config, priorities):
    config.daily_application_limit = 20
    db.flush()
    run = _run(db, user)

    applications = list(
        db.scalars(
            select(Application).where(Application.user_id == user.id, Application.automation_run_id == run.id)
        ).unique()
    )
    queued_order = [
        entry["priority"] for entry in _steps(run)["queue"]["data"]["applications"]
    ]
    assert queued_order, "the run must queue something"
    p1_positions = [i for i, value in enumerate(queued_order) if value == CompanyPriority.P1.value]
    if p1_positions:
        assert max(p1_positions) < min(
            [i for i, value in enumerate(queued_order) if value != CompanyPriority.P1.value] or [len(queued_order)]
        )
    assert any(a.priority == CompanyPriority.P1 for a in applications) or not p1_positions


def test_run_excludes_avoid_companies_and_low_scores(db, user, config, priorities):
    config.min_match_score = 80
    db.flush()
    run = _run(db, user)
    reasons = run.stats["filter_reasons"]

    assert reasons["below_min_score"] > 0
    avoid_names = {
        name.lower()
        for name in db.scalars(
            select(CompanyPreference.company_name).where(
                CompanyPreference.user_id == user.id, CompanyPreference.priority == CompanyPriority.AVOID
            )
        ).all()
    }
    queued_companies = {
        entry["company"].lower() for entry in _steps(run)["queue"]["data"]["applications"]
    }
    assert not (queued_companies & avoid_names)
    for entry in _steps(run)["queue"]["data"]["applications"]:
        assert entry["match_score"] >= 80


def test_run_records_the_limit_reason_when_the_budget_runs_out(db, user, config, priorities):
    config.daily_application_limit = 2
    db.flush()
    run = _run(db, user)
    assert run.stats["queued"] <= 2
    assert run.stats["skipped_limit"] >= 1
    assert run.stats["filter_reasons"]["limit_reached"] >= 1


def test_run_notifies_the_user_with_a_summary(db, user, config, priorities):
    run = _run(db, user)
    notifications = list(
        db.scalars(
            select(Notification).where(
                Notification.user_id == user.id, Notification.type == NotificationType.AUTOMATION_COMPLETED
            )
        )
    )
    assert notifications, "the run must notify the user"
    body = notifications[-1].body or ""
    assert body.startswith("Found ")
    for fragment in ("matched", "high-match", "queued", "ready for review", "need your input"):
        assert fragment in body
    assert run.stats["queued"] >= 0


def test_run_updates_last_and_next_run_at(db, user, config, priorities):
    config.enabled = True
    db.flush()
    _run(db, user)
    db.refresh(config)
    assert config.last_run_at is not None
    assert config.next_run_at is not None
    assert _utc(config.next_run_at) > datetime.now(timezone.utc)


def test_run_writes_the_audit_trail(db, user, config, priorities):
    from app.models.audit import AuditLog

    run = _run(db, user)
    actions = set(
        db.scalars(select(AuditLog.action).where(AuditLog.automation_run_id == run.id)).all()
    )
    assert {"automation.run_started", "automation.step", "automation.run_finished"} <= actions


def test_second_run_skips_jobs_already_applied_to(db, user, config, priorities):
    first = _run(db, user)
    assert first.stats["queued"] > 0
    second = _run(db, user)
    assert second.stats["filter_reasons"]["already_applied"] >= first.stats["queued"]


# --------------------------------------------------------------------------- locking & cancellation


def test_lock_prevents_a_concurrent_run(db, user, config):
    token = locks.acquire_lock(user.id)
    assert token is not None
    try:
        with pytest.raises(ConflictError):
            pipeline.run_pipeline(user.id, AutomationRunTrigger.MANUAL, db=db)
    finally:
        locks.release_lock(user.id, token)
    assert not locks.is_locked(user.id)


def test_start_manual_run_conflicts_while_a_run_is_running(db, user, config):
    automation_service.create_run(db, user.id, AutomationRunTrigger.MANUAL)
    with pytest.raises(ConflictError):
        automation_service.start_manual_run(db, user.id, background=False)


def test_cancel_marks_the_run_cancelled(db, user, config):
    run = automation_service.create_run(db, user.id, AutomationRunTrigger.MANUAL)
    cancelled = automation_service.cancel_run(db, user.id, run.id)
    assert cancelled.status == AutomationRunStatus.CANCELLED
    assert cancelled.finished_at is not None
    with pytest.raises(ConflictError):
        automation_service.cancel_run(db, user.id, run.id)


def test_cancelled_run_stops_the_pipeline_between_steps(db, user, config, priorities):
    run = automation_service.create_run(db, user.id, AutomationRunTrigger.MANUAL)
    automation_service.request_cancel(run.id)
    finished = pipeline.run_pipeline(
        user.id, AutomationRunTrigger.MANUAL, run_id=run.id, db=db, sleep_fn=lambda seconds: None
    )
    assert finished.status == AutomationRunStatus.CANCELLED
    assert db.scalars(select(Application).where(Application.user_id == user.id)).first() is None


def test_lock_is_released_after_a_run(db, user, config, priorities):
    _run(db, user)
    assert not locks.is_locked(user.id)


# --------------------------------------------------------------------------- API


@pytest.fixture
def api_user(auth_client, db) -> User:
    """The auth_client's user, with enough profile data for a real run."""
    row = db.scalars(select(User).where(User.email == "tester@example.com")).first()
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == row.id)).first()
    profile.skills = ["React", "Node.js", "TypeScript"]
    profile.years_of_experience = 2.0
    profile.city = "Bangalore"
    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == row.id)).first()
    preference.desired_titles = ["Software Engineer"]
    preference.preferred_locations = ["Bangalore", "Remote"]
    preference.only_posted_within_hours = 24 * 7
    db.commit()
    return row


def test_config_endpoints(auth_client, api_user):
    response = auth_client.get(f"{API}/config")
    assert response.status_code == 200
    body = response.json()
    assert body["schedule_time"] == "09:00"

    response = auth_client.put(f"{API}/config", json={"enabled": True, "schedule_time": "08:15", "daily_application_limit": 12})
    assert response.status_code == 200, response.text
    assert response.json()["schedule_time"] == "08:15"
    assert response.json()["daily_application_limit"] == 12

    response = auth_client.put(f"{API}/config", json={"schedule_time": "8:15"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_schedule_time"


def test_status_endpoint_reports_today(auth_client, api_user):
    auth_client.put(f"{API}/config", json={"enabled": True, "daily_application_limit": 7})
    response = auth_client.get(f"{API}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["next_run_at"] is not None
    assert body["today"]["applications_submitted"] == 0
    assert body["today"]["limit_remaining"] == 7
    assert body["running"] is False


def test_run_endpoint_starts_a_background_run(auth_client, api_user, monkeypatch):
    started: dict[str, object] = {}

    def fake_spawn(target, *args, **kwargs):
        started["args"] = args
        return None

    monkeypatch.setattr(automation_service, "_spawn", fake_spawn)
    response = auth_client.post(f"{API}/run", json={"dry_run": True})
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == AutomationRunStatus.RUNNING.value
    assert started["args"][0] == api_user.id
    assert started["args"][2] is True  # dry_run forwarded

    # A second request conflicts while the first run is still RUNNING.
    conflict = auth_client.post(f"{API}/run", json={})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "automation_running"

    run_id = body["id"]
    assert auth_client.get(f"{API}/runs/{run_id}").status_code == 200
    listed = auth_client.get(f"{API}/runs").json()
    assert listed["total"] == 1

    cancelled = auth_client.post(f"{API}/runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == AutomationRunStatus.CANCELLED.value


def test_runs_are_scoped_to_the_current_user(auth_client, api_user, db):
    from app.modules.auth.service import create_user

    other = create_user(db, "someone-else@example.com", "StrongPass123!", "Someone Else")
    run = automation_service.create_run(db, other.id, AutomationRunTrigger.MANUAL)
    db.commit()
    assert auth_client.get(f"{API}/runs/{run.id}").status_code == 404
    assert auth_client.get(f"{API}/runs").json()["total"] == 0


def test_endpoints_require_authentication(client):
    assert client.get(f"{API}/config").status_code == 401
    assert client.get(f"{API}/status").status_code == 401
    assert client.post(f"{API}/run", json={}).status_code == 401


# --------------------------------------------------------------------------- worker


def test_due_users_respects_schedule_and_timezone(db, user):
    from app.worker import scheduler

    config = automation_service.get_config(db, user.id)
    config.enabled = True
    config.schedule_time = "09:00"
    config.timezone = "Asia/Kolkata"
    config.last_run_at = None
    db.flush()

    before = datetime(2026, 3, 10, 2, 0, tzinfo=timezone.utc)  # 07:30 IST — too early
    after = datetime(2026, 3, 10, 5, 0, tzinfo=timezone.utc)  # 10:30 IST — due
    assert user.id not in scheduler.due_users(db, before)
    assert user.id in scheduler.due_users(db, after)

    config.last_run_at = datetime(2026, 3, 10, 4, 0, tzinfo=timezone.utc)  # already ran today (IST)
    db.flush()
    assert user.id not in scheduler.due_users(db, after)


def test_tick_starts_a_run_for_every_due_user(db, user, monkeypatch):
    from app.worker import scheduler

    config = automation_service.get_config(db, user.id)
    config.enabled = True
    config.schedule_time = "00:01"  # already past in every timezone by the time this runs
    config.timezone = "UTC"
    config.last_run_at = None
    db.commit()

    started: list[uuid.UUID] = []
    monkeypatch.setattr(scheduler, "_run_for_user", started.append)
    due = scheduler.tick_scheduled_runs(background=False)
    assert user.id in due
    assert started == [user.id]


def test_tick_skips_a_user_that_already_ran_today(db, user, monkeypatch):
    from app.worker import scheduler

    config = automation_service.get_config(db, user.id)
    config.enabled = True
    config.schedule_time = "00:01"
    config.timezone = "UTC"
    config.last_run_at = datetime.now(timezone.utc)
    db.commit()

    started: list[uuid.UUID] = []
    monkeypatch.setattr(scheduler, "_run_for_user", started.append)
    assert scheduler.tick_scheduled_runs(background=False) == []
    assert started == []


def test_scheduled_run_is_skipped_while_the_lock_is_held(db, user, config, monkeypatch):
    """The worker must never start a pipeline for a user the API is already running."""
    from app.worker import scheduler

    calls: list[tuple] = []
    monkeypatch.setattr(pipeline, "run_pipeline", lambda *args, **kwargs: calls.append(args))

    token = locks.acquire_lock(user.id)
    try:
        scheduler._run_for_user(user.id)
        assert calls == [], "the lock must keep a second run out"
    finally:
        locks.release_lock(user.id, token)

    scheduler._run_for_user(user.id)
    assert len(calls) == 1, "once the lock is free the scheduled run proceeds"
    assert not locks.is_locked(user.id), "the scheduler releases the lock it took"


def test_mark_no_response_transitions_old_applications(db, user):
    from app.worker import scheduler

    company = Company(name="Silent Co", normalized_name="silentco")
    db.add(company)
    db.flush()
    job = Job(company_id=company.id, title="Engineer", normalized_title="engineer", dedupe_hash="silent-1")
    db.add(job)
    db.flush()
    application = Application(
        user_id=user.id,
        job_id=job.id,
        status=ApplicationStatus.APPLIED,
        applied_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    db.add(application)
    db.commit()

    assert scheduler.mark_no_response() >= 1
    db.expire_all()
    assert db.get(Application, application.id).status == ApplicationStatus.NO_RESPONSE


def test_build_scheduler_registers_every_job():
    from app.worker.scheduler import build_scheduler

    scheduler = build_scheduler()
    assert {job.id for job in scheduler.get_jobs()} == {
        "tick_scheduled_runs",
        "sync_gmail",
        "sync_linkedin",
        "mark_no_response",
        "cleanup_expired_browser_sessions",
    }
    assert str(scheduler.timezone) == "UTC"
    assert not scheduler.running, "build_scheduler() must not start the scheduler"


def test_cleanup_expired_browser_sessions(db, user):
    from app.models.automation import BrowserSession
    from app.models.enums import BrowserSessionStatus
    from app.worker import scheduler

    db.add(
        BrowserSession(
            user_id=user.id,
            source=JobSourceType.DEMO_ATS,
            encrypted_storage_state="secret",
            status=BrowserSessionStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    db.commit()
    assert scheduler.cleanup_expired_browser_sessions() == 1
    db.expire_all()
    row = db.scalars(select(BrowserSession).where(BrowserSession.user_id == user.id)).first()
    assert row.status == BrowserSessionStatus.EXPIRED
    assert row.encrypted_storage_state is None


def test_sync_gmail_is_safe_without_connected_accounts():
    from app.worker.scheduler import sync_gmail

    assert sync_gmail() == 0


# --------------------------------------------------------------------------- locks module


def test_memory_lock_round_trip():
    user_id = uuid.uuid4()
    assert locks.lock_key(user_id) == f"automation:lock:{user_id}"
    token = locks.acquire_lock(user_id, ttl=30)
    assert token is not None
    assert locks.acquire_lock(user_id, ttl=30) is None
    assert locks.is_locked(user_id)
    assert locks.release_lock(user_id, token)
    assert not locks.is_locked(user_id)


def test_user_lock_context_manager_raises_when_held():
    user_id = uuid.uuid4()
    with locks.user_lock(user_id):
        with pytest.raises(ConflictError):
            with locks.user_lock(user_id):
                pass  # pragma: no cover
    assert not locks.is_locked(user_id)


# --------------------------------------------------------------------------- per-source apply mode


def test_resolve_source_mode_defaults_to_the_adapter_capability(db, user):
    config = automation_service.get_config(db, user.id)
    assert config.source_modes in (None, {})
    # LinkedIn's mock adapter supports auto apply; Glassdoor's deliberately does not.
    assert automation_service.resolve_source_mode(config, JobSourceType.LINKEDIN) is SourceApplyMode.AUTO_APPLY
    assert automation_service.resolve_source_mode(config, JobSourceType.DEMO_ATS) is SourceApplyMode.AUTO_APPLY
    assert automation_service.resolve_source_mode(config, JobSourceType.GLASSDOOR) is SourceApplyMode.DISCOVER_ONLY
    # Unknown / unregistered sources can only ever be discovered.
    assert automation_service.resolve_source_mode(config, JobSourceType.WORKDAY) is SourceApplyMode.DISCOVER_ONLY
    assert automation_service.resolve_source_mode(config, None) is SourceApplyMode.DISCOVER_ONLY
    assert automation_service.resolve_source_mode(None, "linkedin") is SourceApplyMode.AUTO_APPLY


def test_resolve_source_mode_honours_a_stored_override(db, user):
    config = automation_service.get_config(db, user.id)
    config.source_modes = {"LINKEDIN": "DISCOVER_ONLY"}
    db.flush()
    assert automation_service.resolve_source_mode(config, JobSourceType.LINKEDIN) is SourceApplyMode.DISCOVER_ONLY
    assert automation_service.resolve_source_mode(config, JobSourceType.NAUKRI) is SourceApplyMode.AUTO_APPLY


def test_resolve_source_mode_never_forces_auto_apply_on_an_unsupported_adapter(db, user, caplog):
    """Rule 3: a stored AUTO_APPLY for an adapter without supports_auto_apply is downgraded."""
    import logging

    config = automation_service.get_config(db, user.id)
    config.source_modes = {"GLASSDOOR": "AUTO_APPLY", "COMPANY_CAREERS": "auto_apply"}
    db.flush()
    with caplog.at_level(logging.DEBUG, logger="app.modules.automation.service"):
        assert automation_service.resolve_source_mode(config, JobSourceType.GLASSDOOR) is SourceApplyMode.DISCOVER_ONLY
        assert automation_service.resolve_source_mode(config, JobSourceType.COMPANY_CAREERS) is SourceApplyMode.DISCOVER_ONLY
    assert any("cannot apply" in record.message for record in caplog.records)


def test_config_read_resolves_source_modes_for_every_registered_source(db, user):
    from app.modules.adapters.registry import ADAPTERS

    config = automation_service.get_config(db, user.id)
    config.source_modes = {"LINKEDIN": "DISCOVER_ONLY"}
    db.flush()
    read = automation_service.to_config_read(config)
    assert set(read.source_modes) == {source.value for source in ADAPTERS}
    assert read.source_modes["LINKEDIN"] is SourceApplyMode.DISCOVER_ONLY
    assert read.source_modes["NAUKRI"] is SourceApplyMode.AUTO_APPLY
    assert read.source_modes["GLASSDOOR"] is SourceApplyMode.DISCOVER_ONLY


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"NOT_A_SOURCE": "AUTO_APPLY"}, "unknown_source"),
        ({"LINKEDIN": "SOMETIMES"}, "invalid_source_mode"),
        ({"GLASSDOOR": "AUTO_APPLY"}, "auto_apply_unsupported"),
    ],
)
def test_source_modes_validation_rejects_bad_values(db, user, payload, code):
    with pytest.raises(ValidationFailed) as excinfo:
        automation_service.update_config(db, user.id, AutomationConfigUpdate(source_modes=payload))
    assert excinfo.value.code == code


def test_source_modes_update_normalises_and_stores(db, user):
    updated = automation_service.update_config(
        db, user.id, AutomationConfigUpdate(source_modes={"linkedin": "discover_only", "GLASSDOOR": "DISCOVER_ONLY"})
    )
    assert updated.source_modes == {"LINKEDIN": "DISCOVER_ONLY", "GLASSDOOR": "DISCOVER_ONLY"}
    snapshot = automation_service.config_snapshot(updated)
    assert snapshot["source_modes"]["LINKEDIN"] == "DISCOVER_ONLY"
    assert snapshot["source_modes"]["NAUKRI"] == "AUTO_APPLY"


def test_config_endpoint_rejects_auto_apply_for_a_mock_only_source(auth_client, api_user):
    response = auth_client.put(f"{API}/config", json={"source_modes": {"GLASSDOOR": "AUTO_APPLY"}})
    assert response.status_code == 422, response.text
    body = response.json()["error"]
    assert body["code"] == "auto_apply_unsupported"
    assert "GLASSDOOR" in body["message"]

    # A legal table round-trips, and the read side fills in every registered source.
    response = auth_client.put(f"{API}/config", json={"source_modes": {"LINKEDIN": "DISCOVER_ONLY"}})
    assert response.status_code == 200, response.text
    modes = response.json()["source_modes"]
    assert modes["LINKEDIN"] == "DISCOVER_ONLY"
    assert modes["NAUKRI"] == "AUTO_APPLY"
    assert modes["GLASSDOOR"] == "DISCOVER_ONLY"
    assert "DEMO_ATS" in modes


def test_discover_only_source_is_scored_but_never_queued(db, user, config, priorities):
    """LinkedIn jobs are ingested and matched; none of them becomes an application."""
    from app.models.job import JobMatch, JobSource

    config.enabled_sources = ["LINKEDIN", "NAUKRI"]
    config.source_modes = {"LINKEDIN": "DISCOVER_ONLY"}
    config.daily_application_limit = 50
    db.flush()

    run = _run(db, user)
    steps = _steps(run)

    assert run.status in (AutomationRunStatus.SUCCESS, AutomationRunStatus.PARTIAL)
    assert run.config_snapshot["source_modes"] == {"LINKEDIN": "DISCOVER_ONLY", "NAUKRI": "AUTO_APPLY"}
    assert steps["search"]["data"]["source_modes"]["LINKEDIN"] == "DISCOVER_ONLY"

    discover_only = steps["queue"]["data"]["discover_only"]
    assert discover_only, "the LinkedIn catalogue must have produced at least one candidate"
    assert run.stats["discover_only"] == len(discover_only)
    assert all(entry["source"] == "LINKEDIN" for entry in discover_only)
    assert all({"job_id", "title", "company", "source"} <= set(entry) for entry in discover_only)
    assert all(entry["source"] != "LINKEDIN" for entry in steps["queue"]["data"]["applications"])
    assert run.stats["queued"] == len(steps["queue"]["data"]["applications"])

    # The discover-only jobs are real: ingested, with a LinkedIn source and a match score.
    linkedin_job_ids = set(db.scalars(select(JobSource.job_id).where(JobSource.source == JobSourceType.LINKEDIN)).all())
    assert {uuid.UUID(entry["job_id"]) for entry in discover_only} <= linkedin_job_ids
    scored = set(db.scalars(select(JobMatch.job_id).where(JobMatch.user_id == user.id)).all())
    assert {uuid.UUID(entry["job_id"]) for entry in discover_only} <= scored

    # ... but no application exists for any of them.
    applications = list(db.scalars(select(Application).where(Application.user_id == user.id)).unique())
    assert applications, "the NAUKRI side of the run must still queue"
    assert all(a.source != JobSourceType.LINKEDIN for a in applications)
    assert {a.job_id for a in applications}.isdisjoint({uuid.UUID(entry["job_id"]) for entry in discover_only})


def test_discover_only_dry_run_reports_both_lists(db, user, config, priorities):
    config.enabled_sources = ["LINKEDIN", "NAUKRI"]
    config.source_modes = {"LINKEDIN": "DISCOVER_ONLY"}
    db.flush()
    run = _run(db, user, dry_run=True)
    data = _steps(run)["queue"]["data"]
    assert data["discover_only"]
    assert all(entry["source"] != "LINKEDIN" for entry in data["would_queue"])
    assert run.stats["discover_only"] == len(data["discover_only"])
    assert run.stats["would_queue"] == len(data["would_queue"])


@pytest.fixture
def greenhouse_catalogue(db, monkeypatch):
    """Make the (normally empty) Greenhouse adapter return one browser-backed posting.

    Board sources are searched only when a company has a board on that vendor, so the
    fixture also registers the posting's company with a Greenhouse board token.
    """
    from datetime import datetime as _dt

    from app.modules.adapters.base import DiscoveredJob
    from app.modules.adapters.greenhouse import GreenhouseAdapter

    def search_jobs(self, query):
        return [
            DiscoveredJob(
                source=JobSourceType.GREENHOUSE,
                external_id="gh-123",
                url="https://boards.greenhouse.io/acme/jobs/123",
                title="Software Engineer",
                company_name="Acme Greenhouse",
                location="Bangalore, India",
                description="React, Node.js and TypeScript on a PostgreSQL stack.",
                required_skills=["React", "Node.js", "TypeScript"],
                posted_at=_dt.now(timezone.utc) - timedelta(hours=2),
                apply_url="https://boards.greenhouse.io/acme/jobs/123#app",
            )
        ]

    monkeypatch.setattr(GreenhouseAdapter, "search_jobs", search_jobs)
    assert GreenhouseAdapter.uses_browser and GreenhouseAdapter.supports_auto_apply
    db.add(
        Company(
            name="Acme Greenhouse",
            normalized_name="acme greenhouse",
            domain="acme-greenhouse.example",
            ats_type="GREENHOUSE",
            ats_board_token="acme",
        )
    )
    db.flush()


def _stub_prepare(monkeypatch) -> list[uuid.UUID]:
    """Record which applications the answers step hands to ``start_application``."""
    prepared: list[uuid.UUID] = []

    def fake_prepare(ctx, application):
        prepared.append(application.id)
        return "prepared"

    monkeypatch.setattr(pipeline, "_prepare_application", fake_prepare)
    return prepared


def test_browser_backed_source_is_prepared_when_the_browser_is_available(db, user, config, greenhouse_catalogue, monkeypatch):
    config.enabled_sources = ["GREENHOUSE"]
    config.min_match_score = 0
    db.flush()
    monkeypatch.setattr(pipeline, "_browser_available", lambda: True)
    prepared = _stub_prepare(monkeypatch)

    run = _run(db, user)
    steps = _steps(run)

    assert run.stats["queued"] == 1
    queued = steps["queue"]["data"]["applications"]
    assert [entry["source"] for entry in queued] == ["GREENHOUSE"]
    assert steps["generate_answers"]["data"]["deferred"] == []
    assert steps["generate_answers"]["data"]["prepared"] == 1
    assert steps["generate_answers"]["data"]["browser_available"] is True
    assert [str(a) for a in prepared] == [queued[0]["application_id"]]
    assert steps["autofill"]["status"] != "SKIPPED" or steps["autofill"]["data"].get("total", 0) == 1
    assert run.config_snapshot["source_modes"] == {"GREENHOUSE": "AUTO_APPLY"}


def test_browser_backed_source_is_deferred_without_a_browser(db, user, config, greenhouse_catalogue, monkeypatch):
    config.enabled_sources = ["GREENHOUSE"]
    config.min_match_score = 0
    db.flush()
    prepared = _stub_prepare(monkeypatch)  # the autouse fixture already says "no browser"

    run = _run(db, user)
    steps = _steps(run)

    assert run.stats["queued"] == 1
    assert prepared == []
    assert len(steps["generate_answers"]["data"]["deferred"]) == 1
    assert steps["generate_answers"]["data"]["prepared"] == 0
    assert "until a browser is available" in steps["generate_answers"]["message"]
    assert steps["autofill"]["status"] == "SKIPPED"
    application = db.scalars(select(Application).where(Application.user_id == user.id)).first()
    assert application.status == ApplicationStatus.QUEUED
    assert application.source == JobSourceType.GREENHOUSE


def test_auto_submit_refuses_an_application_with_a_required_unanswered_question(db, user, config, priorities, monkeypatch):
    """The submit gate is unchanged: anything still NEEDS_USER_INPUT stays put."""
    from app.models.application import ApplicationAnswer
    from app.models.enums import AnswerStatus, FieldType

    # A fixed mock source: board sources (ASHBY, GREENHOUSE...) search only configured boards.
    source = JobSourceType.LINKEDIN.value
    assert JobSourceType.LINKEDIN in automation_service.auto_apply_sources()
    config.enabled_sources = [source]
    config.auto_submit_enabled = True
    config.auto_submit_sources = [source]
    config.daily_application_limit = 1
    db.flush()

    def fake_prepare(ctx, application):
        db.add(
            ApplicationAnswer(
                application_id=application.id,
                question_key="custom:consent",
                question_text="I consent",
                field_type=FieldType.CHECKBOX,
                required=True,
                status=AnswerStatus.NEEDS_USER_INPUT,
            )
        )
        db.flush()
        return "prepared"

    monkeypatch.setattr(pipeline, "_prepare_application", fake_prepare)
    submitted: list[uuid.UUID] = []
    monkeypatch.setattr(pipeline, "_submit_application", lambda ctx, application: submitted.append(application.id) or "submitted")

    run = _run(db, user)
    steps = _steps(run)
    assert run.stats["queued"] == 1
    assert steps["queue"]["data"]["applications"][0]["auto_submit"] is True
    assert submitted == [], "a required NEEDS_USER_INPUT answer must block unattended submission"
    assert len(steps["auto_submit"]["data"]["skipped_needs_input"]) == 1
    assert run.stats["submitted"] == 0
    assert run.stats["requires_user"] == 1
