"""Seed script tests (contract §14): it must run on SQLite, be idempotent, and leave a live dashboard."""
from __future__ import annotations

import io
from datetime import timezone

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models.base import utcnow
from app.models.application import Application, ApplicationAnswer, ApplicationEvent
from app.models.audit import AuditLog
from app.models.automation import AutomationConfig, AutomationRun
from app.models.email import EmailMessage
from app.models.enums import (
    AnswerStatus,
    ApplicationStatus,
    AutomationRunStatus,
    AutomationState,
    CompanyPriority,
    ResumeParseStatus,
)
from app.models.interview import Interview
from app.models.job import Job, JobMatch
from app.models.notification import Notification
from app.models.profile import CompanyPreference, JobPreference, UserProfile
from app.models.resume import Resume, Skill
from app.models.user import User
from app.modules.dashboard import service as dashboard
from app.seed import DEMO_TIMEZONE, HISTORY_MIX, QUEUE_SIZE, TODAY_APPLICATIONS, build_resume_pdf, seed_demo_data


@pytest.fixture(scope="module")
def _quiet_browser():
    """The seed never needs a browser; nothing here touches Playwright."""
    yield


@pytest.fixture
def seeded(db):
    summary = seed_demo_data(db, force=False)
    db.flush()
    return summary


def _demo_user(db) -> User:
    return db.scalars(select(User).where(User.email == settings.DEMO_USER_EMAIL)).first()


