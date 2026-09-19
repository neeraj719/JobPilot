"""Email ingestion pipeline (contract §13).

One message flows through: **dedupe → classify → link → progress status → notify**.

Every step is idempotent and scoped to one user. The status progression is explicit
and monotonic (see :data:`STATUS_ORDER`): an email can move an application forward,
a rejection can end it, but nothing ever moves it backwards — so a late "we received
your application" after an interview invite cannot undo the interview.

``applications.service`` is imported lazily: the applications module is written in
parallel, and when it is unavailable the status change is applied directly with an
equivalent ``ApplicationEvent`` so the pipeline still works end to end.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.exceptions import NotFoundError, ValidationFailed
from app.models.application import Application, ApplicationEvent
from app.models.base import utcnow
from app.models.email import EmailMessage
from app.models.enums import (
    RESPONSE_STATUSES,
    Actor,
    ApplicationEventType,
    ApplicationStatus,
    CLASSIFICATION_TO_STATUS,
    EmailClassification,
    InterviewStatus,
    InterviewType,
    NotificationType,
)
from app.models.interview import Interview
from app.models.notification import Notification
from app.modules.common.pagination import Pagination, paginate
from app.modules.common.schemas import PageResponse
from app.modules.emails import classifier, linker
from app.modules.emails.schemas import LIST_BODY_LIMIT, EmailMessageRead, IncomingEmail
from app.modules.notifications.service import notify

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- status rules

#: How far along the funnel each status is. Higher wins; equal or lower is ignored.
STATUS_ORDER: dict[ApplicationStatus, int] = {
    ApplicationStatus.DISCOVERED: 0,
    ApplicationStatus.SKIPPED: 0,
    ApplicationStatus.QUEUED: 1,
    ApplicationStatus.IN_PROGRESS: 2,
    ApplicationStatus.APPLIED: 3,
    ApplicationStatus.NO_RESPONSE: 3,
    ApplicationStatus.APPLICATION_RECEIVED: 4,
    ApplicationStatus.RECRUITER_CONTACTED: 5,
    ApplicationStatus.ASSESSMENT: 6,
    ApplicationStatus.INTERVIEW: 7,
    ApplicationStatus.OFFER: 8,
}

#: Nothing an email says can move an application out of these.
TERMINAL_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN, ApplicationStatus.OFFER}
)

#: Notification raised for each classification once an email is linked.
NOTIFICATION_FOR: dict[EmailClassification, NotificationType] = {
    EmailClassification.RECRUITER_MESSAGE: NotificationType.RECRUITER_RESPONSE,
    EmailClassification.INTERVIEW: NotificationType.INTERVIEW_SCHEDULED,
    EmailClassification.ASSESSMENT: NotificationType.ASSESSMENT_RECEIVED,
    EmailClassification.REJECTION: NotificationType.REJECTION,
    EmailClassification.OFFER: NotificationType.OFFER,
    EmailClassification.APPLICATION_RECEIVED: NotificationType.SYSTEM,
}

#: Interview flavours guessed from the wording of an invitation.
_INTERVIEW_TYPE_HINTS: tuple[tuple[InterviewType, tuple[str, ...]], ...] = (
    (InterviewType.SYSTEM_DESIGN, ("system design", "architecture round", "design round")),
    (InterviewType.TECHNICAL, ("technical", "coding", "live code", "pair programming", "dsa")),
    (InterviewType.PHONE_SCREEN, ("phone screen", "intro call", "introductory call", "screening call", "recruiter call")),
    (InterviewType.HR, ("hr round", "culture fit", "values interview", "hr discussion")),
    (InterviewType.ONSITE, ("onsite", "on-site", "office visit", "final round")),
    (InterviewType.BEHAVIORAL, ("behavioral", "behavioural", "managerial round")),
)

_MEETING_LINK_HOSTS = ("meet.google.com", "zoom.us", "teams.microsoft.com", "teams.live.com", "webex.com", "whereby.com")


def status_rank(status: ApplicationStatus | None) -> int:
    return STATUS_ORDER.get(status, -1) if status is not None else -1


def next_status_for(current: ApplicationStatus, classification: EmailClassification) -> ApplicationStatus | None:
    """The status an email of this class implies, or ``None`` to leave the application alone.

    ``OTHER`` never changes anything; ``REJECTION`` applies from any non-terminal state;
    everything else only ever moves the application *forward*.
    """
    target = CLASSIFICATION_TO_STATUS.get(classification)
    if target is None or current in TERMINAL_STATUSES:
        return None
    if target is ApplicationStatus.REJECTED:
        return ApplicationStatus.REJECTED
    return target if status_rank(target) > status_rank(current) else None


# --------------------------------------------------------------------------- applications bridge


def _applications_service() -> Any | None:
    """The applications module, or ``None`` while it is still being written."""
    try:
        from app.modules.applications import service as applications_service  # noqa: PLC0415 - lazy by design

        return applications_service
    except Exception as exc:  # noqa: BLE001 - module may not exist yet
        logger.debug("applications.service unavailable (%s); using the local fallback", exc)
        return None


def _local_transition(
    db: Session,
    application: Application,
    new_status: ApplicationStatus,
    *,
    actor: Actor,
    message: str,
    meta: dict[str, Any] | None = None,
) -> None:
    """Minimal stand-in for ``applications.service.transition``."""
    now = utcnow()
    previous = application.status
    application.status = new_status
    application.last_update_at = now
    if new_status in RESPONSE_STATUSES:
        application.last_response_at = now
    db.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=ApplicationEventType.STATUS_CHANGED,
            actor=actor,
            from_status=previous,
            to_status=new_status,
            message=message,
            meta=meta or {},
            created_at=now,
        )
    )
    db.flush()


def _transition(
    db: Session,
    application: Application,
    new_status: ApplicationStatus,
    *,
    actor: Actor,
    message: str,
    meta: dict[str, Any] | None = None,
) -> bool:
    """Move an application forward. Returns ``True`` when the applications module handled it."""
    service = _applications_service()
    transition = getattr(service, "transition", None) if service else None
    if transition is not None:
        try:
            transition(db, application, new_status, actor=actor, message=message, meta=meta)
            db.flush()
            return True
        except TypeError as exc:  # signature drift during parallel development
            logger.warning("applications.service.transition rejected the contract call (%s); applying locally", exc)
    _local_transition(db, application, new_status, actor=actor, message=message, meta=meta)
    return False


def _record_event(
    db: Session,
    application: Application,
    event_type: ApplicationEventType,
    message: str,
    *,
    actor: Actor = Actor.SYSTEM,
    meta: dict[str, Any] | None = None,
) -> None:
    service = _applications_service()
    record_event = getattr(service, "record_event", None) if service else None
    if record_event is not None:
        try:
            record_event(db, application, event_type, message, actor=actor, meta=meta)
            return
        except TypeError as exc:  # signature drift during parallel development
            logger.warning("applications.service.record_event rejected the contract call (%s); recording locally", exc)
    db.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=event_type,
            actor=actor,
            message=message,
            meta=meta or {},
            created_at=utcnow(),
        )
    )
    db.flush()


# --------------------------------------------------------------------------- small helpers


def company_name_for(application: Application | None) -> str:
    company = getattr(getattr(application, "job", None), "company", None)
    return getattr(company, "name", None) or "the company"


def job_title_for(application: Application | None) -> str:
    return getattr(getattr(application, "job", None), "title", None) or "the role"


def _company_domain_for(application: Application | None) -> str:
    company = getattr(getattr(application, "job", None), "company", None)
    domain = getattr(company, "domain", None)
    if domain:
        return str(domain)
    slug = linker.normalize_text(getattr(company, "name", "") or "careers").replace(" ", "")
    return f"{slug or 'careers'}.example.com"


def _recent_notification_ids(db: Session, user_id: uuid.UUID, type_: NotificationType, limit: int = 10) -> set[uuid.UUID]:
    stmt = (
        select(Notification.id)
        .where(Notification.user_id == user_id, Notification.type == type_)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    return set(db.scalars(stmt))


def _guess_interview_type(text: str) -> InterviewType:
    lowered = (text or "").lower()
    for interview_type, hints in _INTERVIEW_TYPE_HINTS:
        if any(hint in lowered for hint in hints):
            return interview_type
    return InterviewType.OTHER


def _meeting_link(text: str) -> str | None:
    for token in (text or "").replace("<", " ").replace(">", " ").split():
        cleaned = token.strip().rstrip(".,;)")
        if cleaned.startswith(("http://", "https://")) and any(host in cleaned for host in _MEETING_LINK_HOSTS):
            return cleaned[:1000]
    return None


def _ensure_interview(db: Session, email: EmailMessage, application: Application) -> Interview | None:
    """Create a SCHEDULED interview for an invitation, or enrich the one already open.

    ``applications.service.transition`` opens a placeholder round of its own when an
    application reaches INTERVIEW, so the common path is enrichment: attribute that row
    to the email that triggered it and fill in what the wording reveals.
    """
    existing = list(
        db.scalars(select(Interview).where(Interview.application_id == application.id).order_by(Interview.round_number.asc()))
    )
    text = f"{email.subject or ''}\n{email.body_text or email.snippet or ''}"
    scheduled = next((interview for interview in existing if interview.status == InterviewStatus.SCHEDULED), None)
    if scheduled is not None:
        changed = False
        if scheduled.source_email_id is None:
            scheduled.source_email_id = email.id
            changed = True
        if scheduled.interview_type is InterviewType.OTHER:
            guessed = _guess_interview_type(text)
            if guessed is not InterviewType.OTHER:
                scheduled.interview_type = guessed
                changed = True
        if not scheduled.location_or_link:
            link = _meeting_link(text)
            if link:
                scheduled.location_or_link = link
                changed = True
        if not scheduled.notes and email.subject:
            scheduled.notes = email.subject[:1000]
            changed = True
        if changed:
            db.flush()
            logger.info("Enriched interview %s from email %s", scheduled.id, email.id)
        return scheduled

    interview = Interview(
        application_id=application.id,
        user_id=application.user_id,
        interview_type=_guess_interview_type(text),
        status=InterviewStatus.SCHEDULED,
        round_number=len(existing) + 1,
        location_or_link=_meeting_link(text),
        notes=(email.subject or "")[:1000] or None,
        source_email_id=email.id,
    )
    db.add(interview)
    db.flush()
    logger.info("Created interview %s for application %s from email %s", interview.id, application.id, email.id)
    return interview


# --------------------------------------------------------------------------- linking + progression


def _notification_payload(email: EmailMessage, application: Application) -> tuple[str, str | None]:
    company = company_name_for(application)
    title = job_title_for(application)
    titles: dict[EmailClassification, str] = {
        EmailClassification.APPLICATION_RECEIVED: f"Application received by {company}",
        EmailClassification.RECRUITER_MESSAGE: f"Recruiter reply from {company}",
        EmailClassification.INTERVIEW: f"Interview invitation from {company}",
        EmailClassification.ASSESSMENT: f"Assessment from {company}",
        EmailClassification.REJECTION: f"{company} passed on your application",
        EmailClassification.OFFER: f"Offer from {company}",
    }
    title_text = titles.get(email.classification, f"New email from {company}")
    body = email.subject or email.snippet or f"Update on your {title} application."
    return title_text, body


def _apply_to_application(
    db: Session,
    email: EmailMessage,
    application: Application,
    *,
    matched_by: str,
    actor: Actor = Actor.EMAIL,
) -> bool:
    """Attach an email to an application and let its classification act on the status.

    Returns ``True`` when the application status changed.
    """
    email.application_id = application.id
    email.matched_by = matched_by
    subject = email.subject or "(no subject)"
    company = company_name_for(application)

    audit(
        db,
        action="email.linked",
        message=f"Email '{subject[:120]}' linked to the {company} application",
        user_id=email.user_id,
        application_id=application.id,
        actor=actor,
        meta={"email_id": str(email.id), "matched_by": matched_by, "classification": email.classification.value},
    )
    _record_event(
        db,
        application,
        ApplicationEventType.EMAIL_LINKED,
        f"Email: {subject[:200]}",
        actor=actor,
        meta={"email_id": str(email.id), "matched_by": matched_by, "classification": email.classification.value},
    )

    notification_type = NOTIFICATION_FOR.get(email.classification)
    known_notifications = _recent_notification_ids(db, email.user_id, notification_type) if notification_type else set()

    target = next_status_for(application.status, email.classification)
    changed = False
    if target is not None:
        previous = application.status
        _transition(
            db,
            application,
            target,
            actor=actor,
            message=f"Email: {subject[:200]}",
            meta={"email_id": str(email.id), "classification": email.classification.value, "matched_by": matched_by},
        )
        email.status_applied = True
        changed = True
        logger.info("Email %s moved application %s from %s to %s", email.id, application.id, previous.value, target.value)

    if email.classification is EmailClassification.INTERVIEW:
        _ensure_interview(db, email, application)

    if notification_type is not None:
        already = _recent_notification_ids(db, email.user_id, notification_type) - known_notifications
        if already:
            logger.debug("A %s notification was already raised for application %s", notification_type.value, application.id)
        else:
            title, body = _notification_payload(email, application)
            notify(
                db,
                email.user_id,
                notification_type,
                title,
                body=body,
                link=f"/applications/{application.id}",
                meta={"email_id": str(email.id), "application_id": str(application.id), "classification": email.classification.value},
            )

    db.flush()
    return changed


# --------------------------------------------------------------------------- ingestion


def find_by_provider_id(db: Session, user_id: uuid.UUID, provider_message_id: str) -> EmailMessage | None:
    return db.scalars(
        select(EmailMessage).where(
            EmailMessage.user_id == user_id,
            EmailMessage.provider_message_id == provider_message_id,
        )
    ).first()


def ingest_message(
    db: Session,
    user_id: uuid.UUID,
    msg: IncomingEmail,
    *,
    integration_id: uuid.UUID | None = None,
    application_id: uuid.UUID | None = None,
) -> EmailMessage:
    """Store, classify and link one incoming message (idempotent per provider id)."""
    existing = find_by_provider_id(db, user_id, msg.provider_message_id)
    if existing is not None:
        logger.info("Email %s already ingested for user %s; skipping", msg.provider_message_id, user_id)
        return existing

    outcome = classifier.classify(msg.subject, msg.sender, msg.text)
    body_text = msg.body_text or None
    email = EmailMessage(
        user_id=user_id,
        integration_id=integration_id,
        provider_message_id=msg.provider_message_id,
        thread_id=msg.thread_id,
        sender=(msg.sender or "")[:500],
        sender_domain=classifier.extract_domain(msg.sender),
        recipient=(msg.recipient or None),
        subject=(msg.subject or "")[:1000],
        snippet=(msg.snippet or (body_text or "")[:300]) or None,
        body_text=body_text,
        received_at=msg.received_at,
        classification=outcome.classification,
        classification_confidence=outcome.confidence,
        classified_by=outcome.classified_by,
        classification_reason=outcome.reason,
        is_simulated=msg.is_simulated,
        raw_headers=msg.raw_headers or {},
        created_at=utcnow(),
    )
    db.add(email)
    db.flush()

    audit(
        db,
        action="email.classified",
        message=f"{outcome.classification.value} ({outcome.confidence:.2f}) — {(msg.subject or '(no subject)')[:120]}",
        user_id=user_id,
        actor=Actor.SYSTEM,
        meta={
            "email_id": str(email.id),
            "classification": outcome.classification.value,
            "confidence": outcome.confidence,
            "classified_by": outcome.classified_by,
            "reason": outcome.reason[:500],
            "simulated": msg.is_simulated,
        },
    )

    application, matched_by = linker.link(db, user_id, msg, application_id=application_id)
    if application is not None and matched_by is not None:
        _apply_to_application(db, email, application, matched_by=matched_by)
    db.flush()
    return email


# --------------------------------------------------------------------------- simulated email


def _reference_for(application: Application | None) -> str:
    external = getattr(application, "external_application_id", None)
    if external:
        return str(external)
    seed = str(getattr(application, "id", uuid.uuid4())).replace("-", "").upper()
    return f"DEMO-{seed[:6]}"


def _simulated_content(
    kind: EmailClassification,
    *,
    company: str,
    title: str,
    domain: str,
    reference: str,
) -> tuple[str, str, str]:
    """``(subject, body, sender)`` for a realistic demo email."""
    sign_off = f"\n\nBest regards,\n{company} Talent Team"
    templates: dict[EmailClassification, tuple[str, str, str]] = {
        EmailClassification.APPLICATION_RECEIVED: (
            f"Thank you for applying to {company} — {title}",
            (
                f"Hi,\n\nThank you for applying to the {title} role at {company}. "
                f"We have received your application and our recruiting team is reviewing it.\n\n"
                f"Application ID: {reference}\n\n"
                f"You will hear from us if your profile matches what we are looking for."
            ),
            f"{company} Careers <no-reply@{domain}>",
        ),
        EmailClassification.RECRUITER_MESSAGE: (
            f"{title} opportunity at {company}",
            (
                f"Hi,\n\nI am a recruiter at {company} and I came across your profile. "
                f"We are hiring for the {title} role and I wanted to reach out to see if you would be interested "
                f"in a short conversation this week.\n\nReference: {reference}"
            ),
            f"{company} Talent Acquisition <talent@{domain}>",
        ),
        EmailClassification.INTERVIEW: (
            f"Interview invitation — {title} at {company}",
            (
                f"Hi,\n\nThanks for your interest in the {title} role at {company}. "
                f"We would like to schedule a technical interview with you this week. "
                f"Please share your availability and we will send a calendar invite.\n\n"
                f"Reference: {reference}"
            ),
            f"{company} Recruiting <recruiting@{domain}>",
        ),
        EmailClassification.ASSESSMENT: (
            f"Coding assessment for the {title} role at {company}",
            (
                f"Hi,\n\nAs the next step for the {title} role at {company}, please complete the online assessment. "
                f"The coding challenge takes about 90 minutes and the test link expires in 5 days.\n\n"
                f"Reference: {reference}"
            ),
            f"{company} Assessments <no-reply@{domain}>",
        ),
        EmailClassification.REJECTION: (
            f"Update on your application — {title} at {company}",
            (
                f"Hi,\n\nThank you for your interest in the {title} role at {company}. "
                f"Unfortunately, we have decided to move forward with other candidates whose experience "
                f"more closely matches what the team needs right now.\n\n"
                f"We will keep your profile on file for future openings.\n\nReference: {reference}"
            ),
            f"{company} Careers <no-reply@{domain}>",
        ),
        EmailClassification.OFFER: (
            f"Offer letter — {title} at {company}",
            (
                f"Hi,\n\nWe are pleased to offer you the {title} position at {company}. "
                f"The compensation package and joining details are attached to this email. "
                f"Please review and let us know if you have any questions.\n\nReference: {reference}"
            ),
            f"{company} People Team <people@{domain}>",
        ),
        EmailClassification.OTHER: (
            f"{company} newsletter — what the team shipped this month",
            f"Hi,\n\nHere is a short update on what the {company} engineering team shipped this month.",
            f"{company} News <news@{domain}>",
        ),
    }
    subject, body, sender = templates.get(kind, templates[EmailClassification.OTHER])
    return subject, body + sign_off, sender


def build_simulated_email(
    db: Session,
    user_id: uuid.UUID,
    *,
    kind: EmailClassification | None = None,
    application: Application | None = None,
    subject: str | None = None,
    body: str | None = None,
    sender: str | None = None,
    recipient: str | None = None,
) -> IncomingEmail:
    """Build a realistic :class:`IncomingEmail` for a demo/simulated message."""
    resolved_kind = kind or EmailClassification.APPLICATION_RECEIVED
    if application is None:
        candidates = linker.candidate_applications(db, user_id)
        application = candidates[0] if candidates else None
    generated_subject, generated_body, generated_sender = _simulated_content(
        resolved_kind,
        company=company_name_for(application),
        title=job_title_for(application),
        domain=_company_domain_for(application),
        reference=_reference_for(application),
    )
    return IncomingEmail(
        provider_message_id=f"sim-{uuid.uuid4()}",
        thread_id=None,
        sender=(sender or generated_sender)[:500],
        recipient=recipient,
        subject=(subject or generated_subject)[:1000],
        snippet=None,
        body_text=body or generated_body,
        received_at=utcnow(),
        raw_headers={"x-jobpilot-simulated": "true"},
        is_simulated=True,
    )


def ingest_simulated_email(
    db: Session,
    user_id: uuid.UUID,
    subject: str | None = None,
    body: str | None = None,
    sender: str | None = None,
    application_id: uuid.UUID | None = None,
    kind: EmailClassification | None = None,
) -> EmailMessage:
    """Inject a demo email (``is_simulated=True``) through the normal pipeline."""
    application = _get_application(db, user_id, application_id) if application_id else None
    msg = build_simulated_email(
        db,
        user_id,
        kind=kind,
        application=application,
        subject=subject,
        body=body,
        sender=sender,
    )
    logger.info("Ingesting simulated email for user %s (kind=%s)", user_id, (kind or "auto"))
    return ingest_message(db, user_id, msg, application_id=application_id)


# --------------------------------------------------------------------------- queries / commands


def _get_application(db: Session, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    application = db.scalars(
        select(Application).where(Application.id == application_id, Application.user_id == user_id)
    ).first()
    if application is None:
        raise NotFoundError("Application not found")
    return application


def get_email(db: Session, user_id: uuid.UUID, email_id: uuid.UUID) -> EmailMessage:
    email = db.scalars(select(EmailMessage).where(EmailMessage.id == email_id, EmailMessage.user_id == user_id)).first()
    if email is None:
        raise NotFoundError("Email not found")
    return email


def to_read(email: EmailMessage, *, body_limit: int | None = None) -> EmailMessageRead:
    read = EmailMessageRead.model_validate(email)
    if body_limit is not None and read.body_text and len(read.body_text) > body_limit:
        read.body_text = read.body_text[:body_limit]
    return read


def list_emails(
    db: Session,
    user_id: uuid.UUID,
    pagination: Pagination,
    *,
    classification: EmailClassification | None = None,
    application_id: uuid.UUID | None = None,
    unlinked: bool | None = None,
    q: str | None = None,
) -> PageResponse[EmailMessageRead]:
    """The user's messages, newest first, with ``body_text`` truncated for the list view."""
    stmt = select(EmailMessage).where(EmailMessage.user_id == user_id)
    if classification is not None:
        stmt = stmt.where(EmailMessage.classification == classification)
    if application_id is not None:
        stmt = stmt.where(EmailMessage.application_id == application_id)
    if unlinked is True:
        stmt = stmt.where(EmailMessage.application_id.is_(None))
    elif unlinked is False:
        stmt = stmt.where(EmailMessage.application_id.is_not(None))
    term = (q or "").strip().lower()
    if term:
        like = f"%{term}%"
        stmt = stmt.where(
            func.lower(EmailMessage.subject).like(like)
            | func.lower(EmailMessage.sender).like(like)
            | func.lower(func.coalesce(EmailMessage.body_text, "")).like(like)
        )
    stmt = stmt.order_by(EmailMessage.received_at.desc(), EmailMessage.created_at.desc())
    page = paginate(db, stmt, pagination, transform=lambda row: to_read(row, body_limit=LIST_BODY_LIMIT))
    return PageResponse[EmailMessageRead](items=page.items, total=page.total, page=page.page, page_size=page.page_size)


