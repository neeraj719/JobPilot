"""Automation service: config, runs and the manual-run entry point (contract §14).

The heavy lifting lives in :mod:`app.modules.automation.pipeline`; this module owns the
CRUD around it — validating the per-user configuration, creating/cancelling runs and
answering ``GET /automation/status``.
"""
from __future__ import annotations

import logging
import re
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import available_timezones

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.models.automation import AutomationConfig, AutomationRun
from app.models.base import utcnow
from app.models.enums import Actor, AutomationRunStatus, AutomationRunTrigger, JobSourceType, SourceApplyMode
from app.modules.automation import limits, locks
from app.modules.automation.schemas import (
    AutomationConfigRead,
    AutomationConfigUpdate,
    AutomationRunRead,
    AutomationStatusRead,
    TodayStatus,
)
from app.modules.common.pagination import Pagination
from app.modules.common.schemas import PageResponse

logger = logging.getLogger(__name__)

SCHEDULE_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

#: Runs the user asked to cancel while the pipeline is mid-flight.
_cancel_requests: set[uuid.UUID] = set()
_cancel_guard = threading.Lock()

__all__ = [
    "cancel_run",
    "clear_cancel",
    "compute_next_run_at",
    "create_run",
    "get_config",
    "get_run",
    "get_status",
    "is_cancel_requested",
    "list_runs",
    "resolve_source_mode",
    "resolved_source_modes",
    "running_run",
    "start_manual_run",
    "to_config_read",
    "to_run_read",
    "update_config",
]


# --------------------------------------------------------------------------- config


def get_config(db: Session, user_id: uuid.UUID) -> AutomationConfig:
    """The user's automation config, created with safe defaults when missing."""
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


def to_config_read(config: AutomationConfig) -> AutomationConfigRead:
    """``AutomationConfigRead`` with ``source_modes`` resolved for every registered source."""
    read = AutomationConfigRead.model_validate(config)
    read.source_modes = {s.value: m for s, m in resolved_source_modes(config).items()}
    return read


def auto_apply_sources() -> set[JobSourceType]:
    """Sources whose adapter declares ``supports_auto_apply``."""
    from app.modules.adapters.registry import list_adapters

    return {info.source for info in list_adapters() if info.supports_auto_apply}


def _adapter_supports_auto_apply(source: JobSourceType) -> bool:
    try:
        from app.modules.adapters.registry import get_adapter

        return bool(getattr(get_adapter(source), "supports_auto_apply", False))
    except Exception as exc:  # unknown / unregistered source
        logger.debug("No adapter for %s while resolving its apply mode: %s", source, exc)
        return False


def resolve_source_mode(config: AutomationConfig | None, source: JobSourceType | str | None) -> SourceApplyMode:
    """The apply mode the pipeline must use for ``source`` — **the** rule, used everywhere.

    1. An explicit entry in ``config.source_modes`` wins.
    2. Otherwise ``AUTO_APPLY`` when the adapter supports automated applications, else
       ``DISCOVER_ONLY``.
    3. An adapter without ``supports_auto_apply`` can never resolve to ``AUTO_APPLY``,
       whatever the stored value says — the stored value is downgraded, not trusted.
    """
    if source is None:
        return SourceApplyMode.DISCOVER_ONLY
    try:
        resolved = source if isinstance(source, JobSourceType) else JobSourceType(str(source).upper())
    except ValueError:
        logger.debug("Unknown job source %r resolves to DISCOVER_ONLY", source)
        return SourceApplyMode.DISCOVER_ONLY

    supported = _adapter_supports_auto_apply(resolved)
    stored = (getattr(config, "source_modes", None) or {}).get(resolved.value) if config is not None else None
    if stored is not None:
        try:
            mode = SourceApplyMode(str(stored).upper())
        except ValueError:
            logger.debug("Ignoring invalid stored apply mode %r for %s", stored, resolved.value)
            mode = None
        if mode is SourceApplyMode.AUTO_APPLY and not supported:
            logger.debug("%s is stored as AUTO_APPLY but its adapter cannot apply; using DISCOVER_ONLY", resolved.value)
            return SourceApplyMode.DISCOVER_ONLY
        if mode is not None:
            return mode
    return SourceApplyMode.AUTO_APPLY if supported else SourceApplyMode.DISCOVER_ONLY


