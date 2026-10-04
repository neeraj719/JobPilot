"""The daily automation pipeline (contract §14).

``search → collect → dedupe → analyze → filter → prioritize → enforce limits → queue →
generate answers → autofill → approval queue → auto-submit → finish``

Every step is recorded on :class:`~app.models.automation.AutomationRun` with timestamps,
a status (``SUCCESS`` / ``FAILED`` / ``SKIPPED``) and a small JSON payload, and every step
is audited (``automation.step``). A failing step never aborts the run — it is recorded and
the pipeline continues, finishing ``PARTIAL`` instead of ``SUCCESS``.

Human-in-the-loop is the default: applications are prepared and parked in the approval
queue. Auto-submit only happens when the user explicitly enabled it *and* the source is on
their allow-list *and* the adapter supports it *and* nothing needs user input.
"""
from __future__ import annotations

import logging
import time as time_module
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.actor import actor_context
from app.core.audit import audit
from app.core.database import session_scope
from app.core.exceptions import ConflictError, ValidationFailed
from app.models.application import Application, ApplicationAnswer
from app.models.automation import AutomationConfig, AutomationRun
from app.models.base import utcnow
from app.models.enums import (
    Actor,
    AnswerStatus,
    ApplicationStatus,
    AuditLevel,
    AutomationRunStatus,
    AutomationRunTrigger,
    AutomationState,
    CompanyPriority,
    JobSourceType,
    NotificationType,
    PauseReason,
    SourceApplyMode,
)
from app.models.job import Job, JobMatch
from app.models.user import User
from app.modules.automation import limits, locks
from app.modules.automation import service as automation_service

logger = logging.getLogger(__name__)

HIGH_MATCH_SCORE = 85
STEP_SEARCH = "search"
STEP_COLLECT = "collect"
STEP_DEDUPE = "dedupe"
STEP_ANALYZE = "analyze"
STEP_FILTER = "filter"
STEP_PRIORITIZE = "prioritize"
STEP_LIMITS = "enforce_limits"
STEP_QUEUE = "queue"
STEP_ANSWERS = "generate_answers"
STEP_AUTOFILL = "autofill"
STEP_APPROVAL = "approval_queue"
STEP_SUBMIT = "auto_submit"
STEP_FINISH = "finish"

STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED = "SKIPPED"

#: Stats keys every run reports (matches the ``AutomationRun.stats`` docstring).
BASE_STATS: tuple[str, ...] = (
    "jobs_found",
    "jobs_new",
    "duplicates_merged",
    "jobs_analyzed",
    "jobs_matched",
    "high_match",
    "filtered_out",
    "queued",
    "discover_only",
    "prepared",
    "ready_for_review",
    "requires_user",
    "submitted",
    "failed",
    "skipped_limit",
)

#: Reasons a candidate job is dropped during the filter/limit steps.
FILTER_REASONS = (
    "below_min_score",
    "too_old",
    "avoid_company",
    "excluded_keyword",
    "already_applied",
    "already_skipped",
    "limit_reached",
)

#: Application statuses that mean "we already acted on this job".
_ACTED_STATUSES = frozenset(
    {
        ApplicationStatus.QUEUED,
        ApplicationStatus.IN_PROGRESS,
        ApplicationStatus.APPLIED,
        ApplicationStatus.APPLICATION_RECEIVED,
        ApplicationStatus.ASSESSMENT,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.RECRUITER_CONTACTED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.OFFER,
        ApplicationStatus.NO_RESPONSE,
        ApplicationStatus.WITHDRAWN,
    }
)

__all__ = ["run_pipeline", "FILTER_REASONS"]


def _sleep(seconds: float) -> None:
    """Indirection so tests can patch ``pipeline._sleep`` and keep runs instant."""
    if seconds > 0:
        time_module.sleep(seconds)


class _Cancelled(Exception):
    """Raised internally when the user cancelled the run between two steps."""


# --------------------------------------------------------------------------- context


@dataclass
class _Candidate:
    """One job under consideration during a run."""

    job: Job
    match: JobMatch | None = None
    application: Application | None = None
    priority: CompanyPriority = CompanyPriority.P2
    score: int = 0
    source: JobSourceType | None = None
    reason: str | None = None

    @property
    def company_name(self) -> str:
        return getattr(self.job.company, "name", None) or "Unknown"

    @property
    def label(self) -> str:
        return f"{self.company_name} - {self.job.title}"


@dataclass
class _Ctx:
    db: Session
    user_id: uuid.UUID
    run: AutomationRun
    config: AutomationConfig
    dry_run: bool = False
    sleep: Callable[[float], None] = _sleep
    failures: int = 0
    stats: dict[str, Any] = field(default_factory=lambda: {key: 0 for key in BASE_STATS})
    candidates: list[_Candidate] = field(default_factory=list)
    selected: list[_Candidate] = field(default_factory=list)
    queued: list[Application] = field(default_factory=list)
    filter_reasons: dict[str, int] = field(default_factory=lambda: {reason: 0 for reason in FILTER_REASONS})

    def bump(self, key: str, amount: int = 1) -> None:
        self.stats[key] = int(self.stats.get(key, 0)) + amount

    def set_stat(self, key: str, value: Any) -> None:
        self.stats[key] = value

    def persist_stats(self) -> None:
        # JSON columns are only marked dirty when reassigned.
        self.run.stats = {**self.stats, "filter_reasons": dict(self.filter_reasons)}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


