"""Jobs service: discovery orchestration, ingestion/dedupe and the job list.

The ingestion cascade is the interesting part — see :mod:`app.modules.jobs.dedupe`.
Cross-module calls (companies, applications, matching, profiles) are lazy imports with
local fallbacks so this module works even while the other modules are being built.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import audit
from app.core.exceptions import NotFoundError
from app.models.application import Application
from app.models.automation import ConnectedAccount
from app.models.base import utcnow
from app.models.company import Company
from app.models.enums import (
    Actor,
    ApplicationStatus,
    ApplicationType,
    CompanyPriority,
    JobSourceType,
    WorkMode,
)
from app.models.job import Job, JobMatch, JobSource
from app.models.profile import CompanyPreference, JobPreference
from app.modules.adapters.base import DiscoveredJob, SearchQuery
from app.modules.adapters.registry import MOCK_SOURCES, get_enabled_adapters
from app.modules.jobs import dedupe
from app.modules.jobs.normalize import normalize_company_name, normalize_location, normalize_title
from app.modules.jobs.schemas import (
    ApplicationBrief,
    CompanyBrief,
    DiscoverRequest,
    DiscoverResult,
    DiscoverSourceResult,
    IngestResult,
    JobCard,
    JobDetail,
    JobSourceRead,
    PageResponse,
    SourceInfoRead,
)
from app.modules.matching.schemas import JobMatchRead

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_DISCOVER_LIMIT = 50
#: Filter value meaning "no application yet" on the status filter.
STATUS_NONE = "NONE"

#: Lower rank = better place to actually apply from (ATS/company site beat aggregators).
APPLY_SOURCE_RANK: dict[JobSourceType, int] = {
    JobSourceType.DEMO_ATS: 0,
    JobSourceType.GREENHOUSE: 1,
    JobSourceType.LEVER: 1,
    JobSourceType.WORKDAY: 1,
    JobSourceType.COMPANY_CAREERS: 2,
    JobSourceType.LINKEDIN: 3,
    JobSourceType.NAUKRI: 4,
    JobSourceType.INDEED: 4,
    JobSourceType.HIRIST: 5,
    JobSourceType.WELLFOUND: 5,
    JobSourceType.FOUNDIT: 5,
    JobSourceType.GLASSDOOR: 6,
    JobSourceType.INTERNSHALA: 6,
    JobSourceType.OTHER: 9,
}
_DEFAULT_RANK = 8

__all__ = [
    "ingest_discovered",
    "list_jobs",
    "get_job",
    "get_job_detail",
    "discover_jobs",
    "queue_job",
    "skip_job",
    "list_sources",
    "get_company_priority",
    "get_company_priority_map",
    "build_search_query",
    "APPLY_SOURCE_RANK",
]


def apply_rank(source: JobSourceType) -> int:
    return APPLY_SOURCE_RANK.get(source, _DEFAULT_RANK)


# --------------------------------------------------------------------------- cross-module glue


def get_or_create_company(db: Session, name: str, **attrs: Any) -> Company:
    """``companies.service.get_or_create_company`` when available, local fallback otherwise."""
    try:
        from app.modules.companies.service import get_or_create_company as _impl
    except Exception as exc:  # companies module not implemented yet
        logger.debug("companies.service.get_or_create_company unavailable: %s", exc)
    else:
        try:
            return _impl(db, name, **attrs)
        except TypeError:  # signature mismatch — retry without the optional attributes
            return _impl(db, name)
    return _local_get_or_create_company(db, name, **attrs)


def _company_normalizer():
    try:
        from app.modules.companies.service import normalize_company_name as _impl

        return _impl
    except Exception:
        return normalize_company_name


def _local_get_or_create_company(db: Session, name: str, **attrs: Any) -> Company:
    normalizer = _company_normalizer()
    normalized = normalizer(name) or (name or "").strip().lower()
    company = db.scalars(select(Company).where(Company.normalized_name == normalized)).first()
    if company is None:
        company = Company(name=(name or "Unknown").strip(), normalized_name=normalized)
        db.add(company)
        db.flush()
        logger.info("Created company %s", company.name)
    for key, value in attrs.items():
        if value and hasattr(company, key) and not getattr(company, key):
            setattr(company, key, value)
    return company


def get_company_priority(db: Session, user_id: uuid.UUID, company: Company | None) -> CompanyPriority:
    """``companies.service.get_priority`` when available, local fallback otherwise (default P2)."""
    if company is None:
        return CompanyPriority.P2
    try:
        from app.modules.companies.service import get_priority as _impl
    except Exception as exc:
        logger.debug("companies.service.get_priority unavailable: %s", exc)
    else:
        try:
            return _impl(db, user_id, company)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("companies.service.get_priority failed: %s", exc)
    preference = db.scalars(
        select(CompanyPreference).where(
            CompanyPreference.user_id == user_id,
            or_(
                CompanyPreference.company_id == company.id,
                CompanyPreference.normalized_name == company.normalized_name,
            ),
        )
    ).first()
    return preference.priority if preference else CompanyPriority.P2


def get_company_priority_map(
    db: Session, user_id: uuid.UUID, companies: Sequence[Company]
) -> dict[uuid.UUID, CompanyPriority]:
    """Bulk :func:`get_company_priority` - one preference query for a whole page of jobs.

    Delegates to ``companies.service.get_priority_map`` so the list page resolves priorities
    with exactly the same rules as the detail page (company_id, exact normalised name, then
    whole-word prefix), instead of the exact-name-only lookup it used to do.
    """
    companies = [company for company in companies if company is not None]
    if not companies:
        return {}
    try:
        from app.modules.companies.service import get_priority_map as _impl
    except Exception as exc:  # pragma: no cover - companies module always present in practice
        logger.debug("companies.service.get_priority_map unavailable: %s", exc)
    else:
        try:
            return _impl(db, user_id, companies)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("companies.service.get_priority_map failed: %s", exc)
    return {company.id: get_company_priority(db, user_id, company) for company in companies}


def _prioritized_company_ids(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, CompanyPriority]:
    """``{company_id: non-default priority}`` used to filter the job list by priority."""
    try:
        from app.modules.companies.service import prioritized_company_ids as _impl

        return _impl(db, user_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("companies.service.prioritized_company_ids unavailable: %s", exc)
    rows = db.scalars(select(CompanyPreference).where(CompanyPreference.user_id == user_id)).all()
    return {row.company_id: row.priority for row in rows if row.company_id is not None}


def get_job_preference(db: Session, user_id: uuid.UUID) -> JobPreference:
    """The user's preferences, or a transient default when the row does not exist yet."""
    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == user_id)).first()
    return preference if preference is not None else JobPreference(user_id=user_id)


