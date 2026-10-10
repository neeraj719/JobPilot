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
from app.core.database import soft_delete
from app.core.exceptions import ExternalServiceError, NotFoundError, ValidationFailed
from app.models.application import Application, ApplicationEvent
from app.models.base import utcnow
from app.models.company import Company
from app.models.enums import Actor, ApplicationEventType, ApplicationStatus, CompanyPriority, JobSourceType
from app.models.job import Job
from app.models.profile import CompanyPreference
from app.modules.common.pagination import Pagination, paginate
from app.modules.common.schemas import PageResponse
from app.modules.companies.schemas import (
    BoardDetection,
    CompanyBoardResult,
    CompanyDetectResult,
    CompanyPreferenceItem,
    CompanyRead,
    CompanySuggestion,
    CompanySuggestions,
)

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
#: Board columns are only ever written by :func:`set_company_board`, after verification -
#: never as a side effect of ``get_or_create_company`` enrichment.
_BOARD_COLUMNS = frozenset({"ats_board_token", "ats_board_url"})

#: The Companies page shows its "Quick start" panel until the user's list has this many
#: companies with a configured board.
QUICK_START_MIN_BOARDS = 3


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

    payload = {
        k: v for k, v in attrs.items() if k in _COMPANY_COLUMNS and k not in _BOARD_COLUMNS and v is not None and v != ""
    }
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


# --------------------------------------------------------------------------- public job boards


def verify_board(ats_type: JobSourceType | str, board_url: str) -> tuple[JobSourceType, str, str, int]:
    """Parse ``board_url`` for ``ats_type`` and fetch the board once.

    Returns ``(ats_type, token, display_url, open_job_count)``. Raises
    :class:`ValidationFailed` - ``invalid_board_url`` when no token can be read from the
    value, ``board_not_found`` when the vendor answers 404 or with an empty or malformed
    board - and :class:`ExternalServiceError` when the vendor cannot be reached at all.
    """
    from app.modules.adapters.boards import (
        BoardFetchError,
        BoardNotFound,
        BoardPayloadError,
        BoardUrlError,
        infer_ats_type,
        parse_board_url,
        public_board_url,
    )
    from app.modules.adapters.registry import get_adapter

    try:
        vendor = ats_type if isinstance(ats_type, JobSourceType) else JobSourceType(str(ats_type).strip().upper())
        token = parse_board_url(vendor, board_url)
    except (BoardUrlError, ValueError) as exc:
        raise ValidationFailed(str(exc), code="invalid_board_url") from exc

    adapter = get_adapter(vendor)
    try:
        count = int(adapter.count_board_jobs(token))
    except (BoardNotFound, BoardPayloadError) as exc:
        logger.info("Board %s/%s rejected: %s", vendor.value, token, exc)
        raise ValidationFailed(
            f"No {adapter.display_name} job board was found for '{token}'.",
            code="board_not_found",
            details={"ats_type": vendor.value, "token": token},
        ) from exc
    except BoardFetchError as exc:
        logger.warning("Board %s/%s could not be verified: %s", vendor.value, token, exc)
        raise ExternalServiceError(
            f"{adapter.display_name} could not be reached to verify the board. Try again shortly.",
            code="board_unreachable",
        ) from exc
    if count <= 0:
        raise ValidationFailed(
            f"The {adapter.display_name} board '{token}' has no open jobs (or does not exist).",
            code="board_not_found",
            details={"ats_type": vendor.value, "token": token},
        )

    text = board_url.strip()
    if infer_ats_type(text) is vendor:  # a URL on the vendor's host: keep what the user pasted
        display_url = text if "://" in text else f"https://{text}"
    else:  # a bare token: show the vendor's public board page
        display_url = public_board_url(vendor, token)
    return vendor, token, display_url[:500], count