def resolved_source_modes(
    config: AutomationConfig | None, sources: list[JobSourceType] | None = None
) -> dict[JobSourceType, SourceApplyMode]:
    """``resolve_source_mode`` over ``sources`` (default: every registered adapter), in registry order."""
    if sources is None:
        from app.modules.adapters.registry import ADAPTERS

        sources = list(ADAPTERS)
    return {source: resolve_source_mode(config, source) for source in sources}


def _validate_source_modes(raw: dict[str, Any]) -> dict[str, str]:
    """Normalise a ``source_modes`` patch; 422 on unknown sources, modes or unsupported AUTO_APPLY."""
    out: dict[str, str] = {}
    for key, value in dict(raw).items():
        try:
            source = JobSourceType(str(key).upper())
        except ValueError as exc:
            raise ValidationFailed(
                f"Unknown job source '{key}' in source_modes",
                code="unknown_source",
                details={"field": "source_modes", "value": key},
            ) from exc
        try:
            mode = SourceApplyMode(str(value).upper())
        except ValueError as exc:
            raise ValidationFailed(
                f"Unknown apply mode '{value}' for {source.value}; use AUTO_APPLY or DISCOVER_ONLY",
                code="invalid_source_mode",
                details={"field": "source_modes", "source": source.value, "value": value},
            ) from exc
        if mode is SourceApplyMode.AUTO_APPLY and not _adapter_supports_auto_apply(source):
            raise ValidationFailed(
                f"{source.value} cannot be set to AUTO_APPLY: its adapter does not support automated "
                "applications, so it can only be used to discover jobs",
                code="auto_apply_unsupported",
                details={"field": "source_modes", "source": source.value},
            )
        out[source.value] = mode.value
    return out


def _coerce_sources(values: list[str] | None, field: str) -> list[JobSourceType]:
    out: list[JobSourceType] = []
    for value in values or []:
        try:
            source = JobSourceType(str(value).upper())
        except ValueError as exc:
            raise ValidationFailed(
                f"Unknown job source '{value}' in {field}",
                code="unknown_source",
                details={"field": field, "value": value},
            ) from exc
        if source not in out:
            out.append(source)
    return out


def validate_config_update(payload: AutomationConfigUpdate) -> dict[str, Any]:
    """Validate a config patch and return the ORM-ready values."""
    data = payload.model_dump(exclude_unset=True)
    values: dict[str, Any] = {}

    if "schedule_time" in data and data["schedule_time"] is not None:
        schedule_time = str(data["schedule_time"]).strip()
        if not SCHEDULE_TIME_RE.match(schedule_time):
            raise ValidationFailed(
                "schedule_time must be HH:MM in 24-hour format", code="invalid_schedule_time", details={"value": schedule_time}
            )
        values["schedule_time"] = schedule_time

    if "timezone" in data and data["timezone"] is not None:
        tz_name = str(data["timezone"]).strip()
        if tz_name not in available_timezones():
            raise ValidationFailed("Unknown timezone", code="invalid_timezone", details={"value": tz_name})
        values["timezone"] = tz_name

    if "daily_application_limit" in data and data["daily_application_limit"] is not None:
        limit = int(data["daily_application_limit"])
        if limit < 1:
            raise ValidationFailed("daily_application_limit must be at least 1", code="invalid_daily_limit")
        if limit > settings.MAX_DAILY_APPLICATION_LIMIT:
            raise ValidationFailed(
                f"daily_application_limit cannot exceed {settings.MAX_DAILY_APPLICATION_LIMIT}",
                code="daily_limit_too_high",
                details={"max": settings.MAX_DAILY_APPLICATION_LIMIT},
            )
        values["daily_application_limit"] = limit

    if "per_platform_limit" in data and data["per_platform_limit"] is not None:
        per_platform: dict[str, int] = {}
        for key, value in dict(data["per_platform_limit"]).items():
            try:
                source = JobSourceType(str(key).upper())
            except ValueError as exc:
                raise ValidationFailed(
                    f"Unknown job source '{key}' in per_platform_limit",
                    code="unknown_source",
                    details={"field": "per_platform_limit", "value": key},
                ) from exc
            limit = int(value)
            if limit < 0:
                raise ValidationFailed(
                    "per-platform limits cannot be negative", code="invalid_platform_limit", details={"source": source.value}
                )
            per_platform[source.value] = limit
        values["per_platform_limit"] = per_platform

    if "enabled_sources" in data and data["enabled_sources"] is not None:
        values["enabled_sources"] = [s.value for s in _coerce_sources(data["enabled_sources"], "enabled_sources")]

    if "auto_submit_sources" in data and data["auto_submit_sources"] is not None:
        requested = _coerce_sources(data["auto_submit_sources"], "auto_submit_sources")
        allowed = auto_apply_sources()
        invalid = [s.value for s in requested if s not in allowed]
        if invalid:
            raise ValidationFailed(
                "Auto-submit is only available for sources that support automated applications",
                code="auto_submit_unsupported",
                details={"invalid": invalid, "allowed": sorted(s.value for s in allowed)},
            )
        values["auto_submit_sources"] = [s.value for s in requested]

    if "source_modes" in data and data["source_modes"] is not None:
        values["source_modes"] = _validate_source_modes(data["source_modes"])

    for key in (
        "enabled",
        "min_match_score",
        "prioritize_priority_companies",
        "only_posted_within_hours",
        "delay_between_actions_seconds",
        "retry_limit",
        "auto_submit_enabled",
        "auto_generate_cover_letters",
        "notify_on_input_required",
    ):
        if key in data and data[key] is not None:
            values[key] = data[key]
    return values


