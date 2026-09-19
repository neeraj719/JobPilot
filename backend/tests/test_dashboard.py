"""Dashboard tests (contract §14): stats, charts and the merged activity timeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.audit import audit
from app.models.application import Application, ApplicationAnswer, ApplicationEvent
from app.models.company import Company
from app.models.email import EmailMessage
from app.models.enums import (
    Actor,
    AnswerStatus,
    ApplicationEventType,
    ApplicationStatus,
    AutomationRunStatus,
    AutomationRunTrigger,
    AutomationState,
    CompanyPriority,
    EmailClassification,
    FieldType,
    InterviewStatus,
    InterviewType,
    JobSourceType,
    PauseReason,
)
from app.models.interview import Interview
from app.models.job import Job, JobMatch
from app.models.profile import JobPreference
from app.models.user import User
from app.modules.dashboard import service as dashboard

API = "/api/v1/dashboard"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def user(db) -> User:
    from app.modules.auth.service import create_user

    row = create_user(db, "dashboard-tester@example.com", "StrongPass123!", "Dashboard Tester")
    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == row.id)).first()
    preference.min_match_score = 75
    db.flush()
    return row


@pytest.fixture
def world(db, user):
    """A small, fully deterministic dataset: 6 jobs, 5 applications, 1 interview, 1 email."""
    now = datetime.now(timezone.utc)
    companies = {}
    jobs: list[Job] = []
    for index, name in enumerate(["Google", "Microsoft", "Amazon", "Flipkart", "Zoho", "Swiggy"]):
        company = Company(name=name, normalized_name=name.lower())
        db.add(company)
        db.flush()
        companies[name] = company
        job = Job(
            company_id=company.id,
            title=f"Software Engineer {index}",
            normalized_title="software engineer",
            description="React, Node.js, PostgreSQL",
            dedupe_hash=f"dash-{index}",
            posted_at=now - timedelta(hours=index + 1),
        )
        db.add(job)
        db.flush()
        jobs.append(job)
        db.add(
            JobMatch(
                job_id=job.id,
                user_id=user.id,
                match_score=[92, 88, 80, 72, 60, 40][index],
                company_priority=CompanyPriority.P2,
                analyzed_at=now,
            )
        )
    db.flush()

    def make(job: Job, status: ApplicationStatus, *, days_ago: int, responded: bool, source: JobSourceType) -> Application:
        applied_at = now - timedelta(days=days_ago, hours=2)
        application = Application(
            user_id=user.id,
            job_id=job.id,
            status=status,
            source=source,
            match_score=80,
            applied_at=applied_at,
            last_response_at=applied_at + timedelta(days=1) if responded else None,
            automation_state=AutomationState.SUCCESS,
        )
        db.add(application)
        db.flush()
        db.add(
            ApplicationEvent(
                application_id=application.id,
                event_type=ApplicationEventType.SUBMITTED,
                actor=Actor.AUTOMATION,
                to_status=ApplicationStatus.APPLIED,
                message="submitted",
                created_at=applied_at,
            )
        )
        if responded:
            db.add(
                ApplicationEvent(
                    application_id=application.id,
                    event_type=ApplicationEventType.STATUS_CHANGED,
                    actor=Actor.EMAIL,
                    from_status=ApplicationStatus.APPLIED,
                    to_status=status,
                    message="responded",
                    created_at=applied_at + timedelta(days=1),
                )
            )
        db.flush()
        return application

    applied = make(jobs[0], ApplicationStatus.APPLIED, days_ago=0, responded=False, source=JobSourceType.LINKEDIN)
    received = make(jobs[1], ApplicationStatus.APPLICATION_RECEIVED, days_ago=3, responded=True, source=JobSourceType.LINKEDIN)
    interviewing = make(jobs[2], ApplicationStatus.INTERVIEW, days_ago=6, responded=True, source=JobSourceType.NAUKRI)
    rejected = make(jobs[3], ApplicationStatus.REJECTED, days_ago=10, responded=True, source=JobSourceType.NAUKRI)
    offer = make(jobs[4], ApplicationStatus.OFFER, days_ago=15, responded=True, source=JobSourceType.DEMO_ATS)

    # One queued item ready for review and one that needs the user.
    ready = Application(
        user_id=user.id,
        job_id=jobs[5].id,
        status=ApplicationStatus.QUEUED,
        source=JobSourceType.DEMO_ATS,
        automation_state=AutomationState.PAUSED,
        pause_reason=PauseReason.USER_REVIEW,
        match_score=90,
    )
    db.add(ready)
    db.flush()

    db.add(
        Interview(
            application_id=interviewing.id,
            user_id=user.id,
            interview_type=InterviewType.TECHNICAL,
            status=InterviewStatus.SCHEDULED,
            scheduled_at=now + timedelta(days=2),
        )
    )
    db.add(
        EmailMessage(
            user_id=user.id,
            application_id=interviewing.id,
            provider_message_id="dash-email-1",
            sender="talent@amazon.com",
            sender_domain="amazon.com",
            subject="Interview scheduled",
            body_text="Your interview is confirmed",
            received_at=now - timedelta(days=1),
            classification=EmailClassification.INTERVIEW,
            is_read=False,
            created_at=now - timedelta(days=1),
        )
    )
    audit(db, action="automation.run_started", message="Automation run started", user_id=user.id, actor=Actor.AUTOMATION)
    db.flush()
    return {
        "jobs": jobs,
        "applied": applied,
        "received": received,
        "interview": interviewing,
        "rejected": rejected,
        "offer": offer,
        "ready": ready,
    }


# --------------------------------------------------------------------------- stats


def test_stats_totals_and_rates(db, user, world):
    stats = dashboard.build_stats(db, user.id)

    assert stats.totals.jobs_found == 6
    assert stats.totals.jobs_matched == 3  # 92, 88, 80 are >= 75
    assert stats.totals.high_match == 2  # 92, 88 are >= 85
    assert stats.totals.applications == 5  # the five submitted ones
    assert stats.totals.responses == 4
    assert stats.totals.interviews == 1
    assert stats.totals.offers == 1
    assert stats.totals.rejections == 1
    assert stats.totals.queued == 1
    assert stats.totals.pending_review == 1

    assert stats.response_rate == 80.0
    assert stats.interview_rate == 40.0  # INTERVIEW + OFFER reached the interview stage
    assert stats.offer_rate == 20.0


def test_stats_periods(db, user, world):
    stats = dashboard.build_stats(db, user.id)

    assert stats.today.applications == 1
    assert stats.today.pending == 1  # applied today, no response yet
    assert stats.week.applications == 3  # today, 3 days ago, 6 days ago
    assert stats.month.applications == 5
    assert stats.month.responses == 4
    assert stats.month.rejections == 1
    assert stats.month.jobs_found == 6


def test_stats_attention_items(db, user, world):
    stats = dashboard.build_stats(db, user.id)
    by_type = {item.type: item for item in stats.attention}

    assert by_type["pending_review"].count == 1
    assert by_type["pending_review"].link == "/queue"
    assert by_type["upcoming_interviews"].count == 1
    assert by_type["upcoming_interviews"].link == "/interviews"
    assert by_type["unread_emails"].count == 1
    assert by_type["unread_emails"].link == "/emails"


def test_attention_lists_required_unanswered_questions(db, user, world):
    application = world["ready"]
    db.add(
        ApplicationAnswer(
            application_id=application.id,
            order=0,
            question_key="custom:start_date",
            question_text="Preferred start date?",
            field_type=FieldType.TEXT,
            required=True,
            status=AnswerStatus.NEEDS_USER_INPUT,
        )
    )
    db.flush()
    stats = dashboard.build_stats(db, user.id)
    by_type = {item.type: item.count for item in stats.attention}
    assert by_type.get("requires_input") == 1
    assert by_type.get("pending_review", 0) == 0  # it is blocked, not ready


def test_attention_flags_failed_runs_today(db, user, world):
    from app.models.automation import AutomationRun

    db.add(
        AutomationRun(
            user_id=user.id,
            trigger=AutomationRunTrigger.SCHEDULED,
            status=AutomationRunStatus.FAILED,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            error="boom",
        )
    )
    db.flush()
    stats = dashboard.build_stats(db, user.id)
    by_type = {item.type: item for item in stats.attention}
    assert by_type["failed_runs"].count == 1
    assert by_type["failed_runs"].link == "/automation"


def test_stats_are_scoped_to_the_current_user(db, user, world):
    from app.modules.auth.service import create_user

    other = create_user(db, "not-me@example.com", "StrongPass123!", "Not Me")
    db.flush()
    stats = dashboard.build_stats(db, other.id)
    assert stats.totals.applications == 0
    assert stats.totals.jobs_found == 0
    assert stats.attention == []


def test_stats_on_an_empty_account(db, user):
    stats = dashboard.build_stats(db, user.id)
    assert stats.totals.applications == 0
    assert stats.response_rate == 0.0
    assert stats.today.applications == 0


# --------------------------------------------------------------------------- charts


def test_charts_series_and_buckets(db, user, world):
    charts = dashboard.build_charts(db, user.id, "30d")

    assert charts.range == "30d"
    assert len(charts.applications_per_day) == 30
    assert sum(point.count for point in charts.applications_per_day) == 5
    assert sum(point.count for point in charts.responses_per_day) == 4

    funnel = {stage.stage: stage.count for stage in charts.funnel}
    assert list(funnel) == ["discovered", "matched", "queued", "applied", "responses", "interviews", "offers"]
    assert funnel["discovered"] == 6
    assert funnel["matched"] == 3
    assert funnel["applied"] == 5
    assert funnel["offers"] == 1

    distribution = {bucket.bucket: bucket.count for bucket in charts.match_distribution}
    assert distribution == {"0-49": 1, "50-69": 1, "70-84": 2, "85-100": 2}

    by_source = {row.source: row.count for row in charts.by_source}
    assert by_source[JobSourceType.LINKEDIN.value] == 2
    assert by_source[JobSourceType.NAUKRI.value] == 2
    by_company = {row.name for row in charts.by_company}
    assert {"Google", "Microsoft", "Amazon"} <= by_company

    statuses = {row.status for row in charts.by_status}
    assert ApplicationStatus.QUEUED.value in statuses


def test_charts_range_window(db, user, world):
    week = dashboard.build_charts(db, user.id, "7d")
    assert len(week.applications_per_day) == 7
    assert sum(point.count for point in week.applications_per_day) == 3
    quarter = dashboard.build_charts(db, user.id, "90d")
    assert len(quarter.applications_per_day) == 90
    # An unknown range falls back to the default instead of blowing up.
    assert dashboard.build_charts(db, user.id, "bogus").range == "30d"


# --------------------------------------------------------------------------- activity


def test_activity_merges_audit_and_events(db, user, world):
    items = dashboard.list_activity(db, user.id, limit=50)
    kinds = {item.kind for item in items}
    assert kinds == {"AUDIT", "EVENT"}
    assert any(item.action == "automation.run_started" for item in items)
    assert any(item.action == ApplicationEventType.SUBMITTED.value for item in items)
    timestamps = [item.created_at for item in items]
    assert timestamps == sorted(timestamps, reverse=True)
    assert all(item.link is not None for item in items if item.application_id)


def test_activity_respects_the_limit(db, user, world):
    assert len(dashboard.list_activity(db, user.id, limit=3)) == 3


# --------------------------------------------------------------------------- API


@pytest.fixture
def api_world(auth_client, db):
    """The auth_client's user with one submitted application."""
    user = db.scalars(select(User).where(User.email == "tester@example.com")).first()
    company = Company(name="Api Co", normalized_name="apico")
    db.add(company)
    db.flush()
    job = Job(company_id=company.id, title="Engineer", normalized_title="engineer", dedupe_hash="api-1")
    db.add(job)
    db.flush()
    db.add(JobMatch(job_id=job.id, user_id=user.id, match_score=90, analyzed_at=datetime.now(timezone.utc)))
    db.add(
        Application(
            user_id=user.id,
            job_id=job.id,
            status=ApplicationStatus.APPLIED,
            source=JobSourceType.LINKEDIN,
            applied_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return user


def test_stats_endpoint(auth_client, api_world):
    response = auth_client.get(f"{API}/stats")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["totals"]["applications"] == 1
    assert body["today"]["applications"] == 1
    assert set(body["today"]) == {"applications", "responses", "interviews", "rejections", "pending", "jobs_found"}
    assert isinstance(body["attention"], list)


def test_charts_endpoint(auth_client, api_world):
    response = auth_client.get(f"{API}/charts", params={"range": "7d"})
    assert response.status_code == 200
    body = response.json()
    assert body["range"] == "7d"
    assert len(body["applications_per_day"]) == 7
    assert len(body["match_distribution"]) == 4
    assert auth_client.get(f"{API}/charts", params={"range": "1y"}).status_code == 422


def test_activity_endpoint(auth_client, api_world):
    response = auth_client.get(f"{API}/activity", params={"limit": 5})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_dashboard_requires_authentication(client):
    assert client.get(f"{API}/stats").status_code == 401
    assert client.get(f"{API}/charts").status_code == 401
    assert client.get(f"{API}/activity").status_code == 401