def _utc(value):
    """SQLite hands datetimes back naive; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- the PDF writer


def test_build_resume_pdf_is_readable_by_pypdf():
    from pypdf import PdfReader

    data = build_resume_pdf()
    assert data.startswith(b"%PDF-")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    for fragment in ("Aarav Sharma", "Northwind Labs", "React", "PostgreSQL", "B.Tech", "JobTracker", "AWS Certified"):
        assert fragment in text


# --------------------------------------------------------------------------- the seed itself


def test_seed_creates_the_demo_user_and_profile(db, seeded):
    assert seeded.created is True
    user = _demo_user(db)
    assert user is not None and user.id == seeded.user_id
    assert user.full_name == "Aarav Sharma"

    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == user.id)).first()
    assert profile.years_of_experience == 2.0
    assert profile.city == "Bangalore"
    assert profile.current_salary == 800_000
    assert profile.requires_sponsorship is False
    assert profile.work_authorization.get("IN") is True
    assert {"React", "Node.js", "TypeScript", "PostgreSQL", "Docker", "AWS"} <= set(profile.skills)

    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == user.id)).first()
    assert preference.min_match_score == 75
    assert preference.notice_period_days == 30
    assert preference.desired_salary == 1_200_000
    assert "Bangalore" in preference.preferred_locations and "Remote" in preference.preferred_locations


def test_seed_sets_company_priorities(db, seeded):
    user = _demo_user(db)
    rows = {
        row.company_name: row.priority
        for row in db.scalars(select(CompanyPreference).where(CompanyPreference.user_id == user.id))
    }
    assert rows["Google"] == CompanyPriority.P1
    assert rows["Microsoft"] == CompanyPriority.P1
    assert CompanyPriority.P3 in rows.values()
    assert CompanyPriority.AVOID in rows.values()


def test_seed_builds_a_parsed_default_resume(db, seeded):
    user = _demo_user(db)
    resume = db.scalars(select(Resume).where(Resume.user_id == user.id)).first()
    assert resume is not None
    assert resume.is_default is True
    assert resume.mime_type == "application/pdf"
    assert resume.parse_status == ResumeParseStatus.PARSED, resume.parse_error
    assert resume.text_content and "Aarav Sharma" in resume.text_content
    assert resume.parsed_data.get("skills")
    assert resume.current_version == 1


def test_seed_discovers_and_analyzes_jobs(db, seeded):
    user = _demo_user(db)
    assert seeded.jobs > 20
    assert db.scalar(select(func.count(Job.id))) == seeded.jobs
    analyzed = db.scalar(select(func.count(JobMatch.id)).where(JobMatch.user_id == user.id))
    assert analyzed == seeded.jobs
    assert db.scalar(select(func.count(Skill.id))) > 50


def test_seed_history_has_the_documented_status_mix(db, seeded):
    user = _demo_user(db)
    counts = dict(
        db.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.user_id == user.id)
            .group_by(Application.status)
        ).all()
    )
    for status, expected in HISTORY_MIX:
        assert counts.get(status, 0) == expected, f"{status} should appear {expected} times"
    assert counts.get(ApplicationStatus.QUEUED, 0) == QUEUE_SIZE
    assert sum(counts.values()) == sum(count for _s, count in HISTORY_MIX) + QUEUE_SIZE

    # Every application carries its transition events.
    events = db.scalar(select(func.count(ApplicationEvent.id)))
    assert events >= sum(count for _s, count in HISTORY_MIX)


def test_seed_queue_has_a_ready_item_and_one_needing_input(db, seeded):
    user = _demo_user(db)
    queue = list(
        db.scalars(
            select(Application).where(Application.user_id == user.id, Application.status == ApplicationStatus.QUEUED)
        ).unique()
    )
    assert len(queue) == QUEUE_SIZE
    assert any(a.automation_state == AutomationState.PAUSED and a.form_snapshot for a in queue)

    needs_user = [a for a in queue if a.automation_state == AutomationState.REQUIRES_USER]
    assert needs_user, "the demo needs one REQUIRES_USER example"
    unanswered = db.scalars(
        select(ApplicationAnswer).where(
            ApplicationAnswer.application_id == needs_user[0].id,
            ApplicationAnswer.status == AnswerStatus.NEEDS_USER_INPUT,
        )
    ).all()
    assert unanswered, "the paused application must show what the user has to supply"
    assert all(answer.answer is None for answer in unanswered), "the assistant must never invent the missing fact"


def test_seed_creates_interviews_emails_notifications_and_a_run(db, seeded):
    user = _demo_user(db)
    interviews = list(db.scalars(select(Interview).where(Interview.user_id == user.id)))
    assert len(interviews) >= 2
    assert any(interview.prep_material for interview in interviews)

    assert db.scalar(select(func.count(EmailMessage.id)).where(EmailMessage.user_id == user.id)) >= 8
    notifications = list(db.scalars(select(Notification).where(Notification.user_id == user.id)))
    assert len(notifications) >= 5
    assert {n.is_read for n in notifications} == {True, False}, "notifications should be a read/unread mix"

    runs = list(db.scalars(select(AutomationRun).where(AutomationRun.user_id == user.id)))
    assert len(runs) == 1
    run = runs[0]
    assert run.status == AutomationRunStatus.SUCCESS
    assert run.finished_at is not None
    assert run.stats["jobs_found"] > 0
    assert [step["step"] for step in run.steps][-1] == "finish"


def test_seed_writes_the_audit_story_for_one_application(db, seeded):
    user = _demo_user(db)
    story = {
        "job.found",
        "job.analyzed",
        "application.created",
        "application.answers_generated",
        "application.form_detected",
        "application.field_filled",
        "application.paused",
        "application.resumed",
        "application.approved",
        "application.submitted",
    }
    actions = set(db.scalars(select(AuditLog.action).where(AuditLog.user_id == user.id)).all())
    assert story <= actions


def test_seed_enables_the_automation_config(db, seeded):
    user = _demo_user(db)
    config = db.scalars(select(AutomationConfig).where(AutomationConfig.user_id == user.id)).first()
    assert config.enabled is True
    assert config.schedule_time == "09:00"
    assert config.timezone == "Asia/Kolkata"
    assert config.daily_application_limit == 20
    assert config.min_match_score == 75
    assert config.auto_submit_enabled is False
    assert config.next_run_at is not None


def test_seed_dates_a_few_applications_earlier_today(db, seeded):
    from app.modules.automation.limits import day_bounds

    user = _demo_user(db)
    now = utcnow()
    day_start, day_end = day_bounds(DEMO_TIMEZONE, now)
    applied = [
        _utc(row.applied_at)
        for row in db.scalars(
            select(Application).where(Application.user_id == user.id, Application.applied_at.is_not(None))
        ).unique()
    ]
    today = [moment for moment in applied if day_start <= moment < day_end]
    assert len(today) == TODAY_APPLICATIONS
    assert all(moment <= now for moment in today), "no application may be dated in the future"
    assert len(applied) > len(today), "the rest of the history still spans the previous weeks"


def test_seed_is_idempotent(db, seeded):
    before = db.scalar(select(func.count(Application.id)))
    again = seed_demo_data(db, force=False)
    assert again.created is False
    assert again.user_id == seeded.user_id
    assert db.scalar(select(func.count(Application.id))) == before


def test_seed_force_rebuilds_the_demo_user(db, seeded):
    original_user_id = seeded.user_id
    rebuilt = seed_demo_data(db, force=True)
    db.flush()
    assert rebuilt.created is True
    assert rebuilt.user_id != original_user_id
    assert db.scalar(select(func.count(User.id)).where(User.email == settings.DEMO_USER_EMAIL)) == 1
    assert db.scalar(select(func.count(Application.id)).where(Application.user_id == original_user_id)) == 0
    assert rebuilt.applications == sum(count for _s, count in HISTORY_MIX)


# --------------------------------------------------------------------------- the payoff


def test_dashboard_is_alive_after_seeding(db, seeded):
    user = _demo_user(db)
    stats = dashboard.build_stats(db, user.id)

    assert stats.totals.jobs_found > 0
    assert stats.totals.jobs_matched > 0
    assert stats.totals.applications == sum(count for _s, count in HISTORY_MIX)
    assert stats.totals.responses > 0
    assert stats.totals.offers == 1
    assert stats.totals.queued == QUEUE_SIZE
    assert stats.response_rate > 0
    assert stats.month.applications > 0
    assert stats.attention, "the demo must have something waiting for the user"

    # "Applications Today" must not greet a fresh demo account with a zero.
    assert stats.today.applications == TODAY_APPLICATIONS
    assert stats.week.applications >= stats.today.applications

    charts = dashboard.build_charts(db, user.id, "30d")
    assert sum(point.count for point in charts.applications_per_day) > 0
    assert sum(point.count for point in charts.responses_per_day) > 0
    assert charts.by_company and charts.by_source
    assert sum(bucket.count for bucket in charts.match_distribution) == stats.totals.jobs_found

    assert len(dashboard.list_activity(db, user.id, limit=20)) == 20


def test_demo_login_works_through_the_api(client, db):
    seed_demo_data(db, force=False)
    db.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    stats = client.get("/api/v1/dashboard/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["totals"]["applications"] > 0

    charts = client.get("/api/v1/dashboard/charts", headers=headers, params={"range": "30d"})
    assert charts.status_code == 200
    assert any(stage["count"] > 0 for stage in charts.json()["funnel"])

    config = client.get("/api/v1/automation/config", headers=headers)
    assert config.status_code == 200
    assert config.json()["enabled"] is True