def compute_next_run_at(config: AutomationConfig, now: datetime | None = None) -> datetime | None:
    """The next UTC instant ``schedule_time`` occurs in the user's timezone."""
    if not config.enabled:
        return None
    zone = limits.resolve_zone(config.timezone)
    now = now or utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    match = SCHEDULE_TIME_RE.match((config.schedule_time or "09:00").strip())
    hour, minute = (int(match.group(1)), int(match.group(2))) if match else (9, 0)
    local_now = now.astimezone(zone)
    candidate = datetime.combine(local_now.date(), time(hour=hour, minute=minute), tzinfo=zone)
    if candidate <= local_now:
        candidate = datetime.combine(local_now.date() + timedelta(days=1), time(hour=hour, minute=minute), tzinfo=zone)
    return candidate.astimezone(timezone.utc)


def update_config(db: Session, user_id: uuid.UUID, payload: AutomationConfigUpdate) -> AutomationConfig:
    """Apply a validated config patch and refresh ``next_run_at``."""
    config = get_config(db, user_id)
    values = validate_config_update(payload)
    for key, value in values.items():
        setattr(config, key, value)
    config.next_run_at = compute_next_run_at(config)
    db.flush()
    audit(
        db,
        action="automation.config_updated",
        message="Automation settings updated",
        user_id=user_id,
        actor=Actor.USER,
        meta={"changed": sorted(values.keys())},
    )
    logger.info("Automation config updated for user %s: %s", user_id, sorted(values.keys()))
    return config


# --------------------------------------------------------------------------- runs


def to_run_read(run: AutomationRun) -> AutomationRunRead:
    return AutomationRunRead.model_validate(run)


def running_run(db: Session, user_id: uuid.UUID) -> AutomationRun | None:
    return db.scalars(
        select(AutomationRun)
        .where(AutomationRun.user_id == user_id, AutomationRun.status == AutomationRunStatus.RUNNING)
        .order_by(AutomationRun.started_at.desc())
    ).first()


def last_run(db: Session, user_id: uuid.UUID) -> AutomationRun | None:
    return db.scalars(
        select(AutomationRun).where(AutomationRun.user_id == user_id).order_by(AutomationRun.started_at.desc())
    ).first()


def get_run(db: Session, user_id: uuid.UUID, run_id: uuid.UUID) -> AutomationRun:
    run = db.scalars(
        select(AutomationRun).where(AutomationRun.id == run_id, AutomationRun.user_id == user_id)
    ).first()
    if run is None:
        raise NotFoundError("Automation run not found")
    return run


def list_runs(db: Session, user_id: uuid.UUID, pagination: Pagination) -> PageResponse[AutomationRunRead]:
    from app.modules.common.pagination import paginate

    stmt = select(AutomationRun).where(AutomationRun.user_id == user_id).order_by(AutomationRun.started_at.desc())
    page = paginate(db, stmt, pagination, transform=to_run_read)
    return PageResponse[AutomationRunRead](items=page.items, total=page.total, page=page.page, page_size=page.page_size)