@contextmanager
def _step(ctx: _Ctx, name: str) -> Generator[dict[str, Any], None, None]:
    """Record one pipeline step (timestamps + status + payload) on the run."""
    started = utcnow()
    record: dict[str, Any] = {
        "step": name,
        "status": STATUS_SUCCESS,
        "started_at": _iso(started),
        "finished_at": None,
        "duration_ms": None,
        "message": "",
        "data": {},
    }
    ctx.run.current_step = name
    try:
        yield record
    except _Cancelled:
        record["status"] = STATUS_SKIPPED
        record["message"] = "Run cancelled by the user"
        raise
    except Exception as exc:  # a failing step never aborts the run
        record["status"] = STATUS_FAILED
        record["message"] = str(exc)[:500]
        ctx.failures += 1
        ctx.bump("failed")
        logger.exception("Automation step %s failed for run %s: %s", name, ctx.run.id, exc)
    finally:
        finished = utcnow()
        record["finished_at"] = _iso(finished)
        record["duration_ms"] = int((finished - started).total_seconds() * 1000)
        try:
            ctx.run.steps = [*(ctx.run.steps or []), record]
            ctx.persist_stats()
            audit(
                ctx.db,
                action="automation.step",
                message=f"{name}: {record['status']}" + (f" - {record['message']}" if record["message"] else ""),
                user_id=ctx.user_id,
                automation_run_id=ctx.run.id,
                actor=Actor.AUTOMATION,
                level=AuditLevel.ERROR if record["status"] == STATUS_FAILED else AuditLevel.INFO,
                meta={"step": name, "status": record["status"], **{k: v for k, v in record["data"].items() if _scalar(v)}},
            )
            ctx.db.flush()
        except Exception:
            # A step that died mid-``flush`` (IntegrityError, "database is locked", ...)
            # leaves the session needing a rollback, and this bookkeeping flush would then
            # raise ``PendingRollbackError`` straight out of the context manager - aborting
            # the whole run and stranding the row at RUNNING. §14 says a failing step is
            # recorded and the run continues, so un-poison the session and carry on.
            logger.exception("Could not record automation step %s for run %s", name, ctx.run.id)
            ctx.db.rollback()
            ctx.run = ctx.db.merge(ctx.run)
            ctx.config = ctx.db.merge(ctx.config)
            ctx.failures += 1


def _scalar(value: Any) -> bool:
    """Keep audit ``metadata`` small — lists/dicts stay in ``AutomationRun.steps``."""
    return isinstance(value, (str, int, float, bool, type(None)))


def _check_cancelled(ctx: _Ctx) -> None:
    if automation_service.is_cancel_requested(ctx.run.id):
        raise _Cancelled
    current = ctx.db.scalars(select(AutomationRun.status).where(AutomationRun.id == ctx.run.id)).first()
    if current == AutomationRunStatus.CANCELLED:
        raise _Cancelled


# --------------------------------------------------------------------------- helpers


def _job_preference(db: Session, user_id: uuid.UUID) -> Any:
    from app.modules.jobs.service import get_job_preference

    return get_job_preference(db, user_id)


def _primary_source(job: Job) -> JobSourceType | None:
    """The source the automation would actually apply through."""
    from app.modules.jobs.service import apply_rank

    sources = sorted(job.sources or [], key=lambda s: apply_rank(s.source))
    if sources:
        return sources[0].source
    raw = (job.raw or {}).get("apply_source")
    if raw:
        try:
            return JobSourceType(str(raw))
        except ValueError:  # pragma: no cover - defensive
            return None
    return None


def _adapter_for(source: JobSourceType | None) -> Any | None:
    if source is None:
        return None
    try:
        from app.modules.adapters.registry import get_adapter

        return get_adapter(source)
    except Exception as exc:  # pragma: no cover - unknown source
        logger.debug("No adapter for %s: %s", source, exc)
        return None


def _browser_available() -> bool:
    try:
        from app.modules.browser.session import is_browser_available
    except Exception as exc:  # pragma: no cover - browser module missing
        logger.debug("browser.session unavailable: %s", exc)
        return False
    try:
        return bool(is_browser_available())
    except Exception as exc:  # pragma: no cover - probe blew up
        logger.warning("Browser availability probe failed: %s", exc)
        return False


def _needs_user_input(db: Session, application: Application, *, required_only: bool = True) -> bool:
    """True when an answer is still missing.

    ``required_only`` mirrors §11's approve() rule: an optional unanswered question does
    not block a submission, so it must not park the application in "needs your input".
    """
    stmt = select(ApplicationAnswer.id).where(
        ApplicationAnswer.application_id == application.id,
        ApplicationAnswer.status == AnswerStatus.NEEDS_USER_INPUT,
    )
    if required_only:
        stmt = stmt.where(ApplicationAnswer.required.is_(True))
    return db.scalars(stmt).first() is not None


