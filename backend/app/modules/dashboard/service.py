"""Dashboard aggregation (contract §14).

Everything is scoped to the current user. Date bucketing happens in Python after the
rows are fetched so the same code runs on SQLite (tests) and PostgreSQL — no dialect
specific ``date_trunc`` / ``strftime`` anywhere.
"""
from __future__ import annotations

import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.application import Application, ApplicationAnswer, ApplicationEvent
from app.models.audit import AuditLog
from app.models.automation import AutomationRun
from app.models.base import utcnow
from app.models.company import Company
from app.models.email import EmailMessage
from app.models.enums import (
    RESPONSE_STATUSES,
    SUBMITTED_STATUSES,
    AnswerStatus,
    ApplicationStatus,
    AutomationRunStatus,
    AutomationState,
    EmailClassification,
    PauseReason,
)
from app.models.interview import Interview
from app.models.job import Job, JobMatch
from app.models.profile import JobPreference
from app.modules.automation import limits
from app.modules.dashboard.schemas import (
    ActivityItem,
    AttentionItem,
    BucketCount,
    ChartsResponse,
    CompanyCount,
    DayCount,
    FunnelStage,
    PeriodStats,
    SourceCount,
    StatsResponse,
    StatusCount,
    TotalsStats,
)

logger = logging.getLogger(__name__)

HIGH_MATCH_SCORE = 85
DEFAULT_MIN_MATCH_SCORE = 75
RANGE_DAYS: dict[str, int] = {"7d": 7, "30d": 30, "90d": 90}
DEFAULT_RANGE = "30d"
MATCH_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("0-49", 0, 49),
    ("50-69", 50, 69),
    ("70-84", 70, 84),
    ("85-100", 85, 100),
)
#: Emails the user should look at right away.
ATTENTION_CLASSIFICATIONS = (
    EmailClassification.INTERVIEW,
    EmailClassification.OFFER,
    EmailClassification.ASSESSMENT,
)
TOP_COMPANIES = 10

__all__ = ["build_charts", "build_stats", "list_activity"]


# --------------------------------------------------------------------------- row views


@dataclass(frozen=True)
class _AppRow:
    id: uuid.UUID
    job_id: uuid.UUID
    status: ApplicationStatus
    automation_state: AutomationState
    pause_reason: PauseReason | None
    source: str | None
    company: str
    applied_at: datetime | None
    last_response_at: datetime | None
    created_at: datetime | None
    match_score: int | None


def _aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat them as UTC."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _in_window(value: datetime | None, start: datetime, end: datetime) -> bool:
    moment = _aware(value)
    return moment is not None and start <= moment < end


def _load_applications(db: Session, user_id: uuid.UUID) -> list[_AppRow]:
    stmt = (
        select(
            Application.id,
            Application.job_id,
            Application.status,
            Application.automation_state,
            Application.pause_reason,
            Application.source,
            Company.name,
            Application.applied_at,
            Application.last_response_at,
            Application.created_at,
            Application.match_score,
        )
        .select_from(Application)
        .join(Job, Application.job_id == Job.id)
        .join(Company, Job.company_id == Company.id)
        .where(Application.user_id == user_id)
    )
    rows = db.execute(stmt).all()
    return [
        _AppRow(
            id=row[0],
            job_id=row[1],
            status=row[2],
            automation_state=row[3],
            pause_reason=row[4],
            source=row[5].value if hasattr(row[5], "value") else (str(row[5]) if row[5] else None),
            company=row[6] or "Unknown",
            applied_at=_aware(row[7]),
            last_response_at=_aware(row[8]),
            created_at=_aware(row[9]),
            match_score=row[10],
        )
        for row in rows
    ]


def _response_events(db: Session, user_id: uuid.UUID) -> list[tuple[uuid.UUID, ApplicationStatus, datetime]]:
    """``(application_id, to_status, created_at)`` for every transition into a response status."""
    # Filtered in SQL, not in Python: the timeline is the fastest growing table in the
    # schema and only transitions into a response status are ever used here.
    stmt = (
        select(ApplicationEvent.application_id, ApplicationEvent.to_status, ApplicationEvent.created_at)
        .join(Application, ApplicationEvent.application_id == Application.id)
        .where(
            Application.user_id == user_id,
            ApplicationEvent.to_status.in_(tuple(RESPONSE_STATUSES)),
        )
    )
    out = []
    for application_id, to_status, created_at in db.execute(stmt).all():
        moment = _aware(created_at)
        if moment is not None:
            out.append((application_id, to_status, moment))
    return out


