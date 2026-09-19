"""Link an incoming email to one of the user's applications (contract §13).

Candidates are always restricted to *this user's* applications that have actually
been sent (``SUBMITTED_STATUSES`` plus ``IN_PROGRESS``, because a confirmation mail
often lands while the automation is still finishing). Strategies run in order of
trust and the most recently applied match wins:

1. an explicit ``application_id`` (manual link / simulated email);
2. the sender domain matches ``Company.domain`` or ``Company.email_domains``;
3. the normalised company name appears in the sender name, subject or body opening;
4. the job title appears in the subject;
5. an ATS reference such as ``DEMO-AB12CD`` matches ``external_application_id``.

Strategy 3 also *teaches* the system: when a company has no known domain, the
sender's (non-generic) domain is remembered in ``Company.email_domains`` so the next
mail from that ATS links by domain straight away.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import timezone
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.company import Company
from app.models.enums import SUBMITTED_STATUSES, ApplicationStatus
from app.models.job import Job
from app.modules.companies.service import normalize_company_name
from app.modules.emails.classifier import JOB_BOARD_DOMAINS, extract_display_name, extract_domain
from app.modules.emails.schemas import IncomingEmail

logger = logging.getLogger(__name__)

# How the message was linked — stored on ``EmailMessage.matched_by``.
MATCH_EXPLICIT = "EXPLICIT"
MATCH_DOMAIN = "DOMAIN"
MATCH_COMPANY_NAME = "COMPANY_NAME"
MATCH_JOB_TITLE = "JOB_TITLE"
MATCH_APPLICATION_ID = "APPLICATION_ID"
MATCH_MANUAL = "MANUAL"

#: Applications an email may attach to.
LINKABLE_STATUSES: frozenset[ApplicationStatus] = frozenset(SUBMITTED_STATUSES) | {ApplicationStatus.IN_PROGRESS}

#: Free/consumer mail providers — never identify a company, never learned.
PERSONAL_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.in",
        "yahoo.in",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "protonmail.com",
        "proton.me",
        "zoho.com",
        "zohomail.com",
        "rediffmail.com",
        "yandex.com",
        "mail.com",
        "gmx.com",
        "example.com",
        "example.org",
        "example.net",
        "test.com",
        "localhost",
    }
)

#: Characters that may appear in the body before we stop looking for a company name.
BODY_SCAN_CHARS = 500

#: Minimum length before a company name / job title is trusted as a substring match.
MIN_NAME_LENGTH = 3
MIN_TITLE_LENGTH = 5

#: ATS confirmation references, e.g. ``DEMO-AB12CD``, ``GH-91823``, ``REQ_44812``.
_REFERENCE_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}[-_][A-Z0-9]{4,12})\b")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


class LinkResult(NamedTuple):
    """``(application, matched_by)`` — both ``None`` when nothing matched."""

    application: Application | None
    matched_by: str | None


# --------------------------------------------------------------------------- helpers


def normalize_text(value: str | None) -> str:
    """Lowercase, punctuation-free text used for substring comparisons."""
    return _NON_ALNUM_RE.sub(" ", (value or "").lower()).strip()


def _contains_phrase(haystack: str, needle: str) -> bool:
    """Word-boundary-safe containment on already normalised text."""
    if not needle or not haystack:
        return False
    return f" {needle} " in f" {haystack} "


def is_generic_domain(domain: str | None) -> bool:
    """True for consumer mailboxes and ATS/job-board senders (never company-identifying)."""
    if not domain:
        return True
    domain = domain.lower()
    for known in (*PERSONAL_EMAIL_DOMAINS, *JOB_BOARD_DOMAINS):
        if domain == known or domain.endswith(f".{known}"):
            return True
    return False


def domain_matches_company(domain: str | None, company: Company | None) -> bool:
    """``mail.acme.com`` matches a company whose domain (or email_domains) is ``acme.com``."""
    if not domain or company is None:
        return False
    domain = domain.lower()
    known = [company.domain] + list(company.email_domains or [])
    for candidate in known:
        candidate = (candidate or "").strip().lower().lstrip("@")
        if not candidate:
            continue
        if domain == candidate or domain.endswith(f".{candidate}") or candidate.endswith(f".{domain}"):
            return True
    return False


def candidate_applications(db: Session, user_id: uuid.UUID) -> list[Application]:
    """The user's applications an email may attach to, most recently applied first."""
    stmt = (
        select(Application)
        .where(Application.user_id == user_id, Application.status.in_(tuple(LINKABLE_STATUSES)))
        .join(Job, Application.job_id == Job.id)
    )
    applications = list(db.scalars(stmt).unique())
    return sorted(applications, key=_recency_key, reverse=True)