def _has_answers(db: Session, application: Application) -> bool:
    return db.scalars(select(ApplicationAnswer.id).where(ApplicationAnswer.application_id == application.id)).first() is not None


def _source_mode(ctx: _Ctx, source: JobSourceType | None) -> SourceApplyMode:
    """The user's per-source apply mode, resolved by the one rule in the service."""
    return automation_service.resolve_source_mode(ctx.config, source)


def _discover_only(ctx: _Ctx, candidate: _Candidate) -> bool:
    return _source_mode(ctx, candidate.source) is SourceApplyMode.DISCOVER_ONLY


def _candidate_payload(candidate: _Candidate) -> dict[str, Any]:
    return {
        "job_id": str(candidate.job.id),
        "title": candidate.job.title,
        "company": candidate.company_name,
        "priority": candidate.priority.value,
        "match_score": candidate.score,
        "source": candidate.source.value if candidate.source else None,
    }


def _auto_submit_allowed(ctx: _Ctx, source: JobSourceType | None) -> bool:
    if not ctx.config.auto_submit_enabled or source is None:
        return False
    allowed = {str(s).upper() for s in (ctx.config.auto_submit_sources or [])}
    if source.value not in allowed:
        return False
    adapter = _adapter_for(source)
    return bool(adapter is not None and getattr(adapter, "supports_auto_apply", False))


# --------------------------------------------------------------------------- steps


def _step_search(ctx: _Ctx) -> tuple[list[Any], Any]:
    """Resolve the adapters and build the search query from the user's preferences."""
    from app.modules.adapters.registry import get_enabled_adapters
    from app.modules.jobs.service import build_search_query, resolve_discovery_sources

    preference = _job_preference(ctx.db, ctx.user_id)
    requested = [JobSourceType(str(s).upper()) for s in (ctx.config.enabled_sources or [])]
    sources = resolve_discovery_sources(ctx.db, ctx.user_id, requested or None)
    adapters = get_enabled_adapters(sources)
    query = build_search_query(preference)
    if ctx.config.only_posted_within_hours:
        query.posted_within_hours = int(ctx.config.only_posted_within_hours)
    return adapters, query


def _step_collect(ctx: _Ctx, adapters: list[Any], query: Any) -> tuple[list[Any], dict[str, Any]]:
    """Ask every adapter for jobs; a broken platform is recorded, never fatal."""
    discovered: list[Any] = []
    per_source: dict[str, Any] = {}
    for adapter in adapters:
        source_value = adapter.source.value
        try:
            found = adapter.search_jobs(query)
        except Exception as exc:
            logger.exception("Adapter %s failed during automation: %s", source_value, exc)
            per_source[source_value] = {"found": 0, "error": str(exc)[:200]}
            ctx.failures += 1
            continue
        per_source[source_value] = {"found": len(found)}
        discovered.extend(found)
    return discovered, per_source


def _build_candidates(ctx: _Ctx, job_ids: list[uuid.UUID]) -> list[_Candidate]:
    from app.modules.jobs.service import get_company_priority_map

    if not job_ids:
        return []
    jobs = list(ctx.db.scalars(select(Job).where(Job.id.in_(job_ids))).unique())
    matches = {
        m.job_id: m
        for m in ctx.db.scalars(
            select(JobMatch).where(JobMatch.user_id == ctx.user_id, JobMatch.job_id.in_(job_ids))
        )
    }
    applications = {
        a.job_id: a
        for a in ctx.db.scalars(
            select(Application).where(Application.user_id == ctx.user_id, Application.job_id.in_(job_ids))
        ).unique()
    }
    # One preference query for the whole run instead of one per distinct company.
    priority_cache: dict[uuid.UUID, CompanyPriority] = get_company_priority_map(
        ctx.db, ctx.user_id, [job.company for job in jobs]
    )
    candidates: list[_Candidate] = []
    for job in jobs:
        match = matches.get(job.id)
        candidates.append(
            _Candidate(
                job=job,
                match=match,
                application=applications.get(job.id),
                priority=priority_cache.get(job.company_id, CompanyPriority.P2),
                score=int(match.match_score) if match is not None else 0,
                source=_primary_source(job),
            )
        )
    return candidates


def _step_filter(ctx: _Ctx, preference: Any) -> list[_Candidate]:
    """Drop candidates that must not be applied to, counting why."""
    min_score = int(ctx.config.min_match_score or 0)
    window_hours = int(ctx.config.only_posted_within_hours or 0)
    cutoff = utcnow() - timedelta(hours=window_hours) if window_hours else None
    excluded = [str(k).strip().lower() for k in (getattr(preference, "excluded_keywords", None) or []) if str(k).strip()]

    kept: list[_Candidate] = []
    for candidate in ctx.candidates:
        application = candidate.application
        if application is not None and application.status == ApplicationStatus.SKIPPED:
            candidate.reason = "already_skipped"
        elif application is not None and application.status in _ACTED_STATUSES:
            candidate.reason = "already_applied"
        elif candidate.priority == CompanyPriority.AVOID:
            candidate.reason = "avoid_company"
        elif candidate.score < min_score:
            candidate.reason = "below_min_score"
        elif cutoff is not None and _posted_at(candidate.job) is not None and _posted_at(candidate.job) < cutoff:
            candidate.reason = "too_old"
        elif excluded and _matches_excluded(candidate.job, excluded):
            candidate.reason = "excluded_keyword"
        if candidate.reason:
            ctx.filter_reasons[candidate.reason] = ctx.filter_reasons.get(candidate.reason, 0) + 1
            continue
        kept.append(candidate)
    return kept