def _min_match_score(db: Session, user_id: uuid.UUID) -> int:
    value = db.scalars(select(JobPreference.min_match_score).where(JobPreference.user_id == user_id)).first()
    # ``0`` means "no floor", not "unset" - ``value or DEFAULT`` used to turn it into 75.
    return DEFAULT_MIN_MATCH_SCORE if value is None else int(value)


def _match_scores(db: Session, user_id: uuid.UUID) -> list[int]:
    return [int(s) for s in db.scalars(select(JobMatch.match_score).where(JobMatch.user_id == user_id)).all()]


def _interviews(db: Session, user_id: uuid.UUID) -> list[tuple[uuid.UUID, datetime | None, datetime | None]]:
    stmt = select(Interview.application_id, Interview.scheduled_at, Interview.created_at).where(
        Interview.user_id == user_id
    )
    return [(row[0], _aware(row[1]), _aware(row[2])) for row in db.execute(stmt).all()]


def _jobs_found_in(db: Session, user_id: uuid.UUID, start: datetime, end: datetime) -> int:
    """Jobs that entered the user's universe (i.e. were analyzed for them) in a window."""
    stmt = (
        select(func.count(func.distinct(Job.id)))
        .select_from(Job)
        .join(JobMatch, JobMatch.job_id == Job.id)
        .where(JobMatch.user_id == user_id, Job.created_at >= start, Job.created_at < end)
    )
    return int(db.scalar(stmt) or 0)


# --------------------------------------------------------------------------- stats


def _period(
    applications: list[_AppRow],
    response_events: list[tuple[uuid.UUID, ApplicationStatus, datetime]],
    interviews: list[tuple[uuid.UUID, datetime | None, datetime | None]],
    *,
    start: datetime,
    end: datetime,
    jobs_found: int,
) -> PeriodStats:
    applied = [a for a in applications if _in_window(a.applied_at, start, end)]

    responded: set[uuid.UUID] = {a.id for a in applications if _in_window(a.last_response_at, start, end)}
    rejected: set[uuid.UUID] = {
        a.id
        for a in applications
        if a.status == ApplicationStatus.REJECTED and _in_window(a.last_response_at, start, end)
    }
    for application_id, to_status, moment in response_events:
        if start <= moment < end:
            responded.add(application_id)
            if to_status == ApplicationStatus.REJECTED:
                rejected.add(application_id)

    interview_count = sum(1 for _, scheduled_at, created_at in interviews if _in_window(scheduled_at or created_at, start, end))
    pending = sum(1 for a in applied if a.status == ApplicationStatus.APPLIED and a.last_response_at is None)

    return PeriodStats(
        applications=len(applied),
        responses=len(responded),
        interviews=interview_count,
        rejections=len(rejected),
        pending=pending,
        jobs_found=jobs_found,
    )


def _needs_input_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """Applications with an unanswered **required** question (what actually blocks §11 approve)."""
    stmt = (
        select(ApplicationAnswer.application_id)
        .join(Application, ApplicationAnswer.application_id == Application.id)
        .where(
            Application.user_id == user_id,
            ApplicationAnswer.status == AnswerStatus.NEEDS_USER_INPUT,
            ApplicationAnswer.required.is_(True),
        )
        .distinct()
    )
    return set(db.scalars(stmt).all())


def _has_answers_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    stmt = (
        select(ApplicationAnswer.application_id)
        .join(Application, ApplicationAnswer.application_id == Application.id)
        .where(Application.user_id == user_id)
        .distinct()
    )
    return set(db.scalars(stmt).all())


def _responded_and_interviewed(
    applications: list[_AppRow],
    interviews: list[tuple[uuid.UUID, datetime | None, datetime | None]],
    sent_ids: set[uuid.UUID],
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """``(interviewed, responded)`` — both restricted to applications actually sent.

    Two invariants the dashboard promises depend on this:
    * ``response_rate`` cannot exceed 100% — an application that replied and was then
      SKIPPED from the Jobs page used to stay in the numerator but drop out of ``sent``;
    * the funnel stays monotonic — an interview *is* a response, so a manually created
      ``Interview`` on an APPLIED application must not make ``interviews > responses``.
    """
    interviewed = {application_id for application_id, _, _ in interviews}
    interviewed |= {a.id for a in applications if a.status in (ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER)}
    interviewed &= sent_ids
    responded = {
        a.id
        for a in applications
        if a.id in sent_ids and (a.last_response_at is not None or a.status in RESPONSE_STATUSES)
    }
    responded |= interviewed
    return interviewed, responded


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator * 100.0 / denominator, 1)


