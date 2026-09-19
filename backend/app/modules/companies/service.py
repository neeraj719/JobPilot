"""Company registry + per-user priority list (contract §4).

Company names arrive from many platforms in many shapes ("Google India Pvt. Ltd.",
"GOOGLE", "Google Inc") so everything is keyed on :func:`normalize_company_name`.
"""
from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.exceptions import NotFoundError, ValidationFailed
from app.models.application import Application, ApplicationEvent
from app.models.base import utcnow
from app.models.company import Company
from app.models.enums import Actor, ApplicationEventType, ApplicationStatus, CompanyPriority
from app.models.job import Job
from app.models.profile import CompanyPreference
from app.modules.common.pagination import Pagination, paginate
from app.modules.common.schemas import PageResponse
from app.modules.companies.schemas import CompanyPreferenceItem, CompanyRead

logger = logging.getLogger(__name__)

# Legal / generic suffixes stripped from the tail of a company name.
COMPANY_SUFFIXES: frozenset[str] = frozenset(
    {
        "inc",
        "ltd",
        "limited",
        "llc",
        "pvt",
        "private",
        "technologies",
        "technology",
        "labs",
        "corp",
        "corporation",
        "co",
        "india",
        "solutions",
        "services",
        "group",
    }
)

BLACKLIST_SKIP_REASON = "Company blacklisted"
OPEN_APPLICATION_STATUSES = (
    ApplicationStatus.DISCOVERED,
    ApplicationStatus.QUEUED,
    ApplicationStatus.IN_PROGRESS,
)

_COMPANY_COLUMNS = frozenset(c.key for c in Company.__table__.columns) - {"id", "normalized_name", "created_at", "updated_at"}


# --------------------------------------------------------------------------- normalisation


def normalize_company_name(name: str | None) -> str:
    """Lowercase, punctuation-free, legal-suffix-free key for a company name.

    ``normalize_company_name("Google India Pvt. Ltd.") == normalize_company_name("Google")``
    """
    text = (name or "").strip().lower()
    if not text:
        return ""
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]+", "", text)
    tokens = [t for t in text.split() if t]
    while len(tokens) > 1 and tokens[-1] in COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def display_name(name: str | None) -> str:
    return " ".join((name or "").split())


# --------------------------------------------------------------------------- companies