def link_to_application(db: Session, user_id: uuid.UUID, email_id: uuid.UUID, application_id: uuid.UUID) -> EmailMessage:
    """Manual link from the UI — applies the same status progression as an automatic one."""
    email = get_email(db, user_id, email_id)
    application = _get_application(db, user_id, application_id)
    if email.application_id == application.id and email.matched_by == linker.MATCH_MANUAL:
        return email
    _apply_to_application(db, email, application, matched_by=linker.MATCH_MANUAL, actor=Actor.USER)
    logger.info("User %s linked email %s to application %s", user_id, email_id, application_id)
    return email


def unlink(db: Session, user_id: uuid.UUID, email_id: uuid.UUID) -> EmailMessage:
    """Detach a wrongly linked message (the application keeps its current status)."""
    email = get_email(db, user_id, email_id)
    email.application_id = None
    email.matched_by = None
    email.status_applied = False
    db.flush()
    return email


def reclassify(
    db: Session,
    user_id: uuid.UUID,
    email_id: uuid.UUID,
    classification: EmailClassification,
) -> EmailMessage:
    """Manual classification override; re-runs the status progression when linked."""
    email = get_email(db, user_id, email_id)
    previous = email.classification
    email.classification = classification
    email.classification_confidence = 1.0
    email.classified_by = classifier.CLASSIFIED_BY_USER
    email.classification_reason = f"Manually classified by the user (was {previous.value})."
    db.flush()

    audit(
        db,
        action="email.classified",
        message=f"User reclassified an email as {classification.value}",
        user_id=user_id,
        application_id=email.application_id,
        actor=Actor.USER,
        meta={"email_id": str(email.id), "from": previous.value, "to": classification.value},
    )
    if email.application_id is not None:
        application = _get_application(db, user_id, email.application_id)
        _apply_to_application(db, email, application, matched_by=email.matched_by or linker.MATCH_MANUAL, actor=Actor.USER)
    db.flush()
    return email