def _posted_at(job: Job) -> datetime | None:
    value = job.posted_at
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _matches_excluded(job: Job, excluded: list[str]) -> bool:
    haystack = f"{job.title or ''}\n{job.description or ''}".lower()
    return any(keyword in haystack for keyword in excluded)


def _priority_rank(priority: CompanyPriority, prioritize: bool) -> int:
    if not prioritize:
        return 0
    return {CompanyPriority.P1: 0, CompanyPriority.P2: 1, CompanyPriority.P3: 2, CompanyPriority.AVOID: 3}.get(priority, 1)


def _step_prioritize(ctx: _Ctx, candidates: list[_Candidate]) -> list[_Candidate]:
    """P1 companies first (when enabled), then match score, then freshness."""
    prioritize = bool(ctx.config.prioritize_priority_companies)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def sort_key(candidate: _Candidate) -> tuple[int, int, float]:
        posted = _posted_at(candidate.job) or epoch
        return (_priority_rank(candidate.priority, prioritize), -candidate.score, -posted.timestamp())

    return sorted(candidates, key=sort_key)


def _step_enforce_limits(ctx: _Ctx, candidates: list[_Candidate]) -> tuple[list[_Candidate], limits.Budget]:
    budget = limits.compute_budget(ctx.db, ctx.user_id, ctx.config, run_id=ctx.run.id)
    selected: list[_Candidate] = []
    for candidate in candidates:
        if _discover_only(ctx, candidate):
            # Never becomes an application, so it must not eat the day's budget — the
            # queue step reports it under ``discover_only`` instead.
            selected.append(candidate)
            continue
        if budget.can_take(candidate.source):
            budget.take(candidate.source)
            selected.append(candidate)
        else:
            candidate.reason = "limit_reached"
            ctx.filter_reasons["limit_reached"] = ctx.filter_reasons.get("limit_reached", 0) + 1
            ctx.bump("skipped_limit")
    return selected, budget


def _queue_application(ctx: _Ctx, candidate: _Candidate, auto_submit: bool) -> Application | None:
    """Delegate to ``applications.service.queue_job``; fall back to a direct row."""
    try:
        from app.modules.applications.service import queue_job
    except Exception as exc:  # applications module not available yet
        logger.debug("applications.service.queue_job unavailable (%s); creating the row directly", exc)
        return _queue_application_fallback(ctx, candidate, auto_submit)
    try:
        application = queue_job(
            ctx.db,
            ctx.user_id,
            candidate.job.id,
            run_id=ctx.run.id,
            priority=candidate.priority,
            auto_submit=auto_submit,
        )
        # ``queue_job`` re-queues an existing DISCOVERED/SKIPPED row without touching its
        # flags; the auto-submit decision belongs to *this* run, so pin it either way.
        if application is not None and bool(application.auto_submit) != auto_submit:
            application.auto_submit = auto_submit
            ctx.db.flush()
        return application
    except TypeError:  # signature drift — retry with the minimal contract
        application = queue_job(ctx.db, ctx.user_id, candidate.job.id)
        application.automation_run_id = ctx.run.id
        application.priority = candidate.priority
        application.auto_submit = auto_submit
        ctx.db.flush()
        return application


def _queue_application_fallback(ctx: _Ctx, candidate: _Candidate, auto_submit: bool) -> Application:
    application = candidate.application
    if application is None:
        application = Application(user_id=ctx.user_id, job_id=candidate.job.id)
        ctx.db.add(application)
    application.status = ApplicationStatus.QUEUED
    application.priority = candidate.priority
    application.match_score = candidate.score or None
    application.source = candidate.source
    application.automation_run_id = ctx.run.id
    application.auto_submit = auto_submit
    application.skipped_reason = None
    ctx.db.flush()
    audit(
        ctx.db,
        action="application.created",
        message=f"Queued {candidate.label}",
        user_id=ctx.user_id,
        application_id=application.id,
        automation_run_id=ctx.run.id,
        actor=Actor.AUTOMATION,
        meta={"job_id": str(candidate.job.id), "match_score": candidate.score},
    )
    return application