def set_company_board(
    db: Session, user_id: uuid.UUID, company_id: uuid.UUID, ats_type: JobSourceType | str, board_url: str
) -> CompanyBoardResult:
    """Verify and store a company's public job board (``PUT /companies/{id}/board``)."""
    company = get_company(db, company_id)
    vendor, token, display_url, count = verify_board(ats_type, board_url)
    company.ats_type = vendor.value
    company.ats_board_token = token
    company.ats_board_url = display_url
    db.flush()
    audit(
        db,
        action="company.board_configured",
        message=f"{company.name}: {vendor.value} board '{token}' ({count} open jobs)",
        user_id=user_id,
        actor=Actor.USER,
        meta={"company_id": str(company.id), "ats_type": vendor.value, "token": token, "open_jobs": count},
    )
    logger.info("Company %s now reads the %s board %r (%d open jobs)", company.name, vendor.value, token, count)
    return CompanyBoardResult(company=get_company_read(db, user_id, company.id), board_job_count=count)


def clear_company_board(db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> CompanyRead:
    """Stop reading a company's board (``DELETE /companies/{id}/board``); ``ats_type`` is kept."""
    company = get_company(db, company_id)
    previous = company.ats_board_token
    company.ats_board_token = None
    company.ats_board_url = None
    db.flush()
    if previous:
        audit(
            db,
            action="company.board_removed",
            message=f"{company.name}: board '{previous}' removed",
            user_id=user_id,
            actor=Actor.USER,
            meta={"company_id": str(company.id), "ats_type": company.ats_type, "token": previous},
        )
    return get_company_read(db, user_id, company.id)


def create_company(
    db: Session,
    user_id: uuid.UUID,
    name: str,
    *,
    website: str | None = None,
    board_url: str | None = None,
    ats_type: JobSourceType | str | None = None,
    auto_detect: bool = True,
) -> CompanyDetectResult:
    """Add a company by name (``POST /companies``); idempotent on the normalised name.

    With a ``board_url`` the board is verified exactly as ``PUT /companies/{id}/board``
    does, *before* the company row is written, so a bad URL leaves nothing behind.
    Without one, and with ``auto_detect``, :func:`board_detect.detect_board` looks the
    board up and a found board is stored - unless the company already has one. Detection
    never fails the request: no result just means no board.
    """
    from app.modules.adapters.boards import infer_ats_type
    from app.modules.companies import board_detect

    board: tuple[JobSourceType, str, str, int] | None = None
    if board_url and board_url.strip():
        vendor = ats_type or infer_ats_type(board_url)
        if vendor is None:
            raise ValidationFailed(
                "Choose the ATS (Greenhouse, Lever, Ashby or SmartRecruiters) for this board URL.",
                code="invalid_board_url",
            )
        board = verify_board(vendor, board_url)

    website_clean = (website or "").strip() or None
    detection: BoardDetection | None = None
    if board is None and auto_detect:
        existing = find_company_by_name(db, name)
        if existing is None or not existing.ats_board_token:
            # The network work happens before anything is written.
            detection = board_detect.detect_board(name, website_clean or (existing.website if existing else None))

    company = get_or_create_company(db, name, website=website_clean)
    if board is not None:
        vendor_type, token, display_url, count = board
        company.ats_type = vendor_type.value
        company.ats_board_token = token
        company.ats_board_url = display_url
        db.flush()
    saved = apply_detection(db, user_id, company, detection) if detection is not None else False
    audit(
        db,
        action="company.created",
        message=f"{company.name} added to the company registry",
        user_id=user_id,
        actor=Actor.USER,
        meta={
            "company_id": str(company.id),
            "board": board[1] if board else (company.ats_board_token if saved else None),
            "detection": detection.method if detection else None,
        },
    )
    return _detect_result(db, user_id, company, detection, saved)


# --------------------------------------------------------------------------- board auto-detection


def detect_board(name: str | None, website: str | None) -> BoardDetection:
    """``POST /companies/detect-board``: look a board up without storing anything."""
    from app.modules.companies import board_detect

    if not (name or "").strip() and not (website or "").strip():
        raise ValidationFailed("Give a company name or a website to look up.", code="detect_input_required")
    return board_detect.detect_board(name, website)


def apply_detection(db: Session, user_id: uuid.UUID | None, company: Company, detection: BoardDetection) -> bool:
    """Store what :func:`detect_board` found on ``company``; returns whether anything was saved.

    A readable board (Greenhouse, Lever, Ashby, SmartRecruiters) is stored like a board set
    through ``PUT /companies/{id}/board`` - the detection already verified it. A Workday
    site is recorded as ``ats_type=WORKDAY`` plus ``careers_url`` only: no adapter reads
    Workday, so it gets no board token and the company keeps showing "no board". A careers
    page the scan saw fills an empty ``careers_url`` either way.
    """
    from app.modules.adapters.boards import BOARD_SOURCES

    saved = False
    vendor_names = {source.value for source in BOARD_SOURCES}
    if detection.method != "NONE" and detection.ats_type in vendor_names and detection.token:
        company.ats_type = detection.ats_type
        company.ats_board_token = detection.token
        company.ats_board_url = (detection.board_url or "")[:500] or None
        saved = True
        if detection.method == "KNOWN":
            _fill_from_known_board(company, detection)
    elif detection.method != "NONE" and detection.ats_type == "WORKDAY" and not company.ats_board_token:
        company.ats_type = "WORKDAY"
        if detection.board_url and not company.careers_url:
            company.careers_url = detection.board_url[:500]
        saved = True
    if detection.careers_url and not company.careers_url:
        company.careers_url = detection.careers_url[:500]
    db.flush()
    if saved:
        audit(
            db,
            action="company.board_detected",
            message=f"{company.name}: {detection.ats_type} board '{detection.token}' found ({detection.method.lower()})",
            user_id=user_id,
            actor=Actor.USER if user_id else Actor.SYSTEM,
            meta={
                "company_id": str(company.id),
                "ats_type": detection.ats_type,
                "token": detection.token,
                "method": detection.method,
                "open_jobs": detection.open_jobs,
            },
        )
        logger.info("Company %s: %s board %r detected by %s", company.name, detection.ats_type, detection.token, detection.method)
    return saved


def _fill_from_known_board(company: Company, detection: BoardDetection) -> None:
    """A KNOWN hit also brings the company's domain and tags from the bundled list, when unset."""
    from app.modules.companies import board_detect

    for board in board_detect.known_boards():
        if board.ats_type.value == detection.ats_type and board.token == detection.token:
            if board.domain and not company.domain:
                company.domain = board.domain
            if board.tags and not company.tags:
                company.tags = list(board.tags)
            return


def detect_company_board(db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> CompanyDetectResult:
    """``POST /companies/{id}/detect-board``: re-run detection and store a found board."""
    from app.modules.companies import board_detect

    company = get_company(db, company_id)
    website = company.website or (f"https://{company.domain}" if company.domain else None)
    detection = board_detect.detect_board(company.name, website)
    saved = apply_detection(db, user_id, company, detection)
    return _detect_result(db, user_id, company, detection, saved)


def _detect_result(
    db: Session, user_id: uuid.UUID, company: Company, detection: BoardDetection | None, saved: bool
) -> CompanyDetectResult:
    read = get_company_read(db, user_id, company.id)
    return CompanyDetectResult(**read.model_dump(), detection=detection, detection_saved=saved)


# --------------------------------------------------------------------------- quick start


def _board_types() -> list[str]:
    from app.modules.adapters.boards import BOARD_SOURCES

    return [source.value for source in BOARD_SOURCES]


def count_board_companies(
    db: Session, user_id: uuid.UUID, preferences: Sequence[CompanyPreference] | None = None
) -> int:
    """Companies on the user's list (any priority but AVOID) that have a readable board."""
    if preferences is None:
        preferences = list_user_preferences(db, user_id)
    prefs = [p for p in preferences if p.priority != CompanyPriority.AVOID]
    if not prefs:
        return 0
    ids = {p.company_id for p in prefs if p.company_id is not None}
    names = {p.normalized_name for p in prefs if p.normalized_name}
    clauses = []
    if ids:
        clauses.append(Company.id.in_(ids))
    if names:
        clauses.append(Company.normalized_name.in_(names))
    stmt = select(func.count(func.distinct(Company.id))).where(
        or_(*clauses),
        Company.ats_type.in_(_board_types()),
        Company.ats_board_token.is_not(None),
        Company.ats_board_token != "",
    )
    return int(db.scalar(stmt) or 0)


def list_suggestions(db: Session, user_id: uuid.UUID, limit: int = 20) -> CompanySuggestions:
    """``GET /companies/suggestions``: known-board companies not on the user's list yet.

    Ordered by tag (FAANG, unicorn, product, startup, then the rest) and name. Reads the
    bundled list and the registry only - no network.
    """
    from app.modules.companies import board_detect

    preferences = list_user_preferences(db, user_id)
    listed_names = {p.normalized_name for p in preferences if p.normalized_name}
    listed_ids = {p.company_id for p in preferences if p.company_id is not None}

    known = sorted(board_detect.known_boards(), key=lambda b: (board_detect.tag_rank(b.tags), b.name.lower()))
    keys = {board: normalize_company_name(board.name) for board in known}
    rows = {
        company.normalized_name: company
        for company in db.scalars(select(Company).where(Company.normalized_name.in_(set(keys.values()))))
    }
    items: list[CompanySuggestion] = []
    for board in known:
        company = rows.get(keys[board])
        if board_detect.known_name_keys(board) & listed_names or (company is not None and company.id in listed_ids):
            continue
        items.append(
            CompanySuggestion(
                name=board.name,
                domain=board.domain,
                ats_type=board.ats_type.value,
                token=board.token,
                board_url=board.board_url,
                tags=list(board.tags),
                company_id=company.id if company is not None else None,
                board_configured=bool(company is not None and company.ats_board_token),
            )
        )
        if len(items) >= max(1, limit):
            break
    board_companies = count_board_companies(db, user_id, preferences)
    return CompanySuggestions(
        items=items, board_companies=board_companies, show_quick_start=board_companies < QUICK_START_MIN_BOARDS
    )


def order_board_companies(db: Session, user_id: uuid.UUID, companies: Sequence[Company]) -> list[Company]:
    """Board companies in reading order for one user's discovery run.

    Companies on the user's list come first (P1, then P2, then P3), then everything else;
    within each group by tag (FAANG, unicorn, product, startup) and name. Used by
    ``jobs.service.load_board_tokens`` to choose the boards a run reads when more are
    configured than one run reads.
    """
    from app.modules.companies import board_detect

    preferences = list_user_preferences(db, user_id)
    by_id = {p.company_id: p for p in preferences if p.company_id is not None}
    by_name = {p.normalized_name: p for p in preferences if p.normalized_name}
    rank = {CompanyPriority.P1: 0, CompanyPriority.P2: 1, CompanyPriority.P3: 2}

    def key(company: Company) -> tuple[int, int, str]:
        pref = by_id.get(company.id) or by_name.get(company.normalized_name)
        listed = rank.get(pref.priority, 3) if pref is not None else 3
        return listed, board_detect.tag_rank(company.tags), (company.name or "").lower()

    return sorted(companies, key=key)


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
            soft_delete(pref)
    db.flush()
    logger.info("Replaced company preferences for user %s (%d entries)", user_id, len(keep))
    return list_user_preferences(db, user_id)


def delete_preference(db: Session, user_id: uuid.UUID, preference_id: uuid.UUID) -> None:
    pref = db.scalars(
        select(CompanyPreference).where(CompanyPreference.id == preference_id, CompanyPreference.user_id == user_id)
    ).first()
    if pref is None:
        raise NotFoundError("Company preference not found")
    soft_delete(pref)
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