def config_snapshot(config: AutomationConfig) -> dict[str, Any]:
    """JSON-safe copy of the settings a run executed with."""
    return {
        "enabled": bool(config.enabled),
        "schedule_time": config.schedule_time,
        "timezone": config.timezone,
        "daily_application_limit": int(config.daily_application_limit or 0),
        "per_platform_limit": dict(config.per_platform_limit or {}),
        "min_match_score": int(config.min_match_score or 0),
        "prioritize_priority_companies": bool(config.prioritize_priority_companies),
        "only_posted_within_hours": int(config.only_posted_within_hours or 24),
        "enabled_sources": [str(s) for s in (config.enabled_sources or [])],
        "delay_between_actions_seconds": float(config.delay_between_actions_seconds or 0.0),
        "retry_limit": int(config.retry_limit or 0),
        "auto_submit_enabled": bool(config.auto_submit_enabled),
        "auto_submit_sources": [str(s) for s in (config.auto_submit_sources or [])],
        # Resolved per enabled source so the run log shows the mode each one ran in. The
        # pipeline's search step overwrites this with the adapters it actually resolved.
        "source_modes": {s.value: m.value for s, m in resolved_source_modes(config, _snapshot_sources(config)).items()},
        "auto_generate_cover_letters": bool(config.auto_generate_cover_letters),
    }


def _snapshot_sources(config: AutomationConfig) -> list[JobSourceType]:
    """The sources a run would search: the explicit list, else everything that can discover."""
    requested: list[JobSourceType] = []
    for value in config.enabled_sources or []:
        try:
            source = JobSourceType(str(value).upper())
        except ValueError:
            continue
        if source not in requested:
            requested.append(source)
    if requested:
        return requested
    from app.modules.adapters.registry import DISCOVERY_SOURCES

    return list(DISCOVERY_SOURCES)


def ensure_not_running(db: Session, user_id: uuid.UUID) -> None:
    """Raise :class:`ConflictError` when a run is already RUNNING (DB **or** lock)."""
    existing = running_run(db, user_id)
    if existing is not None:
        raise ConflictError("An automation run is already in progress", code="automation_running")
    if locks.is_locked(user_id):
        raise ConflictError("An automation run is already in progress", code="automation_running")


def create_run(
    db: Session,
    user_id: uuid.UUID,
    trigger: AutomationRunTrigger,
    *,
    dry_run: bool = False,
    config: AutomationConfig | None = None,
) -> AutomationRun:
    """Insert a RUNNING :class:`AutomationRun` row for the pipeline to fill in."""
    config = config or get_config(db, user_id)
    snapshot = config_snapshot(config)
    snapshot["dry_run"] = bool(dry_run)
    run = AutomationRun(
        user_id=user_id,
        trigger=trigger,
        status=AutomationRunStatus.RUNNING,
        started_at=utcnow(),
        current_step="search",
        stats={},
        steps=[],
        config_snapshot=snapshot,
    )
    db.add(run)
    db.flush()
    logger.info("Created automation run %s (trigger=%s, dry_run=%s)", run.id, trigger.value, dry_run)
    return run


# --------------------------------------------------------------------------- cancellation


def request_cancel(run_id: uuid.UUID) -> None:
    with _cancel_guard:
        _cancel_requests.add(run_id)


def is_cancel_requested(run_id: uuid.UUID) -> bool:
    with _cancel_guard:
        return run_id in _cancel_requests


def clear_cancel(run_id: uuid.UUID) -> None:
    with _cancel_guard:
        _cancel_requests.discard(run_id)


def cancel_run(db: Session, user_id: uuid.UUID, run_id: uuid.UUID) -> AutomationRun:
    """Mark a run CANCELLED; the pipeline stops at the next step boundary."""
    run = get_run(db, user_id, run_id)
    if run.status != AutomationRunStatus.RUNNING:
        raise ConflictError("Only a running automation can be cancelled", code="run_not_running")
    request_cancel(run.id)
    run.status = AutomationRunStatus.CANCELLED
    run.finished_at = utcnow()
    run.error = run.error or "Cancelled by the user"
    db.flush()
    # Deliberately *not* releasing the lock: the pipeline is still executing the current
    # step (it only notices the cancel at the next boundary) and it releases its own
    # token when it stops. Force-releasing here let a new run start alongside the dying
    # one, and two runs each computing the budget once can spend 2x the daily limit.
    # A hard process kill is covered by the lock's TTL.
    audit(
        db,
        action="automation.run_finished",
        message="Automation run cancelled by the user",
        user_id=user_id,
        automation_run_id=run.id,
        actor=Actor.USER,
        meta={"status": run.status.value},
    )
    logger.info("Automation run %s cancelled by user %s", run.id, user_id)
    return run