def _prepare_application(ctx: _Ctx, application: Application) -> str:
    """Generate answers (and hand to the browser runner) for one application.

    Returns a short outcome code used for the step payload: ``prepared`` / ``skipped``
    (already running or already submitted) / ``failed`` / ``unavailable``.
    """
    try:
        from app.modules.applications.service import start_application
    except Exception as exc:
        logger.debug("applications.service.start_application unavailable: %s", exc)
        return "unavailable"
    try:
        start_application(ctx.db, application.id, ctx.user_id, run_in_background=False)
    except ConflictError as exc:
        logger.info("Skipping application %s: %s", application.id, exc)
        return "skipped"
    except TypeError:
        try:
            start_application(ctx.db, application.id, ctx.user_id)
        except Exception as exc:
            logger.warning("Preparing application %s failed: %s", application.id, exc)
            return "failed"
    except Exception as exc:
        logger.warning("Preparing application %s failed: %s", application.id, exc)
        application.last_error = str(exc)[:500]
        ctx.db.flush()
        return "failed"
    ctx.db.flush()
    return "prepared"


def _submit_application(ctx: _Ctx, application: Application) -> str:
    """Approve + submit one application. ``blocked`` means the review refused it."""
    try:
        from app.modules.applications.service import approve
    except Exception as exc:
        logger.debug("applications.service.approve unavailable: %s", exc)
        return "unavailable"
    user = ctx.db.get(User, ctx.user_id)
    try:
        approve(ctx.db, application, user)
    except ValidationFailed as exc:
        logger.info("Auto-submit refused for %s: %s", application.id, exc)
        return "blocked"
    except TypeError:
        try:
            approve(ctx.db, application.id, ctx.user_id)
        except Exception as exc:
            logger.warning("Auto-submitting application %s failed: %s", application.id, exc)
            return "failed"
    except Exception as exc:
        logger.warning("Auto-submitting application %s failed: %s", application.id, exc)
        return "failed"
    ctx.db.flush()
    return "submitted"


# --------------------------------------------------------------------------- orchestration