def get_company(db: Session, company_id: uuid.UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise NotFoundError("Company not found")
    return company


def find_company_by_name(db: Session, name: str) -> Company | None:
    normalized = normalize_company_name(name)
    if not normalized:
        return None
    return db.scalars(select(Company).where(Company.normalized_name == normalized)).first()


def get_or_create_company(db: Session, name: str, **attrs: Any) -> Company:
    """Fetch (by normalized name) or create a company.

    Attributes are only ever taken from ``attrs`` - in particular the domain is never
    guessed from the company name.
    """
    normalized = normalize_company_name(name)
    if not normalized:
        raise ValidationFailed("Company name is required", code="invalid_company_name")

    payload = {k: v for k, v in attrs.items() if k in _COMPANY_COLUMNS and v is not None and v != ""}
    company = db.scalars(select(Company).where(Company.normalized_name == normalized)).first()
    if company is None:
        payload.setdefault("name", display_name(name) or normalized)
        company = Company(normalized_name=normalized, **payload)
        db.add(company)
        db.flush()
        logger.info("Created company %s (%s)", company.name, normalized)
        return company

    # enrich only the fields we do not know yet; never overwrite curated data
    for key, value in payload.items():
        if key == "name":
            continue
        if not getattr(company, key, None):
            setattr(company, key, value)
    return company


# --------------------------------------------------------------------------- priorities


def _company_key(company: Company | str) -> tuple[uuid.UUID | None, str]:
    if isinstance(company, str):
        return None, normalize_company_name(company)
    normalized = getattr(company, "normalized_name", None) or normalize_company_name(getattr(company, "name", ""))
    return getattr(company, "id", None), normalized


def resolve_priority(preferences: Iterable[CompanyPreference], company: Company | str) -> CompanyPriority:
    """Resolve a company's priority from an already-loaded preference list.

    Match order: company_id, exact normalized name, then the longest preference whose
    normalized name is a whole-word prefix of the company ("google" matches "google cloud").
    """
    company_id, normalized = _company_key(company)
    preferences = list(preferences)

    if company_id is not None:
        for pref in preferences:
            if pref.company_id is not None and pref.company_id == company_id:
                return pref.priority
    if normalized:
        for pref in preferences:
            if pref.normalized_name == normalized:
                return pref.priority
        best: CompanyPriority | None = None
        best_len = -1
        for pref in preferences:
            pref_name = pref.normalized_name or ""
            if pref_name and normalized.startswith(pref_name + " ") and len(pref_name) > best_len:
                best, best_len = pref.priority, len(pref_name)
        if best is not None:
            return best
    return CompanyPriority.P2


def list_user_preferences(db: Session, user_id: uuid.UUID) -> list[CompanyPreference]:
    stmt = select(CompanyPreference).where(CompanyPreference.user_id == user_id).order_by(CompanyPreference.company_name.asc())
    return list(db.scalars(stmt))


def get_priority(db: Session, user_id: uuid.UUID, company: Company | str) -> CompanyPriority:
    """Priority of ``company`` for ``user_id`` (default ``P2``)."""
    return resolve_priority(list_user_preferences(db, user_id), company)


def get_priority_map(db: Session, user_id: uuid.UUID, companies: Sequence[Company]) -> dict[uuid.UUID, CompanyPriority]:
    """Bulk variant of :func:`get_priority` - one query for any number of companies."""
    preferences = list_user_preferences(db, user_id)
    return {company.id: resolve_priority(preferences, company) for company in companies}


def prioritized_company_ids(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, CompanyPriority]:
    """``{company_id: priority}`` for every company the preference list resolves to a
    **non-default** priority (anything missing from the map is :attr:`CompanyPriority.P2`).

    Lets a SQL filter elsewhere (``GET /jobs?priority=``) use exactly the same resolution
    rules as :func:`resolve_priority` - including the whole-word-prefix match - without
    duplicating them in the query. Only companies that could possibly match a preference
    are loaded, so the candidate set stays bounded by the user's own priority list.
    """
    preferences = list_user_preferences(db, user_id)
    if not preferences:
        return {}

    clauses = []
    linked_ids = {pref.company_id for pref in preferences if pref.company_id is not None}
    if linked_ids:
        clauses.append(Company.id.in_(linked_ids))
    for name in {pref.normalized_name for pref in preferences if pref.normalized_name}:
        # normalized names only contain [a-z0-9 ], so no LIKE wildcards need escaping.
        clauses.append(Company.normalized_name == name)
        clauses.append(Company.normalized_name.like(f"{name} %"))
    if not clauses:
        return {}

    companies = list(db.scalars(select(Company).where(or_(*clauses))).unique())
    resolved = {company.id: resolve_priority(preferences, company) for company in companies}
    return {company_id: priority for company_id, priority in resolved.items() if priority != CompanyPriority.P2}


# --------------------------------------------------------------------------- preference list


def upsert_preference(
    db: Session,
    user_id: uuid.UUID,
    company_name: str,
    priority: CompanyPriority,
    *,
    notes: str | None = None,
    company: Company | None = None,
) -> CompanyPreference:
    normalized = normalize_company_name(company_name)
    if not normalized:
        raise ValidationFailed("Company name is required", code="invalid_company_name")
    linked = company or find_company_by_name(db, company_name)
    existing = db.scalars(
        select(CompanyPreference).where(
            CompanyPreference.user_id == user_id,
            CompanyPreference.normalized_name == normalized,
        )
    ).first()
    if existing is None:
        existing = CompanyPreference(
            user_id=user_id,
            company_id=linked.id if linked else None,
            company_name=display_name(company_name),
            normalized_name=normalized,
            priority=priority,
            notes=notes,
        )
        db.add(existing)
    else:
        existing.company_name = display_name(company_name) or existing.company_name
        existing.priority = priority
        if notes is not None:
            existing.notes = notes
        if linked is not None:
            existing.company_id = linked.id
    db.flush()
    return existing


def replace_preferences(db: Session, user_id: uuid.UUID, items: Sequence[CompanyPreferenceItem]) -> list[CompanyPreference]:
    """Replace the user's whole priority list (upsert by normalized name)."""
    keep: set[str] = set()
    for item in items:
        normalized = normalize_company_name(item.company_name)
        if not normalized or normalized in keep:
            continue
        keep.add(normalized)
        upsert_preference(db, user_id, item.company_name, item.priority, notes=item.notes)

    for pref in list_user_preferences(db, user_id):
        if pref.normalized_name not in keep:
            db.delete(pref)
    db.flush()
    logger.info("Replaced company preferences for user %s (%d entries)", user_id, len(keep))
    return list_user_preferences(db, user_id)


def delete_preference(db: Session, user_id: uuid.UUID, preference_id: uuid.UUID) -> None:
    pref = db.scalars(
        select(CompanyPreference).where(CompanyPreference.id == preference_id, CompanyPreference.user_id == user_id)
    ).first()
    if pref is None:
        raise NotFoundError("Company preference not found")
    db.delete(pref)
    db.flush()


def blacklist_company(db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> CompanyPreference:
    """Mark a company AVOID and skip the user's still-open applications for it."""
    company = get_company(db, company_id)
    pref = upsert_preference(db, user_id, company.name, CompanyPriority.AVOID, company=company)

    stmt = (
        select(Application)
        .join(Job, Application.job_id == Job.id)
        .where(
            Application.user_id == user_id,
            Job.company_id == company.id,
            Application.status.in_(OPEN_APPLICATION_STATUSES),
        )
    )
    applications = list(db.scalars(stmt).unique())
    now = utcnow()
    for application in applications:
        previous = application.status
        application.status = ApplicationStatus.SKIPPED
        application.skipped_reason = BLACKLIST_SKIP_REASON
        application.last_update_at = now
        db.add(
            ApplicationEvent(
                application_id=application.id,
                event_type=ApplicationEventType.STATUS_CHANGED,
                actor=Actor.USER,
                from_status=previous,
                to_status=ApplicationStatus.SKIPPED,
                message=BLACKLIST_SKIP_REASON,
                meta={"reason": "company_blacklisted", "company_id": str(company.id)},
                created_at=now,
            )
        )
    audit(
        db,
        action="company.blacklisted",
        message=f"{company.name} added to the avoid list",
        user_id=user_id,
        actor=Actor.USER,
        meta={"company_id": str(company.id), "applications_skipped": len(applications)},
    )
    db.flush()
    logger.info("Blacklisted %s for user %s (%d applications skipped)", company.name, user_id, len(applications))
    return pref


# --------------------------------------------------------------------------- listing


def _open_job_counts(db: Session, company_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not company_ids:
        return {}
    rows = db.execute(
        select(Job.company_id, func.count(Job.id))
        .where(Job.company_id.in_(company_ids), Job.is_active.is_(True))
        .group_by(Job.company_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def _application_counts(db: Session, user_id: uuid.UUID, company_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not company_ids:
        return {}
    rows = db.execute(
        select(Job.company_id, func.count(Application.id))
        .join(Application, Application.job_id == Job.id)
        .where(Job.company_id.in_(company_ids), Application.user_id == user_id)
        .group_by(Job.company_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def to_company_read(company: Company, *, priority: CompanyPriority | None, open_jobs: int = 0, applications: int = 0) -> CompanyRead:
    read = CompanyRead.model_validate(company)
    read.priority = priority
    read.open_jobs = open_jobs
    read.applications = applications
    return read


def get_company_read(db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> CompanyRead:
    company = get_company(db, company_id)
    return to_company_read(
        company,
        priority=get_priority(db, user_id, company),
        open_jobs=_open_job_counts(db, [company.id]).get(company.id, 0),
        applications=_application_counts(db, user_id, [company.id]).get(company.id, 0),
    )


def list_companies(
    db: Session,
    user_id: uuid.UUID,
    pagination: Pagination,
    *,
    q: str | None = None,
    priority: CompanyPriority | None = None,
) -> PageResponse[CompanyRead]:
    """Companies with the user's priority, open job count and application count.

    ``companies`` is a global table, so the page is resolved in SQL: the derived
    ``?priority=`` filter goes through :func:`prioritized_company_ids` (same rules as
    :func:`resolve_priority`) instead of loading every company and filtering in Python.
    """
    stmt = select(Company)
    term = (q or "").strip()
    if term:
        normalized = normalize_company_name(term)
        like = f"%{term.lower()}%"
        conditions = func.lower(Company.name).like(like)
        if normalized:
            conditions = conditions | Company.normalized_name.like(f"%{normalized}%")
        stmt = stmt.where(conditions)

    if priority is not None:
        prioritized = prioritized_company_ids(db, user_id)
        if priority == CompanyPriority.P2:
            # The default: everything the preference list does not resolve to something else.
            if prioritized:
                stmt = stmt.where(Company.id.notin_(list(prioritized)))
        else:
            matching = [cid for cid, value in prioritized.items() if value == priority]
            stmt = stmt.where(Company.id.in_(matching))

    page = paginate(db, stmt.order_by(func.lower(Company.name).asc(), Company.id.asc()), pagination)
    window: list[Company] = list(page.items)
    priorities = get_priority_map(db, user_id, window)
    ids = [company.id for company in window]
    open_jobs = _open_job_counts(db, ids)
    applications = _application_counts(db, user_id, ids)
    items = [
        to_company_read(
            company,
            priority=priorities[company.id],
            open_jobs=open_jobs.get(company.id, 0),
            applications=applications.get(company.id, 0),
        )
        for company in window
    ]
    return PageResponse[CompanyRead](items=items, total=page.total, page=page.page, page_size=page.page_size)