# --------------------------------------------------------------------------- manual run


def _spawn(target: Callable[..., Any], *args: Any, **kwargs: Any) -> threading.Thread:
    """Executor seam — a daemon thread by default, patchable in tests."""
    thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True, name="automation-run")
    thread.start()
    return thread


def _background_pipeline(
    user_id: uuid.UUID, run_id: uuid.UUID, dry_run: bool, token: str | None = None
) -> None:
    """Execute a manual run in its own thread and **always** close the row out.

    The row is committed before the thread starts, so anything that escapes here would
    otherwise leave it ``RUNNING`` for ever - and ``ensure_not_running`` would then
    reject every future run for this user with a permanent 409.
    """
    from app.core.database import session_scope
    from app.modules.automation.pipeline import run_pipeline

    try:
        run_pipeline(
            user_id,
            AutomationRunTrigger.MANUAL,
            run_id=run_id,
            dry_run=dry_run,
            acquire=token is None,
        )
    except Exception as exc:  # the pipeline records its own step failures; this is the backstop
        logger.exception("Background automation run %s failed: %s", run_id, exc)
        try:
            with session_scope() as db:
                run = db.get(AutomationRun, run_id)
                if run is not None and run.status == AutomationRunStatus.RUNNING:
                    run.status = AutomationRunStatus.FAILED
                    run.finished_at = utcnow()
                    run.current_step = None
                    run.error = str(exc)[:1000]
        except Exception:  # pragma: no cover - defensive
            logger.exception("Could not close automation run %s", run_id)
    finally:
        if token is not None:
            locks.release_lock(user_id, token)


def start_manual_run(
    db: Session,
    user_id: uuid.UUID,
    *,
    dry_run: bool = False,
    background: bool = True,
) -> AutomationRun:
    """``POST /automation/run`` — create the run row and execute the pipeline.

    ``background=False`` executes synchronously (used by tests and the seed script).
    """
    ensure_not_running(db, user_id)
    config = get_config(db, user_id)

    if not background:
        from app.modules.automation.pipeline import run_pipeline

        run = create_run(db, user_id, AutomationRunTrigger.MANUAL, dry_run=dry_run, config=config)
        return run_pipeline(user_id, AutomationRunTrigger.MANUAL, run_id=run.id, dry_run=dry_run, db=db)

    # Take the lock *before* inserting the row. ``ensure_not_running`` is only a read, so
    # two requests (or a request and the worker's minute tick) could otherwise both pass
    # the guard and create two RUNNING runs for the same user - §14 allows exactly one.
    token = locks.acquire_lock(user_id)
    if token is None:
        raise ConflictError("An automation run is already in progress", code="automation_running")
    try:
        run = create_run(db, user_id, AutomationRunTrigger.MANUAL, dry_run=dry_run, config=config)
        # The worker thread opens its own session, so the row has to be visible to it.
        db.commit()
    except Exception:
        locks.release_lock(user_id, token)
        raise
    _spawn(_background_pipeline, user_id, run.id, dry_run, token)
    return run


# --------------------------------------------------------------------------- status


def get_status(db: Session, user_id: uuid.UUID) -> AutomationStatusRead:
    """``GET /automation/status``."""
    config = get_config(db, user_id)
    latest = last_run(db, user_id)
    budget = limits.compute_budget(db, user_id, config)
    next_run_at = config.next_run_at if config.enabled else None
    if config.enabled:
        computed = compute_next_run_at(config)
        if computed is not None:
            next_run_at = computed
            config.next_run_at = computed
    return AutomationStatusRead(
        enabled=bool(config.enabled),
        next_run_at=next_run_at,
        last_run=to_run_read(latest) if latest is not None else None,
        running=latest is not None and latest.status == AutomationRunStatus.RUNNING,
        today=TodayStatus(
            applications_submitted=budget.submitted_today,
            limit_remaining=budget.remaining,
            daily_limit=budget.daily_limit,
        ),
    )
