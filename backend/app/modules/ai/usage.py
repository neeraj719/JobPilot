"""Usage and estimated cost of a user's AI calls (``GET /ai/usage``) and retention pruning.

Costs are **estimates**: tokens come from the provider SDK when it reports them (else from
text length, flagged), prices from ``ai.registry`` with their ``prices_as_of`` date. The
provider's own billing console is the source of truth; the page says so.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ValidationFailed
from app.models.ai_settings import AiUsageEvent
from app.modules.ai import registry
from app.modules.ai.errors import label
from app.modules.ai.routing import CONFIGURABLE_WORKFLOWS

logger = logging.getLogger(__name__)

RANGES = ("7d", "30d", "month")
NOTE = (
    "Estimated from token counts and JobPilot's price list; your provider's billing console is the source of truth. "
    "Local models cost nothing."
)


def range_start(range_: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if range_ == "7d":
        return (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    if range_ == "30d":
        return (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
    if range_ == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValidationFailed("range must be one of 7d, 30d, month", code="invalid_range")


def _bucket() -> dict[str, Any]:
    return {"calls": 0, "ok": 0, "errors": 0, "fallbacks": 0, "input_tokens": 0, "output_tokens": 0,
            "estimated_cost_usd": 0.0, "cost_unknown_calls": 0, "tokens_estimated_calls": 0, "_duration": 0}


def _add(bucket: dict[str, Any], event: AiUsageEvent) -> None:
    status = str(event.status.value if hasattr(event.status, "value") else event.status)
    bucket["calls"] += 1
    bucket["ok"] += status == "OK"
    bucket["errors"] += status == "ERROR"
    bucket["fallbacks"] += status == "FALLBACK"
    bucket["input_tokens"] += int(event.input_tokens or 0)
    bucket["output_tokens"] += int(event.output_tokens or 0)
    if event.estimated_cost_usd is None:
        if status != "ERROR":
            bucket["cost_unknown_calls"] += 1
    else:
        bucket["estimated_cost_usd"] += float(event.estimated_cost_usd)
    bucket["tokens_estimated_calls"] += bool(event.tokens_estimated)
    bucket["_duration"] += int(event.duration_ms or 0)


def _finish(bucket: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in bucket.items() if not k.startswith("_")}
    out["estimated_cost_usd"] = round(out["estimated_cost_usd"], 6)
    out["avg_duration_ms"] = int(bucket["_duration"] / bucket["calls"]) if bucket["calls"] else None
    return out


def usage_summary(db: Session, user_id: uuid.UUID, range_: str = "30d", *, settings_row: Any = None) -> dict[str, Any]:
    if range_ not in RANGES:
        raise ValidationFailed("range must be one of 7d, 30d, month", code="invalid_range")
    now = datetime.now(timezone.utc)
    since = range_start(range_, now)
    events = list(
        db.scalars(
            select(AiUsageEvent)
            .where(AiUsageEvent.user_id == user_id, AiUsageEvent.created_at >= since)
            .order_by(AiUsageEvent.created_at)
        )
    )
    totals = _bucket()
    by_workflow: dict[str, dict[str, Any]] = defaultdict(_bucket)
    by_provider: dict[tuple[str, str], dict[str, Any]] = defaultdict(_bucket)
    days: dict[str, dict[str, Any]] = {}
    cursor = since
    while cursor.date() <= now.date():
        days[cursor.date().isoformat()] = {"date": cursor.date().isoformat(), "calls": 0, "errors": 0, "estimated_cost_usd": 0.0, "tokens": 0}
        cursor += timedelta(days=1)
    for event in events:
        _add(totals, event)
        _add(by_workflow[event.workflow], event)
        _add(by_provider[(event.provider, event.model)], event)
        day = days.setdefault(event.created_at.date().isoformat(), {"date": event.created_at.date().isoformat(), "calls": 0, "errors": 0, "estimated_cost_usd": 0.0, "tokens": 0})
        day["calls"] += 1
        day["errors"] += str(getattr(event.status, "value", event.status)) == "ERROR"
        day["estimated_cost_usd"] = round(day["estimated_cost_usd"] + float(event.estimated_cost_usd or 0), 6)
        day["tokens"] += int(event.input_tokens or 0) + int(event.output_tokens or 0)

    workflow_rows = [
        {"key": key, "label": CONFIGURABLE_WORKFLOWS.get(key, key), **_finish(bucket)}
        for key, bucket in sorted(by_workflow.items(), key=lambda kv: -kv[1]["calls"])
    ]
    provider_rows = [
        {"key": f"{provider}/{model}", "label": f"{label(provider)} · {model}", "provider": provider, "model": model, **_finish(bucket)}
        for (provider, model), bucket in sorted(by_provider.items(), key=lambda kv: -kv[1]["calls"])
    ]
    used_providers = {e.provider for e in events}
    prices_as_of = {
        p: registry.PROVIDERS[p].prices_as_of  # type: ignore[misc]
        for p in sorted(used_providers)
        if p in registry.PROVIDERS and registry.PROVIDERS[p].prices_as_of
    }
    limits: dict[str, Any] = {}
    if settings_row is not None:
        limits = {
            "daily_call_limit": settings_row.daily_call_limit,
            "monthly_budget_usd": float(settings_row.monthly_budget_usd) if settings_row.monthly_budget_usd is not None else None,
        }
    limits["server_daily_limit_hosted"] = settings.AI_DEFAULT_DAILY_CALL_LIMIT
    today = now.date().isoformat()
    limits["calls_today"] = days.get(today, {}).get("calls", 0)
    month_start = range_start("month", now)
    if range_ == "month":
        limits["spent_this_month_usd"] = round(totals["estimated_cost_usd"], 6)
    else:
        limits["spent_this_month_usd"] = round(
            sum(float(e.estimated_cost_usd or 0) for e in events if e.created_at >= month_start), 6
        )
    return {
        "range": range_,
        "since": since,
        "totals": _finish(totals),
        "by_workflow": workflow_rows,
        "by_provider": provider_rows,
        "daily": list(days.values()),
        "estimated": True,
        "prices_as_of": prices_as_of,
        "limits": limits,
        "note": NOTE,
    }


def prune_usage_events(days: int | None = None, *, now: datetime | None = None) -> int:
    """Delete usage events older than ``AI_USAGE_RETENTION_DAYS`` (worker job). They hold no
    prompt text, only counts — retention just bounds the table."""
    from app.core.database import session_scope

    keep = int(days if days is not None else settings.AI_USAGE_RETENTION_DAYS)
    if keep <= 0:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=keep)
    with session_scope() as db:
        result = db.execute(delete(AiUsageEvent).where(AiUsageEvent.created_at < cutoff))
        removed = int(result.rowcount or 0)
    if removed:
        logger.info("Pruned %d AI usage events older than %d days", removed, keep)
    return removed


__all__ = ["RANGES", "prune_usage_events", "range_start", "usage_summary"]
