"""Application lifecycle service (CONTRACTS.md section 11).

Everything an application does - queueing, answer preparation, pausing for a human,
approval, submission and status tracking - lives here. The router is a thin shell and
the browser runner calls straight into these functions, so there is exactly one place
where an application's state can change.

Safety rails honoured throughout:

* nothing is ever submitted without either an explicit human approval or an
  explicitly enabled auto-submit source;
* an application with a required ``NEEDS_USER_INPUT`` answer cannot be submitted;
* a company on the user's AVOID list can neither be queued nor submitted;
* every automated step writes an audit entry and an application event.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import audit
from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationFailed
from app.models.application import Application, ApplicationAnswer, ApplicationDocument, ApplicationEvent
from app.models.automation import AutomationConfig
from app.models.base import utcnow
from app.models.company import Company
from app.models.enums import (
    RESPONSE_STATUSES,
    SUBMITTED_STATUSES,
    Actor,
    AnswerStatus,
    ApplicationEventType,
    ApplicationStatus,
    ApplicationType,
    AuditLevel,
    AutomationState,
    CompanyPriority,
    DocumentType,
    InterviewStatus,
    InterviewType,
    JobSourceType,
    NotificationType,
    PauseReason,
)
from app.models.interview import Interview
from app.models.job import Job, JobMatch
from app.models.user import User
from app.modules.applications import answers as answers_engine
from app.modules.applications.questions import FormQuestion
from app.modules.applications.review import SUBMITTABLE_STATUSES, build_review, review_counts
from app.modules.applications.schemas import ApplicationRead, QueueItem, ReviewCounts
from app.modules.common.pagination import Pagination, paginate_sequence
from app.modules.common.schemas import PageResponse
from app.modules.notifications.service import notify

logger = logging.getLogger(__name__)

#: Order companies are worked through in the queue.
PRIORITY_RANK: dict[CompanyPriority, int] = {
    CompanyPriority.P1: 0,
    CompanyPriority.P2: 1,
    CompanyPriority.P3: 2,
    CompanyPriority.AVOID: 9,
}

#: Statuses that appear on the queue screen.
QUEUE_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.QUEUED, ApplicationStatus.IN_PROGRESS}
)

#: Once here, only a deliberate user action may move the application on.
TERMINAL_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.REJECTED, ApplicationStatus.OFFER, ApplicationStatus.WITHDRAWN}
)

#: Reachable from anywhere, by anyone.
ALWAYS_REACHABLE: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.WITHDRAWN, ApplicationStatus.SKIPPED}
)

#: Response status -> the notification the user gets.
STATUS_NOTIFICATIONS: dict[ApplicationStatus, NotificationType] = {
    ApplicationStatus.INTERVIEW: NotificationType.INTERVIEW_SCHEDULED,
    ApplicationStatus.OFFER: NotificationType.OFFER,
    ApplicationStatus.REJECTED: NotificationType.REJECTION,
    ApplicationStatus.ASSESSMENT: NotificationType.ASSESSMENT_RECEIVED,
    ApplicationStatus.RECRUITER_CONTACTED: NotificationType.RECRUITER_RESPONSE,
}

#: Application types that get a generated cover letter when the config asks for one.
COVER_LETTER_TYPES: frozenset[ApplicationType] = frozenset(
    {ApplicationType.ATS_FORM, ApplicationType.EXTERNAL_FORM}
)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- small helpers


def job_label(job: Job | None) -> str:
    if job is None:
        return "an application"
    company = getattr(getattr(job, "company", None), "name", None) or "Unknown company"
    return f"{company} - {job.title}"


def application_link(application: Application) -> str:
    return f"/applications/{application.id}"


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return _EPOCH
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def get_automation_config(db: Session, user_id: uuid.UUID) -> AutomationConfig:
    """The user's automation settings, creating the default row when it is missing."""
    config = db.scalars(select(AutomationConfig).where(AutomationConfig.user_id == user_id)).first()
    if config is None:
        config = AutomationConfig(
            user_id=user_id,
            daily_application_limit=settings.DEFAULT_DAILY_APPLICATION_LIMIT,
            min_match_score=settings.DEFAULT_MIN_MATCH_SCORE,
            retry_limit=settings.AUTOMATION_RETRY_LIMIT,
            delay_between_actions_seconds=settings.AUTOMATION_DELAY_SECONDS,
        )
        db.add(config)
        db.flush()
        logger.info("Created default automation config for user %s", user_id)
    return config


def get_company_priority(db: Session, user_id: uuid.UUID, company: Company | None) -> CompanyPriority:
    """``companies.service.get_priority`` with a safe default."""
    if company is None:
        return CompanyPriority.P2
    try:
        from app.modules.companies.service import get_priority

        return get_priority(db, user_id, company)
    except Exception as exc:  # noqa: BLE001 - never fail an application over a lookup
        logger.debug("companies.service.get_priority unavailable (%s); defaulting to P2", exc)
        return CompanyPriority.P2


def apply_source_rank(source: JobSourceType) -> int:
    try:
        from app.modules.jobs.service import apply_rank

        return apply_rank(source)
    except Exception:  # pragma: no cover - jobs module always present in practice
        return 8