def _execute(ctx: _Ctx) -> AutomationRun:  # noqa: C901 - the pipeline is intentionally linear
    db, run = ctx.db, ctx.run
    audit(
        db,
        action="automation.run_started",
        message=f"Automation run started ({run.trigger.value.lower()}{', dry run' if ctx.dry_run else ''})",
        user_id=ctx.user_id,
        automation_run_id=run.id,
        actor=Actor.AUTOMATION,
        meta={"dry_run": ctx.dry_run, "trigger": run.trigger.value},
    )
    db.flush()

    preference = _job_preference(db, ctx.user_id)
    adapters: list[Any] = []
    query: Any = None
    discovered: list[Any] = []
    kept: list[_Candidate] = []

    try:
        with _step(ctx, STEP_SEARCH) as record:
            adapters, query = _step_search(ctx)
            # The run log must show the mode every source actually ran in.
            modes = {a.source.value: _source_mode(ctx, a.source).value for a in adapters}
            run.config_snapshot = {**(run.config_snapshot or {}), "source_modes": modes}
            record["message"] = f"{len(adapters)} sources enabled"
            record["data"] = {
                "sources": [a.source.value for a in adapters],
                "source_modes": modes,
                "titles": list(getattr(query, "titles", []) or []),
                "locations": list(getattr(query, "locations", []) or []),
                "posted_within_hours": getattr(query, "posted_within_hours", None),
            }
        _check_cancelled(ctx)

        with _step(ctx, STEP_COLLECT) as record:
            if not adapters:
                record["status"] = STATUS_SKIPPED
                record["message"] = "No job sources are enabled"
            else:
                discovered, per_source = _step_collect(ctx, adapters, query)
                ctx.set_stat("jobs_found", len(discovered))
                record["message"] = f"{len(discovered)} listings collected"
                record["data"] = {"per_source": per_source}
        _check_cancelled(ctx)

        job_ids: list[uuid.UUID] = []
        with _step(ctx, STEP_DEDUPE) as record:
            from app.modules.jobs.service import ingest_discovered

            ingested = ingest_discovered(db, ctx.user_id, discovered)
            ctx.set_stat("jobs_found", ingested.jobs_found)
            ctx.set_stat("jobs_new", ingested.jobs_new)
            ctx.set_stat("duplicates_merged", ingested.duplicates_merged)
            job_ids = list(ingested.job_ids_all)
            record["message"] = f"{ingested.jobs_new} new, {ingested.duplicates_merged} merged"
            record["data"] = {
                "jobs_found": ingested.jobs_found,
                "jobs_new": ingested.jobs_new,
                "duplicates_merged": ingested.duplicates_merged,
            }
            for job_id in ingested.job_ids_new:
                job = db.get(Job, job_id)
                if job is not None:
                    audit(
                        db,
                        action="job.found",
                        message=f"{getattr(job.company, 'name', 'Unknown')} - {job.title}",
                        user_id=ctx.user_id,
                        automation_run_id=run.id,
                        actor=Actor.AUTOMATION,
                        meta={"job_id": str(job.id)},
                    )
        _check_cancelled(ctx)

        with _step(ctx, STEP_ANALYZE) as record:
            from app.modules.matching.service import analyze_jobs

            known = set(
                db.scalars(
                    select(JobMatch.job_id).where(JobMatch.user_id == ctx.user_id, JobMatch.job_id.in_(job_ids))
                ).all()
            ) if job_ids else set()
            to_analyze = [job for job in (db.get(Job, jid) for jid in job_ids) if job is not None and job.id not in known]
            matches = analyze_jobs(db, ctx.user_id, to_analyze)
            ctx.set_stat("jobs_analyzed", len(matches))
            record["message"] = f"{len(matches)} jobs analyzed"
            record["data"] = {"analyzed": len(matches), "already_analyzed": len(known)}
        _check_cancelled(ctx)

        with _step(ctx, STEP_FILTER) as record:
            ctx.candidates = _build_candidates(ctx, job_ids)
            scores = [c.score for c in ctx.candidates]
            min_score = int(ctx.config.min_match_score or 0)
            ctx.set_stat("jobs_matched", sum(1 for s in scores if s >= min_score))
            ctx.set_stat("high_match", sum(1 for s in scores if s >= HIGH_MATCH_SCORE))
            kept = _step_filter(ctx, preference)
            ctx.set_stat("filtered_out", len(ctx.candidates) - len(kept))
            record["message"] = f"{len(kept)}/{len(ctx.candidates)} jobs passed the filters"
            record["data"] = {"kept": len(kept), "reasons": dict(ctx.filter_reasons)}
        _check_cancelled(ctx)

        with _step(ctx, STEP_PRIORITIZE) as record:
            kept = _step_prioritize(ctx, kept)
            record["message"] = f"{len(kept)} jobs prioritized"
            record["data"] = {
                "order": [
                    {"job_id": str(c.job.id), "company": c.company_name, "priority": c.priority.value, "score": c.score}
                    for c in kept[:20]
                ]
            }
        _check_cancelled(ctx)

        budget: limits.Budget | None = None
        with _step(ctx, STEP_LIMITS) as record:
            ctx.selected, budget = _step_enforce_limits(ctx, kept)
            record["message"] = f"{len(ctx.selected)} within today's budget of {budget.daily_limit}"
            record["data"] = {"selected": len(ctx.selected), "budget": budget.as_dict()}

        # DISCOVER_ONLY sources: real jobs with real scores that simply never become
        # applications. They are reported on the queue step, in dry runs too.
        to_queue = [c for c in ctx.selected if not _discover_only(ctx, c)]
        discover_only = [c for c in ctx.selected if _discover_only(ctx, c)]
        discover_only_payload = [_candidate_payload(c) for c in discover_only]
        ctx.set_stat("discover_only", len(discover_only))

        if ctx.dry_run:
            with _step(ctx, STEP_QUEUE) as record:
                record["status"] = STATUS_SKIPPED
                record["message"] = f"Dry run - {len(to_queue)} applications would be queued"
                if discover_only:
                    record["message"] += f"; {len(discover_only)} discover-only"
                record["data"] = {
                    "would_queue": [_candidate_payload(c) for c in to_queue],
                    "discover_only": discover_only_payload,
                }
            ctx.set_stat("would_queue", len(to_queue))
            return _finish(ctx)
        _check_cancelled(ctx)

        with _step(ctx, STEP_QUEUE) as record:
            queued_payload = []
            for candidate in to_queue:
                auto_submit = _auto_submit_allowed(ctx, candidate.source)
                application = _queue_application(ctx, candidate, auto_submit)
                if application is None:
                    continue
                ctx.queued.append(application)
                queued_payload.append(
                    {"application_id": str(application.id), **_candidate_payload(candidate), "auto_submit": auto_submit}
                )
            ctx.set_stat("queued", len(ctx.queued))
            record["message"] = f"{len(ctx.queued)} applications queued"
            if discover_only:
                record["message"] += f"; {len(discover_only)} discover-only jobs left for you to apply to by hand"
            record["data"] = {"applications": queued_payload, "discover_only": discover_only_payload}
        _check_cancelled(ctx)

        browser_ready = _browser_available()
        deferred: list[str] = []
        browser_apps: list[Application] = []
        with _step(ctx, STEP_ANSWERS) as record:
            prepared = 0
            failed = 0
            skipped_already = 0
            unavailable = False
            delay = float(ctx.config.delay_between_actions_seconds or 0)
            for index, application in enumerate(ctx.queued):
                adapter = _adapter_for(application.source)
                uses_browser = bool(getattr(adapter, "uses_browser", False))
                # The only reason to hold a browser-backed application back is that there
                # is no browser. Which source it is does not matter: the per-source apply
                # mode already decided, at the queue step, whether it may be applied to.
                if uses_browser and not browser_ready:
                    deferred.append(str(application.id))
                    continue
                if uses_browser:
                    browser_apps.append(application)
                if index:
                    ctx.sleep(delay)
                outcome = _prepare_application(ctx, application)
                if outcome == "prepared":
                    prepared += 1
                elif outcome == "failed":
                    failed += 1
                    ctx.bump("failed")
                elif outcome == "unavailable":
                    unavailable = True
                else:  # already running / already submitted
                    skipped_already += 1
            ctx.set_stat("prepared", prepared)
            if unavailable and prepared == 0:
                record["status"] = STATUS_SKIPPED
                record["message"] = "The applications module is not available; applications stay QUEUED for manual start"
            else:
                record["message"] = f"{prepared} applications prepared"
            if deferred:
                record["message"] += f"; {len(deferred)} left QUEUED until a browser is available"
            record["data"] = {
                "prepared": prepared,
                "failed": failed,
                "skipped": skipped_already,
                "deferred": deferred,
                "browser_available": browser_ready,
            }
        _check_cancelled(ctx)

        with _step(ctx, STEP_AUTOFILL) as record:
            if not browser_apps:
                record["status"] = STATUS_SKIPPED
                record["message"] = (
                    "Chromium is not available; browser-backed applications stay QUEUED until it is"
                    if deferred and not browser_ready
                    else "No browser-backed applications in this run"
                )
                record["data"] = {"browser_available": browser_ready, "deferred": len(deferred)}
            else:
                filled = sum(
                    1
                    for app in browser_apps
                    if app.automation_state in (AutomationState.PAUSED, AutomationState.SUCCESS)
                )
                paused = sum(1 for app in browser_apps if app.automation_state == AutomationState.REQUIRES_USER)
                broken = sum(
                    1
                    for app in browser_apps
                    if app.automation_state in (AutomationState.FAILED, AutomationState.RETRYING)
                )
                record["message"] = f"{filled} forms filled, {paused} need a human, {broken} failed"
                if broken and not filled:
                    record["status"] = STATUS_FAILED
                    ctx.failures += 1  # the run finishes PARTIAL, never silently SUCCESS
                record["data"] = {
                    "filled": filled,
                    "requires_user": paused,
                    "failed": broken,
                    "total": len(browser_apps),
                }
        _check_cancelled(ctx)

        with _step(ctx, STEP_APPROVAL) as record:
            ready, requires_user = _approval_counts(ctx)
            ctx.set_stat("ready_for_review", ready)
            ctx.set_stat("requires_user", requires_user)
            record["message"] = f"{ready} ready for review, {requires_user} need your input"
            record["data"] = {"ready_for_review": ready, "requires_user": requires_user}
        _check_cancelled(ctx)

        with _step(ctx, STEP_SUBMIT) as record:
            submitted = 0
            skipped: list[str] = []
            not_prepared: list[str] = []
            delay = float(ctx.config.delay_between_actions_seconds or 0)
            for index, application in enumerate(ctx.queued):
                if not application.auto_submit or not _auto_submit_allowed(ctx, application.source):
                    continue
                if str(application.id) in deferred:
                    # Never prepared or filled (no browser), so there is nothing to submit;
                    # approving it would only drive the adapter into a guaranteed failure.
                    not_prepared.append(str(application.id))
                    continue
                if _needs_user_input(db, application, required_only=False):
                    skipped.append(str(application.id))
                    continue
                if index:
                    ctx.sleep(delay)
                outcome = _submit_application(ctx, application)
                if outcome == "submitted":
                    submitted += 1
                elif outcome == "blocked":
                    skipped.append(str(application.id))
            ctx.set_stat("submitted", submitted)
            if not ctx.config.auto_submit_enabled:
                record["status"] = STATUS_SKIPPED
                record["message"] = "Auto-submit is disabled; applications wait for your approval"
            else:
                record["message"] = f"{submitted} applications submitted automatically"
                if not_prepared:
                    record["message"] += f"; {len(not_prepared)} still QUEUED (no browser)"
            record["data"] = {
                "submitted": submitted,
                "skipped_needs_input": skipped,
                "skipped_not_prepared": not_prepared,
            }

    except _Cancelled:
        return _finish(ctx, cancelled=True)
    except Exception as exc:  # pragma: no cover - defensive: keep the run row consistent
        logger.exception("Automation run %s crashed: %s", run.id, exc)
        run.error = str(exc)[:1000]
        ctx.failures += 1
        return _finish(ctx, fatal=True)

    return _finish(ctx)