def build_stats(db: Session, user_id: uuid.UUID, *, now: datetime | None = None) -> StatsResponse:
    """``GET /dashboard/stats`` — headline numbers plus the "needs you" list."""
    now = now or utcnow()
    from app.modules.automation.service import get_config

    config = get_config(db, user_id)
    zone = limits.resolve_zone(config.timezone)
    day_start, day_end = limits.day_bounds(config.timezone, now)
    week_start = _window_start(day_start, zone, 6)
    month_start = _window_start(day_start, zone, 29)

    applications = _load_applications(db, user_id)
    response_events = _response_events(db, user_id)
    interviews = _interviews(db, user_id)
    min_score = _min_match_score(db, user_id)
    scores = _match_scores(db, user_id)

    today = _period(
        applications, response_events, interviews,
        start=day_start, end=day_end, jobs_found=_jobs_found_in(db, user_id, day_start, day_end),
    )
    week = _period(
        applications, response_events, interviews,
        start=week_start, end=day_end, jobs_found=_jobs_found_in(db, user_id, week_start, day_end),
    )
    month = _period(
        applications, response_events, interviews,
        start=month_start, end=day_end, jobs_found=_jobs_found_in(db, user_id, month_start, day_end),
    )

    needs_input = _needs_input_ids(db, user_id)
    answered = _has_answers_ids(db, user_id)

    sent = [a for a in applications if a.status in SUBMITTED_STATUSES]
    sent_ids = {a.id for a in sent}
    interviewed, responded_total = _responded_and_interviewed(applications, interviews, sent_ids)
    offers = [a for a in applications if a.status == ApplicationStatus.OFFER]
    rejections = [a for a in applications if a.status == ApplicationStatus.REJECTED]

    open_apps = [a for a in applications if a.status in (ApplicationStatus.QUEUED, ApplicationStatus.IN_PROGRESS)]
    requires_input_rows = [
        a for a in open_apps if a.automation_state == AutomationState.REQUIRES_USER or a.id in needs_input
    ]
    requires_input_ids = {a.id for a in requires_input_rows}
    pending_review_rows = [
        a
        for a in open_apps
        if a.id not in requires_input_ids
        and (
            (a.automation_state == AutomationState.PAUSED and a.pause_reason in (PauseReason.USER_REVIEW, None))
            or a.id in answered
        )
    ]

    totals = TotalsStats(
        jobs_found=len(scores),
        jobs_matched=sum(1 for s in scores if s >= min_score),
        high_match=sum(1 for s in scores if s >= HIGH_MATCH_SCORE),
        queued=sum(1 for a in applications if a.status == ApplicationStatus.QUEUED),
        applications=len(sent),
        responses=len(responded_total),
        interviews=len(interviews),
        offers=len(offers),
        rejections=len(rejections),
        pending_review=len(pending_review_rows),
        requires_input=len(requires_input_rows),
    )

    return StatsResponse(
        today=today,
        week=week,
        month=month,
        totals=totals,
        response_rate=_rate(len(responded_total), len(sent)),
        interview_rate=_rate(len(interviewed), len(sent)),
        offer_rate=_rate(len(offers), len(sent)),
        attention=_attention(
            db,
            user_id,
            now=now,
            requires_input=len(requires_input_rows),
            pending_review=len(pending_review_rows),
            day_start=day_start,
            day_end=day_end,
        ),
    )