def pick_apply_source(job: Job) -> JobSourceType | None:
    """The channel an application should actually be submitted through.

    Hosted ATS forms and company career sites beat aggregators, and a source whose
    ``apply_url`` is the one stored on the job wins its rank tie.
    """
    sources = list(job.sources or [])
    if not sources:
        return None
    job_apply_url = (job.apply_url or "").strip()

    def sort_key(row: Any) -> tuple[int, int, int, str]:
        return (
            apply_source_rank(row.source),
            0 if (job_apply_url and row.apply_url == job_apply_url) else 1,
            0 if row.apply_url else 1,
            str(row.source),
        )

    return sorted(sources, key=sort_key)[0].source


def build_candidate(db: Session, application: Application) -> Any:
    """The flattened candidate view for this application's resume."""
    from app.modules.profiles.service import build_candidate_context

    return build_candidate_context(db, application.user_id, application.resume_id)


# --------------------------------------------------------------------------- lookups


def get_application(db: Session, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    """One application, always scoped to its owner."""
    application = db.scalars(
        select(Application)
        .where(Application.id == application_id, Application.user_id == user_id)
        .options(selectinload(Application.answers), selectinload(Application.events))
    ).first()
    if application is None:
        raise NotFoundError("Application not found")
    return application


def is_ready(application: Application) -> bool:
    """"Ready" in the queue: answers prepared and nothing waiting on the user."""
    rows = list(application.answers or [])
    if not rows:
        return False
    if any(r.required and r.status == AnswerStatus.NEEDS_USER_INPUT for r in rows):
        return False
    return application.status in SUBMITTABLE_STATUSES


def to_read(application: Application) -> ApplicationRead:
    """ORM row -> ``ApplicationRead`` with the denormalised job fields filled in."""
    read = ApplicationRead.model_validate(application)
    job = getattr(application, "job", None)
    if job is not None:
        company = getattr(job, "company", None)
        read.job_title = job.title
        read.company_name = getattr(company, "name", None)
        read.company_logo_url = getattr(company, "logo_url", None)
        read.location = job.location
        read.application_type = job.application_type
    read.ready = is_ready(application)
    return read


# --------------------------------------------------------------------------- events & audit


def record_event(
    db: Session,
    application: Application,
    event_type: ApplicationEventType,
    message: str,
    *,
    actor: Actor = Actor.SYSTEM,
    meta: dict[str, Any] | None = None,
    from_status: ApplicationStatus | None = None,
    to_status: ApplicationStatus | None = None,
) -> ApplicationEvent:
    """Append one entry to the application's timeline."""
    event = ApplicationEvent(
        application_id=application.id,
        event_type=event_type,
        actor=actor,
        from_status=from_status,
        to_status=to_status,
        message=message[:4000],
        meta=meta or {},
        created_at=utcnow(),
    )
    db.add(event)
    if application.events is not None:
        application.events.append(event)
    db.flush()
    return event


# --------------------------------------------------------------------------- transitions


def _validate_transition(current: ApplicationStatus, new_status: ApplicationStatus, actor: Actor) -> None:
    if new_status in ALWAYS_REACHABLE:
        return
    if current in TERMINAL_STATUSES and actor != Actor.USER:
        raise ConflictError(
            f"Application is {current.value}; only a manual action can move it to {new_status.value}",
            code="terminal_status",
        )


def ensure_interview(db: Session, application: Application, *, source_email_id: uuid.UUID | None = None) -> Interview:
    """An application in INTERVIEW always has at least one interview row."""
    existing = list(application.interviews or [])
    if existing:
        return existing[0]
    interview = Interview(
        application_id=application.id,
        user_id=application.user_id,
        interview_type=InterviewType.OTHER,
        status=InterviewStatus.SCHEDULED,
        scheduled_at=None,
        source_email_id=source_email_id,
    )
    db.add(interview)
    if application.interviews is not None:
        application.interviews.append(interview)
    db.flush()
    logger.info("Created placeholder interview %s for application %s", interview.id, application.id)
    return interview


def transition(
    db: Session,
    application: Application,
    new_status: ApplicationStatus | str,
    *,
    actor: Actor = Actor.SYSTEM,
    message: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Application:
    """Move an application to ``new_status``, recording the event and side effects."""
    target = ApplicationStatus(str(new_status))
    current = application.status
    if target == current:
        application.last_update_at = utcnow()
        db.flush()
        return application

    _validate_transition(current, target, actor)
    application.status = target
    application.last_update_at = utcnow()
    if target in RESPONSE_STATUSES:
        application.last_response_at = utcnow()
    if target == ApplicationStatus.APPLIED and application.applied_at is None:
        application.applied_at = utcnow()
    if target not in QUEUE_STATUSES:
        application.queue_position = None

    text = message or f"Status changed from {current.value} to {target.value}"
    record_event(
        db,
        application,
        ApplicationEventType.STATUS_CHANGED,
        text,
        actor=actor,
        meta=meta,
        from_status=current,
        to_status=target,
    )

    if target == ApplicationStatus.INTERVIEW:
        ensure_interview(db, application)

    notification_type = STATUS_NOTIFICATIONS.get(target)
    if notification_type is not None:
        notify(
            db,
            application.user_id,
            notification_type,
            f"{job_label(application.job)}: {target.value.replace('_', ' ').title()}",
            body=text,
            link=application_link(application),
            meta={"application_id": str(application.id), "status": target.value},
        )

    audit(
        db,
        action="application.status_changed",
        message=f"{job_label(application.job)}: {current.value} -> {target.value}",
        user_id=application.user_id,
        application_id=application.id,
        actor=actor,
        meta={"from": current.value, "to": target.value, **(meta or {})},
    )
    db.flush()
    logger.info("Application %s: %s -> %s (%s)", application.id, current.value, target.value, actor.value)
    return application


# --------------------------------------------------------------------------- automation state


def pause(
    db: Session,
    application: Application,
    reason: PauseReason,
    message: str,
    *,
    form_snapshot: dict[str, Any] | None = None,
) -> Application:
    """Stop the automation and hand control back to the human (never bypass)."""
    application.automation_state = AutomationState.REQUIRES_USER
    application.pause_reason = reason
    application.pause_message = message[:4000]
    if form_snapshot is not None:
        application.form_snapshot = form_snapshot
    record_event(
        db,
        application,
        ApplicationEventType.PAUSED,
        message,
        actor=Actor.AUTOMATION,
        meta={"pause_reason": reason.value},
    )
    notify(
        db,
        application.user_id,
        NotificationType.INPUT_REQUIRED,
        f"Action needed: {job_label(application.job)}",
        body=message,
        link=application_link(application),
        meta={"application_id": str(application.id), "pause_reason": reason.value},
    )
    audit(
        db,
        action="application.paused",
        message=f"Paused ({reason.value}): {message}",
        user_id=application.user_id,
        application_id=application.id,
        actor=Actor.AUTOMATION,
        level=AuditLevel.WARN,
        meta={"pause_reason": reason.value},
    )
    db.flush()
    logger.info("Application %s paused: %s", application.id, reason.value)
    return application


def await_review(db: Session, application: Application, message: str, *, form_snapshot: dict[str, Any] | None = None) -> Application:
    """Everything is filled in - wait for the human to press Submit."""
    application.automation_state = AutomationState.PAUSED
    application.pause_reason = PauseReason.USER_REVIEW
    application.pause_message = message[:4000]
    application.review_required = True
    if form_snapshot is not None:
        application.form_snapshot = form_snapshot
    record_event(
        db,
        application,
        ApplicationEventType.PAUSED,
        message,
        actor=Actor.AUTOMATION,
        meta={"pause_reason": PauseReason.USER_REVIEW.value},
    )
    notify(
        db,
        application.user_id,
        NotificationType.SYSTEM,
        "Application ready for review",
        body=f"{job_label(application.job)} is filled in and waiting for your approval.",
        link=application_link(application),
        meta={"application_id": str(application.id)},
    )
    audit(
        db,
        action="application.paused",
        message=f"Ready for review: {job_label(application.job)}",
        user_id=application.user_id,
        application_id=application.id,
        actor=Actor.AUTOMATION,
        meta={"pause_reason": PauseReason.USER_REVIEW.value},
    )
    db.flush()
    return application


def mark_failed(db: Session, application: Application, error: str, *, final: bool = False) -> Application:
    """Record an automation failure; retries until ``retry_limit`` is exhausted."""
    config = get_automation_config(db, application.user_id)
    application.retry_count = int(application.retry_count or 0) + 1
    application.last_error = (error or "")[:4000]
    exhausted = final or application.retry_count >= max(1, int(config.retry_limit or 1))
    application.automation_state = AutomationState.FAILED if exhausted else AutomationState.RETRYING
    record_event(
        db,
        application,
        ApplicationEventType.ERROR,
        error[:4000],
        actor=Actor.AUTOMATION,
        meta={"retry_count": application.retry_count, "state": application.automation_state.value},
    )
    audit(
        db,
        action="application.failed",
        message=f"{job_label(application.job)}: {error}"[:2000],
        user_id=application.user_id,
        application_id=application.id,
        actor=Actor.AUTOMATION,
        level=AuditLevel.ERROR,
        meta={"retry_count": application.retry_count, "final": exhausted},
    )
    if exhausted:
        notify(
            db,
            application.user_id,
            NotificationType.AUTOMATION_FAILED,
            f"Automation failed: {job_label(application.job)}",
            body=error[:500],
            link=application_link(application),
            meta={"application_id": str(application.id)},
        )
    db.flush()
    logger.warning("Application %s failed (%s): %s", application.id, application.automation_state.value, error)
    return application


def _is_past_applied(status: ApplicationStatus | None) -> bool:
    """True when ``status`` is *further along* the funnel than ``APPLIED``.

    Uses the emails module's ``STATUS_ORDER`` (the single definition of "further along"),
    imported lazily because emails imports this module.
    """
    if status is None:
        return False
    if status in TERMINAL_STATUSES:
        return True
    try:
        from app.modules.emails.service import status_rank

        return status_rank(status) > status_rank(ApplicationStatus.APPLIED)
    except Exception:  # pragma: no cover - emails module always present in practice
        return status in RESPONSE_STATUSES


def mark_submitted(
    db: Session,
    application: Application,
    *,
    external_application_id: str | None = None,
    confirmation_message: str | None = None,
    via: str = "AUTOMATION",
) -> Application:
    """The application really went out: record the reference and move to APPLIED."""
    application.external_application_id = (external_application_id or None) and str(external_application_id)[:255]
    application.confirmation_message = confirmation_message
    application.submitted_via = via
    application.applied_at = application.applied_at or utcnow()
    application.automation_state = AutomationState.SUCCESS
    application.pause_reason = None
    application.pause_message = None
    application.last_error = None
    application.review_required = False

    actor = Actor.USER if via == "MANUAL" else Actor.AUTOMATION
    record_event(
        db,
        application,
        ApplicationEventType.SUBMITTED,
        confirmation_message or f"Application submitted via {via.lower()}",
        actor=actor,
        meta={"external_application_id": application.external_application_id, "via": via},
    )
    if _is_past_applied(application.status):
        # An ATS confirmation email can land while the submission is still finishing (the
        # linker deliberately accepts IN_PROGRESS applications) - never walk the status back.
        logger.info("Application %s is already %s; keeping it", application.id, application.status.value)
        application.last_update_at = utcnow()
        db.flush()
    else:
        transition(
            db,
            application,
            ApplicationStatus.APPLIED,
            actor=actor,
            message=f"Submitted to {job_label(application.job)}",
            meta={"via": via},
        )
    notify(
        db,
        application.user_id,
        NotificationType.APPLICATION_SUBMITTED,
        f"Applied: {job_label(application.job)}",
        body=confirmation_message,
        link=application_link(application),
        meta={"application_id": str(application.id), "external_application_id": application.external_application_id},
    )
    audit(
        db,
        action="application.submitted",
        message=f"Submitted {job_label(application.job)}"
        + (f" (ref {application.external_application_id})" if application.external_application_id else ""),
        user_id=application.user_id,
        application_id=application.id,
        actor=actor,
        meta={"via": via, "external_application_id": application.external_application_id},
    )
    db.flush()
    logger.info("Application %s submitted via %s", application.id, via)
    return application


# --------------------------------------------------------------------------- queueing


def _match_score(db: Session, user_id: uuid.UUID, job: Job) -> int | None:
    score = db.scalars(
        select(JobMatch.match_score).where(JobMatch.job_id == job.id, JobMatch.user_id == user_id)
    ).first()
    if score is not None:
        return int(score)
    try:
        from app.modules.matching.service import analyze_job

        match = analyze_job(db, user_id, job)
        return int(match.match_score)
    except Exception as exc:  # noqa: BLE001 - a missing score must not block queueing
        logger.warning("Could not analyze job %s for user %s: %s", job.id, user_id, exc)
        return None


def recompute_queue_positions(db: Session, user_id: uuid.UUID) -> None:
    """Renumber the queue: P1 first, then match score, then freshest posting."""
    rows = db.execute(
        select(Application, Job).join(Job, Application.job_id == Job.id).where(Application.user_id == user_id)
    ).unique().all()
    open_rows = [(a, j) for a, j in rows if a.status in QUEUE_STATUSES]
    closed_rows = [a for a, _ in rows if a.status not in QUEUE_STATUSES]
    ordered = sorted(
        open_rows,
        key=lambda row: (
            PRIORITY_RANK.get(row[0].priority, 5),
            -int(row[0].match_score or 0),
            -_aware(row[1].posted_at).timestamp(),
            str(row[0].id),
        ),
    )
    for position, (application, _job) in enumerate(ordered, start=1):
        application.queue_position = position
    for application in closed_rows:
        application.queue_position = None
    db.flush()


def queue_job(
    db: Session,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    *,
    run_id: uuid.UUID | None = None,
    priority: CompanyPriority | None = None,
    auto_submit: bool = False,
) -> Application:
    """Queue ``job_id`` for ``user_id`` (idempotent). AVOID companies are refused."""
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found")

    resolved_priority = priority or get_company_priority(db, user_id, job.company)
    if resolved_priority == CompanyPriority.AVOID:
        raise ConflictError("Company is on your avoid list", code="company_avoided")

    existing = db.scalars(
        select(Application).where(Application.user_id == user_id, Application.job_id == job_id)
    ).first()
    if existing is not None:
        if existing.status in {ApplicationStatus.DISCOVERED, ApplicationStatus.SKIPPED}:
            existing.status = ApplicationStatus.QUEUED
            existing.skipped_reason = None
            existing.last_update_at = utcnow()
            record_event(
                db,
                existing,
                ApplicationEventType.CREATED,
                f"Re-queued {job_label(job)}",
                actor=Actor.USER,
            )
        if run_id is not None and existing.automation_run_id is None:
            existing.automation_run_id = run_id
        recompute_queue_positions(db, user_id)
        db.flush()
        logger.info("Application %s already exists for job %s", existing.id, job_id)
        return existing

    resume_id = _default_resume_id(db, user_id)
    application = Application(
        user_id=user_id,
        job_id=job_id,
        resume_id=resume_id,
        automation_run_id=run_id,
        status=ApplicationStatus.QUEUED,
        priority=resolved_priority,
        match_score=_match_score(db, user_id, job),
        source=pick_apply_source(job),
        automation_state=AutomationState.IDLE,
        auto_submit=bool(auto_submit),
        review_required=True,
        form_snapshot={},
        last_update_at=utcnow(),
    )
    db.add(application)
    db.flush()

    record_event(
        db,
        application,
        ApplicationEventType.CREATED,
        f"Queued {job_label(job)}",
        actor=Actor.SCHEDULER if run_id else Actor.USER,
        meta={"source": application.source.value if application.source else None, "priority": resolved_priority.value},
    )
    audit(
        db,
        action="application.created",
        message=f"Queued {job_label(job)}",
        user_id=user_id,
        application_id=application.id,
        automation_run_id=run_id,
        actor=Actor.SCHEDULER if run_id else Actor.USER,
        meta={"job_id": str(job_id), "priority": resolved_priority.value, "match_score": application.match_score},
    )
    recompute_queue_positions(db, user_id)
    logger.info("Queued application %s for job %s (user %s)", application.id, job_id, user_id)
    return application


def _default_resume_id(db: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    try:
        from app.modules.resumes.service import get_default_resume

        resume = get_default_resume(db, user_id)
    except Exception as exc:  # noqa: BLE001 - resumes are optional for queueing
        logger.debug("Could not resolve the default resume for %s: %s", user_id, exc)
        return None
    return getattr(resume, "id", None)


# --------------------------------------------------------------------------- preparation


def generate_application_answers(db: Session, application: Application) -> list[ApplicationAnswer]:
    """(Re)generate answers, keeping everything the user typed."""
    candidate = build_candidate(db, application)
    return answers_engine.generate_answers(db, application, candidate)


def generate_cover_letter(db: Session, application: Application) -> str:
    """Compose a cover letter from the profile + posting (no invented facts)."""
    from app.modules.ai import tasks as ai_tasks

    candidate = build_candidate(db, application)
    letter = ai_tasks.generate_cover_letter(application.job, candidate)
    save_cover_letter(db, application, letter, actor=Actor.AUTOMATION)
    return letter


def save_cover_letter(db: Session, application: Application, content: str, *, actor: Actor = Actor.USER) -> str:
    text = (content or "").strip()
    application.cover_letter = text or None
    document = ApplicationDocument(
        application_id=application.id,
        resume_id=application.resume_id,
        document_type=DocumentType.COVER_LETTER,
        filename=f"cover-letter-{application.id}.txt",
        content=text or None,
        created_at=utcnow(),
    )
    db.add(document)
    if application.documents is not None:
        application.documents.append(document)
    record_event(
        db,
        application,
        ApplicationEventType.NOTE,
        "Cover letter saved" if actor == Actor.USER else "Cover letter generated",
        actor=actor,
        meta={"length": len(text)},
    )
    db.flush()
    return text


def start_application(
    db: Session,
    application_id: uuid.UUID,
    user_id: uuid.UUID,
    run_in_background: bool = True,
) -> Application:
    """Prepare an application and hand it to the browser/adapter runner."""
    from app.modules.applications import executor

    application = get_application(db, user_id, application_id)
    if application.status in SUBMITTED_STATUSES:
        raise ConflictError("This application has already been submitted", code="already_submitted")
    if executor.is_running(application.id):
        raise ConflictError("This application is already being processed", code="already_running")

    if application.resume_id is None:
        application.resume_id = _default_resume_id(db, user_id)

    transition(
        db,
        application,
        ApplicationStatus.IN_PROGRESS,
        actor=Actor.USER,
        message=f"Started preparing {job_label(application.job)}",
    )
    application.automation_state = AutomationState.RUNNING
    application.pause_reason = None
    application.pause_message = None
    application.last_error = None

    candidate = build_candidate(db, application)
    answers_engine.generate_answers(db, application, candidate)

    config = get_automation_config(db, user_id)
    job_type = getattr(application.job, "application_type", ApplicationType.UNKNOWN)
    if config.auto_generate_cover_letters and job_type in COVER_LETTER_TYPES and not application.cover_letter:
        try:
            from app.modules.ai import tasks as ai_tasks

            save_cover_letter(db, application, ai_tasks.generate_cover_letter(application.job, candidate), actor=Actor.AUTOMATION)
        except Exception as exc:  # noqa: BLE001 - a cover letter is never worth failing over
            logger.warning("Cover letter generation failed for %s: %s", application.id, exc)

    db.flush()
    if run_in_background:
        db.commit()  # the worker thread opens its own session and must see this row
        executor.run_in_background(application.id)
    else:
        executor.run_now(application.id, db=db)
        db.refresh(application)
    return application


def resume_automation(
    db: Session,
    application: Application,
    answers: Sequence[Any] | None = None,
    *,
    run_in_background: bool = True,
) -> Application:
    """Continue after the user resolved a pause (answered a question, did a CAPTCHA)."""
    from app.modules.applications import executor

    if answers:
        answers_engine.save_user_answers(db, application, answers)
    application.automation_state = AutomationState.RUNNING
    application.pause_reason = None
    application.pause_message = None
    if application.status not in SUBMITTED_STATUSES:
        transition(
            db,
            application,
            ApplicationStatus.IN_PROGRESS,
            actor=Actor.USER,
            message="Automation resumed",
        )
    record_event(db, application, ApplicationEventType.RESUMED, "Automation resumed by you", actor=Actor.USER)
    audit(
        db,
        action="application.resumed",
        message=f"Automation resumed for {job_label(application.job)}",
        user_id=application.user_id,
        application_id=application.id,
        actor=Actor.USER,
    )
    db.flush()
    if run_in_background:
        db.commit()
        executor.run_in_background(application.id)
    else:
        executor.run_now(application.id, db=db)
        db.refresh(application)
    return application


# --------------------------------------------------------------------------- approval


def _apply_context(db: Session, application: Application, page: Any = None) -> Any:
    from app.modules.adapters.base import ApplyContext

    return ApplyContext(
        application=application,
        job=application.job,
        candidate=build_candidate(db, application),
        answers=list(application.answers or []),
        page=page,
        db=db,
        settings=settings,
    )


def _submit_through_adapter(db: Session, application: Application) -> Any:
    """Run the adapter's submit step, re-opening a browser session when one is needed."""
    from app.modules.adapters.base import ApplyStepResult
    from app.modules.adapters.registry import get_adapter

    source = application.source or pick_apply_source(application.job)
    if source is None:
        return ApplyStepResult(state=AutomationState.FAILED, message="This job has no source to apply through")
    adapter = get_adapter(source)

    if not adapter.uses_browser:
        return adapter.submit_application(_apply_context(db, application))

    from app.modules.browser.session import BrowserSessionHandle, is_browser_available

    if not is_browser_available():
        return ApplyStepResult(
            state=AutomationState.FAILED,
            message="A browser is required to submit this application but Chromium is not available here",
        )

    with BrowserSessionHandle(application.user_id, source, db) as handle:
        ctx = _apply_context(db, application, page=handle.page)
        opened = adapter.start_application(ctx)
        if opened.state != AutomationState.SUCCESS:
            return opened
        # The hosted form is stateless, so re-filling with the now-complete answers is safe.
        filled = adapter.fill_application(ctx)
        if filled.state != AutomationState.SUCCESS:
            return filled
        if filled.form_snapshot:
            application.form_snapshot = filled.form_snapshot
        result = adapter.submit_application(ctx)
        result.screenshot_path = handle.screenshot("after_submit", application.id) or result.screenshot_path
        return result


def approve(db: Session, application: Application, user: User) -> Application:
    """Human-in-the-loop submission. Refuses anything the review flags as a blocker."""
    review = build_review(db, application)
    if not review.can_submit:
        raise ValidationFailed(
            "This application is not ready to submit",
            code="review_blocked",
            details={"blockers": review.blockers, "missing": review.missing},
        )

    application.approved_at = utcnow()
    application.review_required = False
    application.automation_state = AutomationState.RUNNING
    record_event(
        db,
        application,
        ApplicationEventType.APPROVED,
        f"Approved by {user.email}",
        actor=Actor.USER,
    )
    audit(
        db,
        action="application.approved",
        message=f"Approved {job_label(application.job)}",
        user_id=application.user_id,
        application_id=application.id,
        actor=Actor.USER,
    )
    db.flush()
    # Submitting drives a real browser and takes seconds. Commit the approval first so the
    # write transaction is not held open across it: the ATS answers in the same process
    # (the bundled demo ATS writes its confirmation email) and a held writer would block it.
    db.commit()

    try:
        result = _submit_through_adapter(db, application)
    except Exception as exc:  # noqa: BLE001 - surface a clean error, never a traceback
        logger.exception("Submission crashed for application %s", application.id)
        mark_failed(db, application, f"{type(exc).__name__}: {exc}", final=True)
        db.commit()  # keep the failure record; get_db would roll it back
        raise AppError(f"Could not submit this application: {exc}", code="submit_failed") from exc

    if result.state == AutomationState.SUCCESS:
        # End the snapshot the browser step read under and pick up anything that happened
        # meanwhile - typically the ATS confirmation email that already moved us forward.
        db.commit()
        db.refresh(application)
        return mark_submitted(
            db,
            application,
            external_application_id=result.external_application_id,
            confirmation_message=result.confirmation_message or result.message,
            via="AUTOMATION",
        )

    if result.state == AutomationState.REQUIRES_USER:
        pause(
            db,
            application,
            result.pause_reason or PauseReason.OTHER,
            result.message or "The application needs your input before it can be submitted",
            form_snapshot=result.form_snapshot,
        )
        record_snapshot_questions(db, application, result.form_snapshot)
        db.flush()
        return application

    mark_failed(db, application, result.message or "Submission failed", final=True)
    db.commit()  # keep the failure record; get_db would roll it back
    raise AppError(
        result.message or "Could not submit this application",
        code="submit_failed",
        details={"state": result.state.value},
    )


def record_snapshot_questions(db: Session, application: Application, snapshot: dict[str, Any] | None) -> list[ApplicationAnswer]:
    """Turn the unanswered required fields of a form snapshot into answer rows."""
    questions = questions_from_snapshot(snapshot, application)
    if not questions:
        return []
    candidate = build_candidate(db, application)
    return answers_engine.generate_answers(db, application, candidate, questions=questions)


def questions_from_snapshot(snapshot: dict[str, Any] | None, application: Application) -> list[FormQuestion]:
    """Extract the questions a paused form is still waiting on.

    Reads both shapes the adapters produce: the ``fields`` list of the ATS snapshot and
    the ``needs_user`` rows ``browser.autofill`` reports.
    """
    from app.models.enums import FieldType

    if not isinstance(snapshot, dict):
        return []
    answered_keys = {
        row.question_key
        for row in (application.answers or [])
        if row.status == AnswerStatus.ANSWERED and row.answer
    }
    seen: set[str] = set()
    questions: list[FormQuestion] = []

    def add(key: str | None, label: str | None, field_type: Any, required: Any, selector: str | None, options: Any = ()) -> None:
        resolved_key = (key or "").strip()
        if not resolved_key:
            from app.modules.ai.answer_rules import infer_question_key

            resolved_key = infer_question_key(label or "", str(field_type or ""))
        if resolved_key in seen or resolved_key in answered_keys:
            return
        seen.add(resolved_key)
        try:
            resolved_type = FieldType(str(field_type).split(".")[-1].upper()) if field_type else FieldType.TEXT
        except ValueError:
            resolved_type = FieldType.TEXT
        option_labels: list[str] = []
        for option in options or []:
            if isinstance(option, dict):
                option_labels.append(str(option.get("label") or option.get("value") or ""))
            else:
                option_labels.append(str(option))
        questions.append(
            FormQuestion(
                key=resolved_key,
                text=(label or resolved_key).strip(),
                field_type=resolved_type,
                options=[o for o in option_labels if o],
                required=bool(required),
                selector=selector,
            )
        )

    for row in snapshot.get("fields") or []:
        if not isinstance(row, dict) or not row.get("required"):
            continue
        if row.get("value") not in (None, ""):
            continue
        add(row.get("key") or row.get("mapped_to"), row.get("label"), row.get("field_type"), True, row.get("selector"), row.get("options"))

    for row in snapshot.get("needs_user") or []:
        if not isinstance(row, dict):
            continue
        add(row.get("key"), row.get("label"), row.get("field_type"), row.get("required", True), row.get("selector"), row.get("options"))

    return questions


# --------------------------------------------------------------------------- user actions


def skip(db: Session, application: Application, reason: str | None = None) -> Application:
    application.skipped_reason = (reason or "")[:500] or None
    application.automation_state = AutomationState.IDLE
    application.pause_reason = None
    application.pause_message = None
    transition(
        db,
        application,
        ApplicationStatus.SKIPPED,
        actor=Actor.USER,
        message=reason or "Skipped by you",
    )
    recompute_queue_positions(db, application.user_id)
    return application


def withdraw(db: Session, application: Application, reason: str | None = None) -> Application:
    transition(
        db,
        application,
        ApplicationStatus.WITHDRAWN,
        actor=Actor.USER,
        message=reason or "Withdrawn by you",
    )
    recompute_queue_positions(db, application.user_id)
    return application


def update_application(db: Session, application: Application, payload: Any) -> Application:
    """``PATCH /applications/{id}`` - notes, next action, resume swap."""
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else dict(payload or {})
    if "resume_id" in data and data["resume_id"] is not None:
        from app.modules.resumes.service import get_resume

        get_resume(db, application.user_id, data["resume_id"])  # raises when it is not theirs
    for field_name in ("notes", "next_action", "next_action_due", "resume_id"):
        if field_name in data:
            setattr(application, field_name, data[field_name])
    application.last_update_at = utcnow()
    record_event(db, application, ApplicationEventType.USER_ACTION, "Application details updated", actor=Actor.USER, meta=_jsonable(data))
    db.flush()
    return application


def set_status(db: Session, application: Application, new_status: ApplicationStatus, note: str | None = None) -> Application:
    """Manual status change from the UI (actor ``USER``)."""
    return transition(
        db,
        application,
        new_status,
        actor=Actor.USER,
        message=note or f"Status set to {ApplicationStatus(str(new_status)).value} by you",
        meta={"manual": True},
    )


def _jsonable(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, (uuid.UUID, datetime)):
            out[key] = str(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        else:
            out[key] = str(value)
    return out


# --------------------------------------------------------------------------- listings


def _list_statement(user_id: uuid.UUID) -> Select[Any]:
    return (
        select(Application)
        .join(Job, Application.job_id == Job.id)
        .join(Company, Job.company_id == Company.id)
        .where(Application.user_id == user_id)
        .options(selectinload(Application.answers))
    )


def list_applications(
    db: Session,
    user_id: uuid.UUID,
    pagination: Pagination,
    *,
    status: ApplicationStatus | None = None,
    source: JobSourceType | None = None,
    company: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = None,
    sort: str | None = None,
) -> PageResponse[ApplicationRead]:
    """``GET /applications`` with every section 11 filter applied."""
    stmt = _list_statement(user_id)
    if status is not None:
        stmt = stmt.where(Application.status == status)
    if source is not None:
        stmt = stmt.where(Application.source == source)
    if company:
        stmt = stmt.where(Company.name.ilike(f"%{company.strip()}%"))
    if date_from is not None:
        stmt = stmt.where(Application.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Application.created_at <= date_to)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(or_(Job.title.ilike(needle), Company.name.ilike(needle), Application.notes.ilike(needle)))

    rows = list(db.scalars(stmt).unique().all())
    rows = _sort_applications(rows, sort)
    page = paginate_sequence(rows, pagination)
    return PageResponse[ApplicationRead](
        items=[to_read(row) for row in page.items],
        total=page.total,
        page=page.page,
        page_size=page.page_size,
    )


def _sort_applications(rows: list[Application], sort: str | None) -> list[Application]:
    key = (sort or "recent").lower()
    if key in {"score", "match"}:
        return sorted(rows, key=lambda a: (-(a.match_score or 0), -_aware(a.created_at).timestamp()))
    if key == "company":
        return sorted(rows, key=lambda a: (getattr(getattr(a.job, "company", None), "name", "") or "").lower())
    if key == "applied":
        return sorted(rows, key=lambda a: -_aware(a.applied_at or a.created_at).timestamp())
    if key == "priority":
        return sorted(rows, key=lambda a: (PRIORITY_RANK.get(a.priority, 5), -(a.match_score or 0)))
    return sorted(rows, key=lambda a: -_aware(a.last_update_at or a.updated_at or a.created_at).timestamp())


def list_queue(
    db: Session,
    user_id: uuid.UUID,
    pagination: Pagination,
    *,
    priority: CompanyPriority | None = None,
    status: ApplicationStatus | None = None,
    ready_only: bool = False,
) -> PageResponse[QueueItem]:
    """``GET /applications/queue`` ordered by (priority, match score, posting age)."""
    stmt = _list_statement(user_id).where(Application.status.in_(tuple(QUEUE_STATUSES)))
    if priority is not None:
        stmt = stmt.where(Application.priority == priority)
    if status is not None:
        stmt = stmt.where(Application.status == status)
    rows = list(db.scalars(stmt).unique().all())
    if ready_only:
        rows = [row for row in rows if is_ready(row)]
    ordered = sorted(
        rows,
        key=lambda a: (
            PRIORITY_RANK.get(a.priority, 5),
            -int(a.match_score or 0),
            -_aware(getattr(a.job, "posted_at", None)).timestamp(),
            str(a.id),
        ),
    )
    page = paginate_sequence(ordered, pagination)
    job_cards = _job_cards(db, user_id, [row.job_id for row in page.items])
    items = [
        QueueItem(
            application=to_read(row),
            job=job_cards.get(row.job_id),
            position=row.queue_position or (page.page - 1) * page.page_size + index + 1,
        )
        for index, row in enumerate(page.items)
    ]
    return PageResponse[QueueItem](items=items, total=page.total, page=page.page, page_size=page.page_size)


def _job_cards(db: Session, user_id: uuid.UUID, job_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Any]:
    """Job cards for the queue, via the jobs module (best effort)."""
    out: dict[uuid.UUID, Any] = {}
    try:
        from app.modules.jobs.service import get_job_detail
    except Exception as exc:  # pragma: no cover - jobs module always present
        logger.debug("jobs.service.get_job_detail unavailable: %s", exc)
        return out
    for job_id in job_ids:
        try:
            out[job_id] = get_job_detail(db, user_id, job_id)
        except Exception as exc:  # noqa: BLE001 - one bad job must not break the page
            logger.warning("Could not build a job card for %s: %s", job_id, exc)
    return out


def review_summary(db: Session, user_id: uuid.UUID) -> ReviewCounts:
    """``GET /applications/review-summary``."""
    rows = list(
        db.scalars(
            select(Application)
            .where(Application.user_id == user_id, Application.status.in_(tuple(QUEUE_STATUSES)))
            .options(selectinload(Application.answers))
        )
        .unique()
        .all()
    )
    return ReviewCounts(**review_counts(rows))


def list_events(db: Session, application: Application) -> list[ApplicationEvent]:
    return sorted(application.events or [], key=lambda e: _aware(e.created_at))


def build_detail(db: Session, user_id: uuid.UUID, application: Application) -> dict[str, Any]:
    """``GET /applications/{id}`` payload (assembled as a dict for the schema)."""
    base = to_read(application).model_dump()
    job_detail = None
    try:
        from app.modules.jobs.service import get_job_detail

        job_detail = get_job_detail(db, user_id, application.job_id)
    except Exception as exc:  # noqa: BLE001 - the detail page still works without it
        logger.warning("Could not build the job detail for %s: %s", application.job_id, exc)

    base.update(
        {
            "form_snapshot": application.form_snapshot or {},
            "answers": sorted(application.answers or [], key=lambda a: (a.order, a.question_key)),
            "events": list_events(db, application),
            "documents": list(application.documents or []),
            "emails": _emails_for(db, application),
            "interviews": _interviews_for(application),
            "job": job_detail,
            "review": build_review(db, application),
        }
    )
    return base


def _emails_for(db: Session, application: Application) -> list[dict[str, Any]]:
    """Linked emails as plain JSON (the emails module is owned by another agent)."""
    try:
        from app.models.email import EmailMessage

        rows = db.scalars(
            select(EmailMessage)
            .where(EmailMessage.application_id == application.id, EmailMessage.user_id == application.user_id)
            .order_by(EmailMessage.received_at.desc())
        ).all()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not load emails for application %s: %s", application.id, exc)
        return []
    return [
        {
            "id": str(row.id),
            "application_id": str(row.application_id) if row.application_id else None,
            "provider_message_id": row.provider_message_id,
            "thread_id": row.thread_id,
            "sender": row.sender,
            "sender_domain": row.sender_domain,
            "recipient": row.recipient,
            "subject": row.subject,
            "snippet": row.snippet,
            "body_text": (row.body_text or "")[:2000] or None,
            "received_at": row.received_at.isoformat() if row.received_at else None,
            "classification": row.classification.value,
            "classification_confidence": row.classification_confidence,
            "classified_by": row.classified_by,
            "is_simulated": row.is_simulated,
            "is_read": row.is_read,
        }
        for row in rows
    ]


def _interviews_for(application: Application) -> list[Any]:
    from app.modules.interviews.service import to_read as interview_to_read

    return [interview_to_read(row) for row in sorted(application.interviews or [], key=lambda i: _aware(i.scheduled_at))]


__all__ = [
    "approve",
    "build_detail",
    "build_review",
    "ensure_interview",
    "generate_application_answers",
    "generate_cover_letter",
    "get_application",
    "get_automation_config",
    "is_ready",
    "list_applications",
    "list_events",
    "list_queue",
    "mark_failed",
    "mark_submitted",
    "pause",
    "await_review",
    "pick_apply_source",
    "queue_job",
    "questions_from_snapshot",
    "record_snapshot_questions",
    "recompute_queue_positions",
    "record_event",
    "resume_automation",
    "review_summary",
    "save_cover_letter",
    "set_status",
    "skip",
    "start_application",
    "to_read",
    "transition",
    "update_application",
    "withdraw",
]