def _approval_counts(ctx: _Ctx) -> tuple[int, int]:
    """(ready for review, needs user input) across this run's applications."""
    ready = 0
    requires_user = 0
    for application in ctx.queued:
        needs_input = _needs_user_input(ctx.db, application)
        if application.automation_state == AutomationState.REQUIRES_USER or needs_input:
            requires_user += 1
            continue
        if application.automation_state == AutomationState.PAUSED and application.pause_reason in (
            PauseReason.USER_REVIEW,
            None,
        ):
            ready += 1
        elif application.status == ApplicationStatus.QUEUED and _has_answers(ctx.db, application):
            ready += 1
    return ready, requires_user


def _summary_body(stats: dict[str, Any], *, dry_run: bool = False) -> str:
    queued = int(stats.get("would_queue", 0)) if dry_run else int(stats.get("queued", 0))
    return (
        f"Found {int(stats.get('jobs_found', 0))} jobs, "
        f"{int(stats.get('jobs_matched', 0))} matched, "
        f"{int(stats.get('high_match', 0))} high-match, "
        f"{queued} {'would be queued' if dry_run else 'queued'}, "
        f"{int(stats.get('ready_for_review', 0))} ready for review, "
        f"{int(stats.get('requires_user', 0))} need your input"
    )


def _finish(ctx: _Ctx, *, cancelled: bool = False, fatal: bool = False) -> AutomationRun:
    """Close the run: status, stats, notification, audit and the next scheduled slot."""
    db, run = ctx.db, ctx.run
    now = utcnow()

    if cancelled:
        status = AutomationRunStatus.CANCELLED
    elif fatal:
        status = AutomationRunStatus.FAILED
    elif ctx.failures:
        status = AutomationRunStatus.PARTIAL
    else:
        status = AutomationRunStatus.SUCCESS

    body = _summary_body(ctx.stats, dry_run=ctx.dry_run)
    with _step(ctx, STEP_FINISH) as record:
        record["status"] = STATUS_SKIPPED if cancelled else STATUS_SUCCESS
        record["message"] = body
        record["data"] = {"status": status.value, "stats": dict(ctx.stats)}

    run.status = status
    run.finished_at = now
    run.current_step = None
    ctx.persist_stats()

    # A dry run must not consume the day's scheduled slot: the worker's tick skips a user
    # whose ``last_run_at`` is already today, so previewing at 08:00 used to silently
    # cancel the real 09:00 run.
    if not ctx.dry_run:
        ctx.config.last_run_at = now
    ctx.config.next_run_at = automation_service.compute_next_run_at(ctx.config, now)

    try:
        from app.modules.notifications.service import notify

        if status in (AutomationRunStatus.FAILED,):
            notify(
                db,
                ctx.user_id,
                NotificationType.AUTOMATION_FAILED,
                "Automation run failed",
                body=run.error or body,
                link="/automation",
                meta={"run_id": str(run.id)},
            )
        elif not cancelled:
            title = "Daily automation finished" if not ctx.dry_run else "Automation dry run finished"
            notify(
                db,
                ctx.user_id,
                NotificationType.AUTOMATION_COMPLETED,
                title,
                body=body,
                link="/automation",
                meta={"run_id": str(run.id), "status": status.value, "dry_run": ctx.dry_run},
            )
    except Exception as exc:  # pragma: no cover - never fail a run on a notification
        logger.warning("Could not create the automation notification: %s", exc)

    audit(
        db,
        action="automation.run_finished",
        message=f"Automation run {status.value.lower()}: {body}",
        user_id=ctx.user_id,
        automation_run_id=run.id,
        actor=Actor.AUTOMATION,
        level=AuditLevel.ERROR if status == AutomationRunStatus.FAILED else AuditLevel.INFO,
        meta={"status": status.value, "stats": dict(ctx.stats), "dry_run": ctx.dry_run},
    )
    db.flush()
    automation_service.clear_cancel(run.id)
    logger.info("Automation run %s finished with status %s (%s)", run.id, status.value, body)
    return run