def mark_read(db: Session, user_id: uuid.UUID, email_id: uuid.UUID) -> EmailMessage:
    email = get_email(db, user_id, email_id)
    email.is_read = True
    db.flush()
    return email


def simulate(
    db: Session,
    user_id: uuid.UUID,
    *,
    kind: EmailClassification,
    application_id: uuid.UUID | None = None,
    subject: str | None = None,
    body: str | None = None,
    sender: str | None = None,
) -> EmailMessage:
    """``POST /emails/simulate`` — generate and ingest a demo email."""
    if kind is None:  # pragma: no cover - guarded by pydantic
        raise ValidationFailed("A classification kind is required", code="missing_kind")
    return ingest_simulated_email(
        db,
        user_id,
        subject=subject,
        body=body,
        sender=sender,
        application_id=application_id,
        kind=kind,
    )


__all__ = [
    "NOTIFICATION_FOR",
    "STATUS_ORDER",
    "TERMINAL_STATUSES",
    "build_simulated_email",
    "find_by_provider_id",
    "get_email",
    "ingest_message",
    "ingest_simulated_email",
    "link_to_application",
    "list_emails",
    "mark_read",
    "next_status_for",
    "reclassify",
    "simulate",
    "status_rank",
    "to_read",
    "unlink",
]