def _attention(
    db: Session,
    user_id: uuid.UUID,
    *,
    now: datetime,
    requires_input: int,
    pending_review: int,
    day_start: datetime,
    day_end: datetime,
) -> list[AttentionItem]:
    items: list[AttentionItem] = []
    if requires_input:
        items.append(
            AttentionItem(
                type="requires_input",
                title=f"{requires_input} application{'s' if requires_input != 1 else ''} need your input",
                link="/queue",
                count=requires_input,
            )
        )
    if pending_review:
        items.append(
            AttentionItem(
                type="pending_review",
                title=f"{pending_review} application{'s' if pending_review != 1 else ''} ready for review",
                link="/queue",
                count=pending_review,
            )
        )

    upcoming = int(
        db.scalar(
            select(func.count(Interview.id)).where(
                Interview.user_id == user_id,
                Interview.scheduled_at.is_not(None),
                Interview.scheduled_at >= now,
                Interview.scheduled_at < now + timedelta(days=7),
            )
        )
        or 0
    )
    if upcoming:
        items.append(
            AttentionItem(
                type="upcoming_interviews",
                title=f"{upcoming} interview{'s' if upcoming != 1 else ''} in the next 7 days",
                link="/interviews",
                count=upcoming,
            )
        )

    unread_emails = int(
        db.scalar(
            select(func.count(EmailMessage.id)).where(
                EmailMessage.user_id == user_id,
                EmailMessage.is_read.is_(False),
                EmailMessage.classification.in_(ATTENTION_CLASSIFICATIONS),
            )
        )
        or 0
    )
    if unread_emails:
        items.append(
            AttentionItem(
                type="unread_emails",
                title=f"{unread_emails} unread email{'s' if unread_emails != 1 else ''} about interviews or offers",
                link="/emails",
                count=unread_emails,
            )
        )

    failed_runs = int(
        db.scalar(
            select(func.count(AutomationRun.id)).where(
                AutomationRun.user_id == user_id,
                AutomationRun.status.in_((AutomationRunStatus.FAILED, AutomationRunStatus.PARTIAL)),
                AutomationRun.started_at >= day_start,
                AutomationRun.started_at < day_end,
            )
        )
        or 0
    )
    if failed_runs:
        items.append(
            AttentionItem(
                type="failed_runs",
                title=f"{failed_runs} automation run{'s' if failed_runs != 1 else ''} needs attention today",
                link="/automation",
                count=failed_runs,
            )
        )
    return items


# --------------------------------------------------------------------------- charts


def _window_start(day_start: datetime, zone: Any, days_back: int) -> datetime:
    """Local midnight ``days_back`` days before today, as a UTC instant.

    ``day_start - timedelta(days=N)`` is N x 24h, which lands on 01:00 (or 23:00) local
    across a DST change and then silently drops the first day of the window.
    """
    today_local = day_start.astimezone(zone).date()
    return datetime.combine(today_local - timedelta(days=days_back), time.min, tzinfo=zone).astimezone(timezone.utc)


def _day_series(counter: Counter[date], start_day: date, end_day: date) -> list[DayCount]:
    out: list[DayCount] = []
    cursor = start_day
    while cursor <= end_day:
        out.append(DayCount(date=cursor, count=int(counter.get(cursor, 0))))
        cursor += timedelta(days=1)
    return out


