"""Daily / per-platform application budget for the automation pipeline (contract §14).

The safety rails are deliberately conservative: the remaining budget counts both the
applications that were actually **submitted today** (in the user's own timezone) and the
ones the current run has already put in flight, so a crashed-and-restarted run can never
blow past ``daily_application_limit``.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.automation import AutomationConfig
from app.models.base import utcnow
from app.models.enums import ApplicationStatus, JobSourceType

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Asia/Kolkata"
#: Statuses that mean "this run already committed to an application".
IN_FLIGHT_STATUSES: tuple[ApplicationStatus, ...] = (ApplicationStatus.QUEUED, ApplicationStatus.IN_PROGRESS)

__all__ = [
    "Budget",
    "compute_budget",
    "day_bounds",
    "resolve_zone",
    "submitted_today",
]


def resolve_zone(timezone_name: str | None) -> ZoneInfo:
    """``ZoneInfo`` for a user timezone, falling back to the project default."""
    for candidate in (timezone_name, DEFAULT_TIMEZONE, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            logger.warning("Unknown timezone %r; falling back", candidate)
    return ZoneInfo("UTC")  # pragma: no cover - UTC always resolves


def day_bounds(timezone_name: str | None, now: datetime | None = None) -> tuple[datetime, datetime]:
    """UTC bounds of "today" as the *user* sees it: ``[start, end)``."""
    zone = resolve_zone(timezone_name)
    now = now or utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local_now = now.astimezone(zone)
    start_local = datetime.combine(local_now.date(), time.min, tzinfo=zone)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


@dataclass
class Budget:
    """How many applications the pipeline may still send."""

    daily_limit: int
    submitted_today: int = 0
    in_flight: int = 0
    remaining: int = 0
    per_platform_limit: dict[str, int] = field(default_factory=dict)
    per_platform_used: dict[str, int] = field(default_factory=dict)
    per_platform_remaining: dict[str, int] = field(default_factory=dict)
    timezone: str = DEFAULT_TIMEZONE
    day_start: datetime | None = None
    day_end: datetime | None = None

    # -- runtime helpers (the pipeline decrements as it queues) ------------

    def remaining_for(self, source: JobSourceType | str | None) -> int:
        """Remaining slots for ``source`` — the stricter of daily and per-platform."""
        if source is None:
            return self.remaining
        key = source.value if isinstance(source, JobSourceType) else str(source)
        if key not in self.per_platform_limit:
            return self.remaining
        return max(0, min(self.remaining, self.per_platform_remaining.get(key, 0)))

    def can_take(self, source: JobSourceType | str | None) -> bool:
        return self.remaining_for(source) > 0

    def take(self, source: JobSourceType | str | None) -> None:
        """Record that one slot was consumed by ``source``."""
        self.remaining = max(0, self.remaining - 1)
        if source is None:
            return
        key = source.value if isinstance(source, JobSourceType) else str(source)
        self.per_platform_used[key] = self.per_platform_used.get(key, 0) + 1
        if key in self.per_platform_limit:
            self.per_platform_remaining[key] = max(0, self.per_platform_remaining.get(key, 0) - 1)

    def as_dict(self) -> dict[str, object]:
        return {
            "daily_limit": self.daily_limit,
            "submitted_today": self.submitted_today,
            "in_flight": self.in_flight,
            "remaining": self.remaining,
            "timezone": self.timezone,
            "per_platform_limit": dict(self.per_platform_limit),
            "per_platform_used": dict(self.per_platform_used),
            "per_platform_remaining": dict(self.per_platform_remaining),
        }


def _coerce_limits(raw: dict[str, object] | None) -> dict[str, int]:
    """Keep only ``{JobSourceType: positive int}`` entries."""
    out: dict[str, int] = {}
    for key, value in (raw or {}).items():
        try:
            source = JobSourceType(str(key).upper())
            limit = int(value)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            logger.warning("Ignoring invalid per-platform limit %r=%r", key, value)
            continue
        if limit >= 0:
            out[source.value] = limit
    return out


def submitted_today(
    db: Session,
    user_id: uuid.UUID,
    timezone_name: str | None,
    *,
    now: datetime | None = None,
) -> int:
    """Applications actually submitted during the user's current calendar day."""
    start, end = day_bounds(timezone_name, now)
    stmt = select(func.count(Application.id)).where(
        Application.user_id == user_id,
        Application.applied_at.is_not(None),
        Application.applied_at >= start,
        Application.applied_at < end,
    )
    return int(db.scalar(stmt) or 0)


def _per_platform_used(
    db: Session,
    user_id: uuid.UUID,
    *,
    start: datetime,
    end: datetime,
    run_id: uuid.UUID | None,
) -> dict[str, int]:
    applied_today = and_(
        Application.applied_at.is_not(None),
        Application.applied_at >= start,
        Application.applied_at < end,
    )
    conditions = [applied_today]
    if run_id is not None:
        conditions.append(and_(Application.automation_run_id == run_id, Application.status.in_(IN_FLIGHT_STATUSES)))
    clause = (
        select(Application.source, func.count(Application.id))
        .where(Application.user_id == user_id, Application.source.is_not(None), or_(*conditions))
        .group_by(Application.source)
    )
    rows = db.execute(clause).all()
    out: dict[str, int] = {}
    for source, count in rows:
        if source is None:
            continue
        key = source.value if isinstance(source, JobSourceType) else str(source)
        out[key] = out.get(key, 0) + int(count)
    return out


def compute_budget(
    db: Session,
    user_id: uuid.UUID,
    config: AutomationConfig,
    *,
    run_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> Budget:
    """Remaining daily + per-platform budget for ``user_id``.

    ``remaining = daily_application_limit - (applied today in the user's timezone +
    applications this run already queued / started)``.
    """
    timezone_name = getattr(config, "timezone", None) or DEFAULT_TIMEZONE
    start, end = day_bounds(timezone_name, now)
    done = submitted_today(db, user_id, timezone_name, now=now)

    in_flight = 0
    if run_id is not None:
        in_flight = int(
            db.scalar(
                select(func.count(Application.id)).where(
                    Application.user_id == user_id,
                    Application.automation_run_id == run_id,
                    Application.status.in_(IN_FLIGHT_STATUSES),
                    or_(Application.applied_at.is_(None), Application.applied_at < start, Application.applied_at >= end),
                )
            )
            or 0
        )

    daily_limit = max(0, int(getattr(config, "daily_application_limit", 0) or 0))
    per_platform_limit = _coerce_limits(getattr(config, "per_platform_limit", None))
    per_platform_used = _per_platform_used(db, user_id, start=start, end=end, run_id=run_id)
    per_platform_remaining = {
        source: max(0, limit - per_platform_used.get(source, 0)) for source, limit in per_platform_limit.items()
    }

    budget = Budget(
        daily_limit=daily_limit,
        submitted_today=done,
        in_flight=in_flight,
        remaining=max(0, daily_limit - done - in_flight),
        per_platform_limit=per_platform_limit,
        per_platform_used=per_platform_used,
        per_platform_remaining=per_platform_remaining,
        timezone=timezone_name,
        day_start=start,
        day_end=end,
    )
    logger.debug("Budget for user %s: %s", user_id, budget.as_dict())
    return budget