# --------------------------------------------------------------------------- ingestion


def _merge_skills(existing: list[Any] | None, incoming: list[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in list(existing or []) + list(incoming or []):
        if not isinstance(value, str):
            continue
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(value.strip())
    return out


def _earliest(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(_aware(left), _aware(right))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _find_by_external_id(db: Session, discovered: DiscoveredJob) -> JobSource | None:
    return db.scalars(
        select(JobSource).where(
            JobSource.source == discovered.source, JobSource.external_id == discovered.external_id
        )
    ).first()


def _find_by_url(db: Session, discovered: DiscoveredJob) -> Job | None:
    if not discovered.url:
        return None
    return db.scalars(select(Job).where(Job.canonical_url == discovered.url)).first()


def _find_by_hash(db: Session, dedupe_hash: str) -> Job | None:
    return db.scalars(select(Job).where(Job.dedupe_hash == dedupe_hash)).first()


def _find_by_fuzzy(db: Session, company: Company, discovered: DiscoveredJob) -> Job | None:
    candidates = db.scalars(select(Job).where(Job.company_id == company.id)).unique().all()
    return dedupe.find_fuzzy_duplicate(discovered.title, discovered.description, candidates)


def _update_job_from_source(job: Job, discovered: DiscoveredJob) -> None:
    """Merge a newly seen listing into an existing Job (best source wins for applying)."""
    job.posted_at = _earliest(job.posted_at, discovered.posted_at)
    job.required_skills = _merge_skills(job.required_skills, discovered.required_skills)
    job.preferred_skills = _merge_skills(job.preferred_skills, discovered.preferred_skills)
    if discovered.description and len(discovered.description) > len(job.description or ""):
        job.description = discovered.description
    for attr in ("location", "work_mode", "employment_type", "salary_min", "salary_max", "salary_currency",
                 "experience_min", "experience_max"):
        if getattr(job, attr, None) in (None, "") and getattr(discovered, attr, None) not in (None, ""):
            setattr(job, attr, getattr(discovered, attr))
    if not job.normalized_location and job.location:
        job.normalized_location = normalize_location(job.location)

    current_rank = _DEFAULT_RANK + 1
    current_source = (job.raw or {}).get("apply_source")
    if current_source:
        try:
            current_rank = apply_rank(JobSourceType(current_source))
        except ValueError:  # pragma: no cover - defensive
            current_rank = _DEFAULT_RANK + 1
    new_rank = apply_rank(discovered.source)
    if new_rank < current_rank:
        job.apply_url = discovered.apply_url or discovered.url
        job.canonical_url = discovered.url
        job.application_type = discovered.application_type or ApplicationType.UNKNOWN
        raw = dict(job.raw or {})
        raw["apply_source"] = discovered.source.value
        job.raw = raw
    job.is_active = True


def _create_job(db: Session, company: Company, discovered: DiscoveredJob, dedupe_hash: str) -> Job:
    job = Job(
        company_id=company.id,
        title=discovered.title,
        normalized_title=normalize_title(discovered.title),
        description=discovered.description or "",
        location=discovered.location,
        normalized_location=normalize_location(discovered.location),
        work_mode=discovered.work_mode,
        employment_type=discovered.employment_type,
        salary_min=discovered.salary_min,
        salary_max=discovered.salary_max,
        salary_currency=discovered.salary_currency,
        experience_min=discovered.experience_min,
        experience_max=discovered.experience_max,
        required_skills=_merge_skills([], discovered.required_skills),
        preferred_skills=_merge_skills([], discovered.preferred_skills),
        posted_at=discovered.posted_at,
        canonical_url=discovered.url,
        apply_url=discovered.apply_url or discovered.url,
        application_type=discovered.application_type or ApplicationType.UNKNOWN,
        dedupe_hash=dedupe_hash,
        is_active=True,
        raw={"apply_source": discovered.source.value},
    )
    db.add(job)
    db.flush()
    return job


def _attach_source(db: Session, job: Job, discovered: DiscoveredJob, now: datetime) -> JobSource:
    source_row = JobSource(
        job_id=job.id,
        source=discovered.source,
        external_id=discovered.external_id,
        url=discovered.url,
        apply_url=discovered.apply_url,
        application_type=discovered.application_type or ApplicationType.UNKNOWN,
        posted_at=discovered.posted_at,
        discovered_at=now,
        last_seen_at=now,
        raw=discovered.raw or {},
    )
    db.add(source_row)
    db.flush()
    return source_row


def ingest_discovered(db: Session, user_id: uuid.UUID, jobs: list[DiscoveredJob]) -> IngestResult:
    """Normalise, deduplicate and persist discovered listings.

    Matching cascade per listing: ``(source, external_id)`` → ``canonical_url`` →
    ``dedupe_hash`` → fuzzy title+description within the same company. A listing that
    matches an existing :class:`Job` becomes an extra :class:`JobSource` row on it.
    """
    now = utcnow()
    result = IngestResult()
    seen_new: set[uuid.UUID] = set()
    seen_all: list[uuid.UUID] = []

    for discovered in jobs:
        result.jobs_found += 1
        bucket = result.per_source.setdefault(
            discovered.source.value, {"found": 0, "new": 0, "duplicates": 0, "seen": 0}
        )
        bucket["found"] += 1

        company = get_or_create_company(
            db,
            discovered.company_name,
            domain=discovered.company_domain,
            logo_url=discovered.company_logo_url,
        )
        title_norm = normalize_title(discovered.title)
        location_norm = normalize_location(discovered.location)
        dedupe_hash = dedupe.compute_dedupe_hash(company.normalized_name, title_norm, location_norm or "")

        existing_source = _find_by_external_id(db, discovered)
        if existing_source is not None:
            job = db.get(Job, existing_source.job_id)
            if job is not None:
                existing_source.last_seen_at = now
                existing_source.url = discovered.url
                existing_source.apply_url = discovered.apply_url
                _update_job_from_source(job, discovered)
                bucket["seen"] += 1
                if job.id not in seen_all:
                    seen_all.append(job.id)
                continue

        job = _find_by_url(db, discovered) or _find_by_hash(db, dedupe_hash) or _find_by_fuzzy(db, company, discovered)
        if job is not None:
            _update_job_from_source(job, discovered)
            _attach_source(db, job, discovered, now)
            result.duplicates_merged += 1
            bucket["duplicates"] += 1
            logger.info(
                "Merged %s listing %s into job %s (%s)",
                discovered.source.value,
                discovered.external_id,
                job.id,
                job.title,
            )
        else:
            job = _create_job(db, company, discovered, dedupe_hash)
            _attach_source(db, job, discovered, now)
            result.jobs_new += 1
            bucket["new"] += 1
            if job.id not in seen_new:
                seen_new.add(job.id)
                result.job_ids_new.append(job.id)
        if job.id not in seen_all:
            seen_all.append(job.id)

    result.job_ids_all = seen_all
    db.flush()
    logger.info(
        "Ingested %d listings: %d new jobs, %d merged duplicates",
        result.jobs_found,
        result.jobs_new,
        result.duplicates_merged,
    )
    return result


# --------------------------------------------------------------------------- listing


def _base_statement(user_id: uuid.UUID, *entities: Any) -> Select[Any]:
    """``select(entities)`` joined to the current user's match / application rows."""
    return (
        select(*entities)
        .select_from(Job)
        .join(Company, Job.company_id == Company.id)
        .outerjoin(JobMatch, and_(JobMatch.job_id == Job.id, JobMatch.user_id == user_id))
        .outerjoin(Application, and_(Application.job_id == Job.id, Application.user_id == user_id))
    )


def _apply_filters(
    stmt: Select[Any],
    user_id: uuid.UUID,
    *,
    q: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    salary_min: int | None = None,
    location: str | None = None,
    work_mode: WorkMode | None = None,
    company: str | None = None,
    experience_min: float | None = None,
    experience_max: float | None = None,
    source: JobSourceType | None = None,
    posted_within_hours: int | None = None,
    status: str | None = None,
    priority: CompanyPriority | None = None,
    is_active: bool | None = True,
    prioritized_company_ids: dict[uuid.UUID, CompanyPriority] | None = None,
) -> Select[Any]:
    if is_active is not None:
        stmt = stmt.where(Job.is_active.is_(is_active))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Company.name.ilike(like), Job.description.ilike(like)))
    if min_score is not None:
        stmt = stmt.where(JobMatch.match_score >= min_score)
    if max_score is not None:
        stmt = stmt.where(JobMatch.match_score <= max_score)
    if salary_min is not None:
        stmt = stmt.where(or_(Job.salary_max >= salary_min, Job.salary_min >= salary_min))
    if location:
        normalized = normalize_location(location)
        clauses = [Job.location.ilike(f"%{location.strip()}%")]
        if normalized:
            clauses.append(Job.normalized_location == normalized)
        stmt = stmt.where(or_(*clauses))
    if work_mode is not None:
        stmt = stmt.where(Job.work_mode == work_mode)
    if company:
        stmt = stmt.where(Company.name.ilike(f"%{company.strip()}%"))
    if experience_min is not None:
        stmt = stmt.where(or_(Job.experience_min >= experience_min, Job.experience_min.is_(None)))
    if experience_max is not None:
        stmt = stmt.where(or_(Job.experience_max <= experience_max, Job.experience_max.is_(None)))
    if source is not None:
        stmt = stmt.where(
            select(JobSource.id).where(and_(JobSource.job_id == Job.id, JobSource.source == source)).exists()
        )
    if posted_within_hours:
        cutoff = utcnow() - timedelta(hours=posted_within_hours)
        stmt = stmt.where(Job.posted_at.is_not(None), Job.posted_at >= cutoff)
    if status:
        if status.upper() == STATUS_NONE:
            stmt = stmt.where(Application.id.is_(None))
        else:
            stmt = stmt.where(Application.status == ApplicationStatus(status.upper()))
    if priority is not None:
        # Priority is *derived* (see companies.service.resolve_priority), so the filter works
        # off the resolved company ids rather than an exact normalised-name join - otherwise
        # ?priority=P1 would hide jobs whose card already shows P1.
        prioritized = prioritized_company_ids if prioritized_company_ids is not None else {}
        if priority == CompanyPriority.P2:
            if prioritized:
                stmt = stmt.where(Job.company_id.notin_(list(prioritized)))
        else:
            matching = [company_id for company_id, value in prioritized.items() if value == priority]
            stmt = stmt.where(Job.company_id.in_(matching))
    return stmt


def _apply_sort(stmt: Select[Any], sort: str | None) -> Select[Any]:
    """``match`` (score desc, nulls last) | ``posted`` | ``salary``."""
    nulls_last_score = case((JobMatch.match_score.is_(None), 1), else_=0)
    nulls_last_posted = case((Job.posted_at.is_(None), 1), else_=0)
    nulls_last_salary = case((Job.salary_max.is_(None), 1), else_=0)
    if sort == "salary":
        return stmt.order_by(nulls_last_salary, Job.salary_max.desc(), Job.posted_at.desc())
    if sort == "posted" or sort is None:
        return stmt.order_by(nulls_last_posted, Job.posted_at.desc(), Job.created_at.desc())
    return stmt.order_by(
        nulls_last_score, JobMatch.match_score.desc(), nulls_last_posted, Job.posted_at.desc()
    )


def _company_brief(company: Company) -> CompanyBrief:
    return CompanyBrief(id=company.id, name=company.name, logo_url=company.logo_url, domain=company.domain)


def _sorted_sources(job: Job) -> list[JobSource]:
    return sorted(job.sources or [], key=lambda s: apply_rank(s.source))


def _to_card(
    job: Job,
    match: JobMatch | None,
    application: Application | None,
    priority: CompanyPriority,
) -> JobCard:
    sources = _sorted_sources(job)
    return JobCard(
        id=job.id,
        title=job.title,
        company=_company_brief(job.company),
        location=job.location,
        work_mode=job.work_mode,
        employment_type=job.employment_type,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        experience_min=job.experience_min,
        experience_max=job.experience_max,
        sources=[s.source for s in sources],
        primary_source=sources[0].source if sources else None,
        posted_at=job.posted_at,
        application_type=job.application_type,
        match_score=match.match_score if match else None,
        company_priority=priority,
        application_status=application.status if application else None,
        application_id=application.id if application else None,
        missing_skills=list(match.missing_skills or []) if match else [],
    )


def list_jobs(
    db: Session,
    user_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    sort: str | None = "match",
    **filters: Any,
) -> PageResponse[JobCard]:
    """Paginated job cards for the current user, with every §9 filter applied."""
    page = max(1, int(page or 1))
    page_size = max(1, min(MAX_PAGE_SIZE, int(page_size or DEFAULT_PAGE_SIZE)))

    prioritized = _prioritized_company_ids(db, user_id) if filters.get("priority") is not None else None

    count_stmt = _apply_filters(
        _base_statement(user_id, func.count(func.distinct(Job.id))),
        user_id,
        prioritized_company_ids=prioritized,
        **filters,
    )
    total = int(db.scalar(count_stmt) or 0)

    stmt = _apply_filters(
        _base_statement(user_id, Job, JobMatch, Application),
        user_id,
        prioritized_company_ids=prioritized,
        **filters,
    )
    stmt = _apply_sort(stmt, sort).offset((page - 1) * page_size).limit(page_size)
    stmt = stmt.options(selectinload(Job.sources))
    rows = db.execute(stmt).unique().all()

    priorities = get_company_priority_map(db, user_id, [job.company for job, _match, _app in rows])
    items = [
        _to_card(job, match, application, priorities.get(job.company_id, CompanyPriority.P2))
        for job, match, application in rows
    ]
    return PageResponse[JobCard](items=items, total=total, page=page, page_size=page_size)


def get_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    return job


def get_job_detail(db: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> JobDetail:
    job = get_job(db, job_id)
    match = db.scalars(select(JobMatch).where(JobMatch.job_id == job.id, JobMatch.user_id == user_id)).first()
    application = db.scalars(
        select(Application).where(Application.job_id == job.id, Application.user_id == user_id)
    ).first()
    priority = get_company_priority(db, user_id, job.company)
    card = _to_card(job, match, application, priority)
    return JobDetail(
        **card.model_dump(),
        description=job.description or "",
        required_skills=list(job.required_skills or []),
        preferred_skills=list(job.preferred_skills or []),
        canonical_url=job.canonical_url,
        apply_url=job.apply_url,
        is_active=job.is_active,
        job_sources=[JobSourceRead.model_validate(s) for s in _sorted_sources(job)],
        match=JobMatchRead.model_validate(match) if match else None,
        application=ApplicationBrief.model_validate(application) if application else None,
    )


# --------------------------------------------------------------------------- discovery


def build_search_query(preference: JobPreference, limit: int | None = None) -> SearchQuery:
    """Turn the user's :class:`JobPreference` into an adapter :class:`SearchQuery`."""
    return SearchQuery(
        titles=[str(t) for t in (preference.desired_titles or []) if t],
        locations=[str(location) for location in (preference.preferred_locations or []) if location],
        keywords=[str(tech) for tech in (preference.preferred_technologies or []) if tech],
        posted_within_hours=preference.only_posted_within_hours,
        limit=limit or DEFAULT_DISCOVER_LIMIT,
    )


def resolve_discovery_sources(db: Session, user_id: uuid.UUID, requested: list[JobSourceType] | None) -> list[JobSourceType]:
    """Explicit request → the user's connected accounts → every mock adapter. Demo ATS always."""
    if requested:
        return list(dict.fromkeys(requested))
    connected = list(
        db.scalars(
            select(ConnectedAccount.source).where(ConnectedAccount.user_id == user_id)
        ).all()
    )
    base = connected or list(MOCK_SOURCES)
    if JobSourceType.DEMO_ATS not in base:
        base.append(JobSourceType.DEMO_ATS)
    return list(dict.fromkeys(base))


def discover_jobs(db: Session, user_id: uuid.UUID, request: DiscoverRequest | None = None) -> DiscoverResult:
    """Run the enabled adapters, ingest what they return and analyze the new jobs."""
    request = request or DiscoverRequest()
    preference = get_job_preference(db, user_id)
    query = build_search_query(preference, request.limit)
    sources = resolve_discovery_sources(db, user_id, request.sources)
    adapters = get_enabled_adapters(sources)

    result = DiscoverResult()
    discovered: list[DiscoveredJob] = []
    per_adapter: dict[JobSourceType, DiscoverSourceResult] = {}

    for adapter in adapters:
        row = DiscoverSourceResult(source=adapter.source)
        per_adapter[adapter.source] = row
        try:
            found = adapter.search_jobs(query)
        except Exception as exc:  # a broken platform must never abort discovery
            logger.exception("Adapter %s failed: %s", adapter.source.value, exc)
            row.error = str(exc)[:200]
            continue
        row.found = len(found)
        discovered.extend(found)

    ingested = ingest_discovered(db, user_id, discovered)
    result.jobs_found = ingested.jobs_found
    result.jobs_new = ingested.jobs_new
    result.duplicates_merged = ingested.duplicates_merged
    for source_value, counts in ingested.per_source.items():
        row = per_adapter.setdefault(JobSourceType(source_value), DiscoverSourceResult(source=JobSourceType(source_value)))
        row.new = counts.get("new", 0)
    result.sources = list(per_adapter.values())

    new_jobs = [job for job in (db.get(Job, job_id) for job_id in ingested.job_ids_new) if job is not None]
    for job in new_jobs:
        audit(
            db,
            action="job.found",
            message=f"{job.company.name} — {job.title}",
            user_id=user_id,
            actor=Actor.AUTOMATION,
            meta={"job_id": str(job.id), "sources": [s.source.value for s in job.sources]},
        )

    from app.modules.matching.service import analyze_jobs

    matches = analyze_jobs(db, user_id, new_jobs)
    result.jobs_analyzed = len(matches)
    logger.info(
        "Discovery for user %s: %d found, %d new, %d merged, %d analyzed",
        user_id,
        result.jobs_found,
        result.jobs_new,
        result.duplicates_merged,
        result.jobs_analyzed,
    )
    return result


# --------------------------------------------------------------------------- queue / skip


def _match_score(db: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> int | None:
    return db.scalars(
        select(JobMatch.match_score).where(JobMatch.job_id == job_id, JobMatch.user_id == user_id)
    ).first()


def _primary_source(job: Job) -> JobSourceType | None:
    sources = _sorted_sources(job)
    return sources[0].source if sources else None


def queue_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> Application:
    """Queue a job for application (delegates to the applications module when present)."""
    job = get_job(db, job_id)
    try:
        from app.modules.applications.service import queue_job as _impl
    except Exception as exc:
        logger.debug("applications.service.queue_job unavailable: %s", exc)
    else:
        return _impl(db, user_id, job_id)

    existing = db.scalars(
        select(Application).where(Application.user_id == user_id, Application.job_id == job_id)
    ).first()
    if existing is not None:
        if existing.status in {ApplicationStatus.DISCOVERED, ApplicationStatus.SKIPPED}:
            existing.status = ApplicationStatus.QUEUED
            existing.skipped_reason = None
        return existing

    application = Application(
        user_id=user_id,
        job_id=job_id,
        status=ApplicationStatus.QUEUED,
        priority=get_company_priority(db, user_id, job.company),
        match_score=_match_score(db, user_id, job_id),
        source=_primary_source(job),
    )
    db.add(application)
    db.flush()
    audit(
        db,
        action="application.created",
        message=f"Queued {job.company.name} — {job.title}",
        user_id=user_id,
        application_id=application.id,
        actor=Actor.USER,
    )
    return application


def skip_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID, reason: str | None = None) -> Application:
    """Mark a job as skipped for this user (creating the application row if needed)."""
    job = get_job(db, job_id)
    application = db.scalars(
        select(Application).where(Application.user_id == user_id, Application.job_id == job_id)
    ).first()
    if application is None:
        application = Application(
            user_id=user_id,
            job_id=job_id,
            priority=get_company_priority(db, user_id, job.company),
            match_score=_match_score(db, user_id, job_id),
            source=_primary_source(job),
        )
        db.add(application)
    application.status = ApplicationStatus.SKIPPED
    application.skipped_reason = (reason or "")[:500] or None
    db.flush()
    audit(
        db,
        action="application.skipped",
        message=f"Skipped {job.company.name} — {job.title}",
        user_id=user_id,
        application_id=application.id,
        actor=Actor.USER,
        meta={"reason": reason} if reason else None,
    )
    return application


# --------------------------------------------------------------------------- sources


def list_sources(db: Session, user_id: uuid.UUID) -> list[SourceInfoRead]:
    """Adapter metadata plus how many listings we hold per source."""
    from app.modules.adapters.registry import list_adapters

    counts = {
        source: int(total)
        for source, total in db.execute(select(JobSource.source, func.count(JobSource.id)).group_by(JobSource.source)).all()
    }
    connected = set(db.scalars(select(ConnectedAccount.source).where(ConnectedAccount.user_id == user_id)).all())
    return [
        SourceInfoRead(
            source=info.source,
            display_name=info.display_name,
            is_mock=info.is_mock,
            supports_auto_apply=info.supports_auto_apply,
            requires_account=info.requires_account,
            uses_browser=info.uses_browser,
            rate_limit_per_minute=info.rate_limit_per_minute,
            terms_note=info.terms_note,
            job_count=counts.get(info.source, 0),
            connected=info.source in connected,
        )
        for info in list_adapters()
    ]