def run_pipeline(
    user_id: uuid.UUID,
    trigger: AutomationRunTrigger = AutomationRunTrigger.MANUAL,
    run_id: uuid.UUID | None = None,
    dry_run: bool = False,
    *,
    db: Session | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    acquire: bool = True,
) -> AutomationRun:
    """Run the whole automation pipeline for one user.

    ``db`` lets a caller (tests, the API's synchronous path) supply the session; when it
    is ``None`` the pipeline opens its own via ``session_scope`` (background thread /
    scheduler). ``acquire=False`` is for callers that already hold the user's lock.
    """
    token: str | None = None
    if acquire:
        token = locks.acquire_lock(user_id)
        if token is None:
            raise ConflictError("An automation run is already in progress for this account", code="automation_running")
    try:
        # The pipeline acts *for* this user, from a scheduler tick or a worker thread as
        # often as from a request, so it publishes the actor itself: every row it writes
        # is attributed to the user rather than filed as an anonymous system write.
        with actor_context(user_id):
            if db is not None:
                return _bootstrap(db, user_id, trigger, run_id, dry_run, sleep_fn)
            with session_scope() as session:
                return _bootstrap(session, user_id, trigger, run_id, dry_run, sleep_fn)
    finally:
        if token is not None:
            locks.release_lock(user_id, token)


def _bootstrap(
    db: Session,
    user_id: uuid.UUID,
    trigger: AutomationRunTrigger,
    run_id: uuid.UUID | None,
    dry_run: bool,
    sleep_fn: Callable[[float], None] | None,
) -> AutomationRun:
    config = automation_service.get_config(db, user_id)
    if run_id is not None:
        run = db.get(AutomationRun, run_id)
        if run is None or run.user_id != user_id:
            raise ConflictError("Automation run not found for this user", code="run_not_found")
        dry_run = bool((run.config_snapshot or {}).get("dry_run", dry_run))
    else:
        run = automation_service.create_run(db, user_id, trigger, dry_run=dry_run, config=config)
    ctx = _Ctx(db=db, user_id=user_id, run=run, config=config, dry_run=dry_run, sleep=sleep_fn or _sleep)
    return _execute(ctx)