def build_charts(db: Session, user_id: uuid.UUID, range_: str = DEFAULT_RANGE, *, now: datetime | None = None) -> ChartsResponse:
    """``GET /dashboard/charts`` — per-day series plus the funnel and distributions."""
    now = now or utcnow()
    days = RANGE_DAYS.get((range_ or DEFAULT_RANGE).lower(), RANGE_DAYS[DEFAULT_RANGE])
    range_key = (range_ or DEFAULT_RANGE).lower() if (range_ or "").lower() in RANGE_DAYS else DEFAULT_RANGE

    from app.modules.automation.service import get_config

    config = get_config(db, user_id)
    zone = limits.resolve_zone(config.timezone)
    day_start, day_end = limits.day_bounds(config.timezone, now)
    window_start = _window_start(day_start, zone, days - 1)

    applications = _load_applications(db, user_id)
    response_events = _response_events(db, user_id)
    interviews = _interviews(db, user_id)
    scores = _match_scores(db, user_id)
    min_score = _min_match_score(db, user_id)

    applied_per_day: Counter[date] = Counter()
    responses_per_day: Counter[date] = Counter()
    seen_response: set[tuple[uuid.UUID, date]] = set()

    for row in applications:
        if _in_window(row.applied_at, window_start, day_end) and row.applied_at is not None:
            applied_per_day[row.applied_at.astimezone(zone).date()] += 1
        if _in_window(row.last_response_at, window_start, day_end) and row.last_response_at is not None:
            key = (row.id, row.last_response_at.astimezone(zone).date())
            if key not in seen_response:
                seen_response.add(key)
                responses_per_day[key[1]] += 1
    for application_id, _status, moment in response_events:
        if window_start <= moment < day_end:
            key = (application_id, moment.astimezone(zone).date())
            if key not in seen_response:
                seen_response.add(key)
                responses_per_day[key[1]] += 1

    sent = [a for a in applications if a.status in SUBMITTED_STATUSES]
    by_company = Counter(a.company for a in sent)
    by_source = Counter(a.source or "UNKNOWN" for a in sent)
    by_status: Counter[str] = Counter()
    for row in applications:
        by_status[row.status.value if hasattr(row.status, "value") else str(row.status)] += 1

    sent_ids = {a.id for a in sent}
    interviewed, responded_total = _responded_and_interviewed(applications, interviews, sent_ids)
    queued_or_beyond = [a for a in applications if a.status != ApplicationStatus.DISCOVERED and a.status != ApplicationStatus.SKIPPED]

    funnel = [
        FunnelStage(stage="discovered", count=len(scores)),
        FunnelStage(stage="matched", count=sum(1 for s in scores if s >= min_score)),
        FunnelStage(stage="queued", count=len(queued_or_beyond)),
        FunnelStage(stage="applied", count=len(sent)),
        FunnelStage(stage="responses", count=len(responded_total)),
        FunnelStage(stage="interviews", count=len(interviewed)),
        FunnelStage(stage="offers", count=sum(1 for a in applications if a.status == ApplicationStatus.OFFER)),
    ]

    distribution: list[BucketCount] = []
    for label, low, high in MATCH_BUCKETS:
        distribution.append(BucketCount(bucket=label, count=sum(1 for s in scores if low <= s <= high)))

    return ChartsResponse(
        range=range_key,
        start_date=window_start.astimezone(zone).date(),
        end_date=(day_end - timedelta(seconds=1)).astimezone(zone).date(),
        applications_per_day=_day_series(applied_per_day, window_start.astimezone(zone).date(), (day_end - timedelta(seconds=1)).astimezone(zone).date()),
        responses_per_day=_day_series(responses_per_day, window_start.astimezone(zone).date(), (day_end - timedelta(seconds=1)).astimezone(zone).date()),
        by_company=[CompanyCount(name=name, count=count) for name, count in by_company.most_common(TOP_COMPANIES)],
        by_source=[SourceCount(source=source, count=count) for source, count in by_source.most_common()],
        by_status=[StatusCount(status=status, count=count) for status, count in by_status.most_common()],
        funnel=funnel,
        match_distribution=distribution,
    )


# --------------------------------------------------------------------------- activity


def _audit_link(row: AuditLog) -> str | None:
    if row.application_id:
        return f"/applications/{row.application_id}"
    if row.automation_run_id:
        return "/automation"
    return None


def list_activity(db: Session, user_id: uuid.UUID, limit: int = 30) -> list[ActivityItem]:
    """``GET /dashboard/activity`` — audit entries and application events, newest first."""
    limit = max(1, min(200, int(limit or 30)))

    audit_rows = list(
        db.scalars(
            select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.created_at.desc()).limit(limit)
        )
    )
    event_rows = list(
        db.execute(
            select(ApplicationEvent)
            .join(Application, ApplicationEvent.application_id == Application.id)
            .where(Application.user_id == user_id)
            .order_by(ApplicationEvent.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    items: list[ActivityItem] = [
        ActivityItem(
            id=row.id,
            kind="AUDIT",
            action=row.action,
            actor=row.actor,
            level=row.level.value if hasattr(row.level, "value") else str(row.level),
            message=row.message,
            application_id=row.application_id,
            automation_run_id=row.automation_run_id,
            link=_audit_link(row),
            metadata=dict(row.meta or {}),
            created_at=_aware(row.created_at) or utcnow(),
        )
        for row in audit_rows
    ]
    items += [
        ActivityItem(
            id=row.id,
            kind="EVENT",
            action=row.event_type.value if hasattr(row.event_type, "value") else str(row.event_type),
            actor=row.actor,
            level="INFO",
            message=row.message,
            application_id=row.application_id,
            from_status=row.from_status.value if row.from_status is not None else None,
            to_status=row.to_status.value if row.to_status is not None else None,
            link=f"/applications/{row.application_id}",
            metadata=dict(row.meta or {}),
            created_at=_aware(row.created_at) or utcnow(),
        )
        for row in event_rows
    ]
    items.sort(key=lambda item: item.created_at, reverse=True)
    return items[:limit]