def _recency_key(application: Application) -> tuple[float, float]:
    """Sort key: applied first, then last touched. Naive datetimes are treated as UTC."""

    def _ts(value) -> float:  # noqa: ANN001 - datetime | None
        if value is None:
            return 0.0
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()

    return (_ts(application.applied_at), _ts(application.last_update_at or application.created_at))


def learn_sender_domain(db: Session, company: Company | None, domain: str | None) -> bool:
    """Remember a non-generic sender domain for a company that has none.

    Returns ``True`` when something was learned. Consumer and ATS domains are skipped —
    ``greenhouse-mail.io`` identifies an ATS, not the employer.
    """
    if company is None or not domain or is_generic_domain(domain):
        return False
    if company.domain:
        return False
    known = {str(d).lower() for d in (company.email_domains or [])}
    if domain.lower() in known:
        return False
    company.email_domains = list(company.email_domains or []) + [domain.lower()]
    db.flush()
    logger.info("Learned sender domain %s for company %s", domain, company.name)
    return True


# --------------------------------------------------------------------------- strategies


def _by_domain(applications: list[Application], domain: str | None) -> Application | None:
    if not domain or is_generic_domain(domain):
        return None
    for application in applications:
        company = getattr(application.job, "company", None)
        if domain_matches_company(domain, company):
            return application
    return None


def _by_company_name(applications: list[Application], haystack: str) -> Application | None:
    if not haystack:
        return None
    for application in applications:
        company = getattr(application.job, "company", None)
        if company is None:
            continue
        normalized = company.normalized_name or normalize_company_name(company.name)
        if len(normalized) < MIN_NAME_LENGTH:
            continue
        if _contains_phrase(haystack, normalized):
            return application
    return None


def _by_job_title(applications: list[Application], subject: str) -> Application | None:
    if not subject:
        return None
    for application in applications:
        title = normalize_text(getattr(application.job, "title", None))
        if len(title) < MIN_TITLE_LENGTH:
            continue
        if _contains_phrase(subject, title):
            return application
    return None


def _by_reference(applications: list[Application], text: str) -> Application | None:
    references = {ref.upper() for ref in _REFERENCE_RE.findall(text or "")}
    if not references:
        return None
    for application in applications:
        external = (application.external_application_id or "").strip().upper()
        if external and external in references:
            return application
    return None


# --------------------------------------------------------------------------- public API


def link(
    db: Session,
    user_id: uuid.UUID,
    msg: IncomingEmail,
    *,
    application_id: uuid.UUID | None = None,
    learn: bool = True,
) -> LinkResult:
    """Find the application an email belongs to (scoped to ``user_id``)."""
    if application_id is not None:
        application = db.scalars(
            select(Application).where(Application.id == application_id, Application.user_id == user_id)
        ).first()
        if application is not None:
            return LinkResult(application, MATCH_EXPLICIT)
        logger.warning("Explicit application %s does not belong to user %s; falling back to heuristics", application_id, user_id)

    applications = candidate_applications(db, user_id)
    if not applications:
        return LinkResult(None, None)

    domain = extract_domain(msg.sender)
    body_head = (msg.text or "")[:BODY_SCAN_CHARS]
    subject_norm = normalize_text(msg.subject)
    haystack = normalize_text(" ".join([extract_display_name(msg.sender), msg.subject or "", body_head]))
    raw_text = f"{msg.subject or ''}\n{body_head}"

    application = _by_domain(applications, domain)
    if application is not None:
        return LinkResult(application, MATCH_DOMAIN)

    application = _by_company_name(applications, haystack)
    if application is not None:
        if learn:
            learn_sender_domain(db, getattr(application.job, "company", None), domain)
        return LinkResult(application, MATCH_COMPANY_NAME)

    application = _by_job_title(applications, subject_norm)
    if application is not None:
        return LinkResult(application, MATCH_JOB_TITLE)

    application = _by_reference(applications, raw_text)
    if application is not None:
        return LinkResult(application, MATCH_APPLICATION_ID)

    logger.info("No application matched email %s from %s for user %s", msg.provider_message_id, msg.sender, user_id)
    return LinkResult(None, None)


__all__ = [
    "LINKABLE_STATUSES",
    "LinkResult",
    "MATCH_APPLICATION_ID",
    "MATCH_COMPANY_NAME",
    "MATCH_DOMAIN",
    "MATCH_EXPLICIT",
    "MATCH_JOB_TITLE",
    "MATCH_MANUAL",
    "PERSONAL_EMAIL_DOMAINS",
    "candidate_applications",
    "domain_matches_company",
    "is_generic_domain",
    "learn_sender_domain",
    "link",
    "normalize_text",
]
