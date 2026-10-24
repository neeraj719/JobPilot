"""Background scheduler (contract §14).

Five jobs, all idempotent and all safe to run in several processes because every
pipeline execution goes through the per-user lock in :mod:`app.modules.automation.locks`:

``tick_scheduled_runs``              every minute — start the daily pipeline for users whose
                                     ``schedule_time`` has passed in *their* timezone today
``sync_gmail``                       every 30 minutes — pull new mail for connected accounts
``sync_linkedin``                    hourly tick — re-read LinkedIn for connections with
                                     auto-sync on whose last sync is ``LINKEDIN_AUTO_SYNC_HOURS``
                                     old; stores the diff and notifies, **never** writes the profile
``mark_no_response``                 nightly 02:00 UTC — APPLIED + 21 days + silence → NO_RESPONSE
``cleanup_expired_browser_sessions`` daily 03:00 UTC — expire stale Playwright storage state

Who the rows say wrote them (``created_by`` / ``updated_by``, see :mod:`app.core.actor`)
follows the same split. ``tick_scheduled_runs`` and ``sync_gmail`` act *for* a user and
publish that user as the actor — the pipeline does it in ``run_pipeline`` and the ingest
in ``integrations.service.sync_gmail`` — so their rows carry the owner. The two
housekeeping jobs are the scheduler's own decisions, taken on nobody's behalf, so they
write with no actor and the rows read as system writes (``NULL``). That is the honest
answer to "who marked this application NO_RESPONSE": not the candidate.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.database import session_scope
from app.models.application import Application
from app.models.automation import AutomationConfig, BrowserSession
from app.models.base import utcnow
from app.models.enums import (
    Actor,
    ApplicationStatus,
    AutomationRunTrigger,
    BrowserSessionStatus,
)
from app.modules.automation import limits, locks, service as automation_service

logger = logging.getLogger(__name__)

#: An APPLIED application with no reply after this many days is marked NO_RESPONSE.
NO_RESPONSE_AFTER_DAYS = 21
TICK_SECONDS = 60
GMAIL_SYNC_MINUTES = 30
#: The LinkedIn job ticks hourly; each connection is only re-read once it is due.
LINKEDIN_TICK_MINUTES = 60

__all__ = [
    "build_scheduler",
    "cleanup_expired_browser_sessions",
    "due_users",
    "mark_no_response",
    "sync_gmail",
    "sync_linkedin",
    "tick_scheduled_runs",
]


# --------------------------------------------------------------------------- daily pipeline


def _already_ran_today(config: AutomationConfig, now: datetime) -> bool:
    """True when ``last_run_at`` falls on today's date in the user's timezone."""
    if config.last_run_at is None:
        return False
    zone = limits.resolve_zone(config.timezone)
    last = config.last_run_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return last.astimezone(zone).date() >= now.astimezone(zone).date()


def _scheduled_today(config: AutomationConfig, now: datetime) -> datetime:
    """Today's ``schedule_time`` in the user's timezone, as UTC."""
    zone = limits.resolve_zone(config.timezone)
    match = automation_service.SCHEDULE_TIME_RE.match((config.schedule_time or "09:00").strip())
    hour, minute = (int(match.group(1)), int(match.group(2))) if match else (9, 0)
    local_today = now.astimezone(zone).date()
    return datetime(local_today.year, local_today.month, local_today.day, hour, minute, tzinfo=zone).astimezone(timezone.utc)


def due_users(db: Session, now: datetime | None = None) -> list[uuid.UUID]:
    """Users whose scheduled automation should start right now.

    The daily automation belongs to the Job Apply workspace module: a user for whom ``apply``
    is unavailable (switched off platform-wide, or for that account, or above their role) is
    skipped, exactly as the ``automation`` API refuses them with ``403 module_disabled``.
    """
    from app.modules.workspace.service import module_available

    now = now or utcnow()
    due: list[uuid.UUID] = []
    for config in db.scalars(select(AutomationConfig).where(AutomationConfig.enabled.is_(True))):
        if _already_ran_today(config, now):
            continue
        if now < _scheduled_today(config, now):
            continue
        if not module_available(db, config.user_id, "apply"):
            logger.info("Skipping scheduled automation for user %s: the Job Apply module is off", config.user_id)
            continue
        due.append(config.user_id)
    return due


def _run_for_user(user_id: uuid.UUID) -> None:
    """Execute one scheduled pipeline run under the user's lock."""
    from app.modules.automation.pipeline import run_pipeline

    token = locks.acquire_lock(user_id)
    if token is None:
        logger.info("Skipping scheduled run for user %s — another run holds the lock", user_id)
        return
    try:
        run_pipeline(user_id, AutomationRunTrigger.SCHEDULED, acquire=False)
    except Exception as exc:  # pragma: no cover - the pipeline records its own failures
        logger.exception("Scheduled automation for user %s failed: %s", user_id, exc)
    finally:
        locks.release_lock(user_id, token)


def tick_scheduled_runs(now: datetime | None = None, *, background: bool = True) -> list[uuid.UUID]:
    """Minute tick: start the pipeline for every user whose slot has arrived."""
    with session_scope() as db:
        users = due_users(db, now)
    for user_id in users:
        logger.info("Starting scheduled automation for user %s", user_id)
        if background:
            threading.Thread(target=_run_for_user, args=(user_id,), daemon=True, name=f"automation-{user_id}").start()
        else:
            _run_for_user(user_id)
    return users


# --------------------------------------------------------------------------- gmail


def sync_gmail() -> int:
    """Pull new mail for every connected Gmail integration. Returns users synced."""
    try:
        from app.modules.integrations.service import sync_all_connected
    except Exception as exc:
        logger.debug("integrations.service.sync_all_connected unavailable: %s", exc)
        return 0
    try:
        result = sync_all_connected()
    except TypeError:
        with session_scope() as db:
            result = sync_all_connected(db)
    except Exception as exc:  # pragma: no cover - never kill the scheduler
        logger.exception("Gmail sync failed: %s", exc)
        return 0
    count = len(result) if isinstance(result, (list, tuple, dict)) else int(result or 0)
    logger.info("Gmail sync finished for %s account(s)", count)
    return count


# --------------------------------------------------------------------------- linkedin


def sync_linkedin(now: datetime | None = None) -> dict[str, str]:
    """Re-read LinkedIn for due auto-sync connections; notify about changes, never apply them.

    Acts for each connection's owner (``integrations.linkedin_service`` publishes the actor);
    users without the Resume Studio module are skipped.
    """
    try:
        from app.modules.integrations.linkedin_service import sync_due_connections
    except Exception as exc:  # pragma: no cover - never kill the scheduler
        logger.debug("linkedin_service.sync_due_connections unavailable: %s", exc)
        return {}
    try:
        with session_scope() as db:
            return sync_due_connections(db, now)
    except Exception as exc:  # pragma: no cover - never kill the scheduler
        logger.exception("LinkedIn sync failed: %s", exc)
        return {}


# --------------------------------------------------------------------------- housekeeping


def _transition_no_response(db: Session, application: Application, message: str) -> bool:
    """Use the applications module when present, otherwise update the row directly."""
    try:
        from app.modules.applications.service import transition
    except Exception as exc:
        logger.debug("applications.service.transition unavailable: %s", exc)
    else:
        try:
            transition(db, application, ApplicationStatus.NO_RESPONSE, actor=Actor.SCHEDULER, message=message)
            return True
        except Exception as exc:  # pragma: no cover - fall through to the direct update
            logger.warning("transition() failed for %s: %s", application.id, exc)
    application.status = ApplicationStatus.NO_RESPONSE
    application.last_update_at = utcnow()
    audit(
        db,
        action="application.no_response",
        message=message,
        user_id=application.user_id,
        application_id=application.id,
        actor=Actor.SCHEDULER,
    )
    return True


def mark_no_response(days: int = NO_RESPONSE_AFTER_DAYS, now: datetime | None = None) -> int:
    """APPLIED for more than ``days`` with no reply → ``NO_RESPONSE``."""
    now = now or utcnow()
    cutoff = now - timedelta(days=days)
    updated = 0
    with session_scope() as db:
        stmt = select(Application).where(
            Application.status == ApplicationStatus.APPLIED,
            Application.applied_at.is_not(None),
            Application.applied_at < cutoff,
            Application.last_response_at.is_(None),
        )
        for application in db.scalars(stmt).unique():
            _transition_no_response(db, application, f"No response after {days} days")
            updated += 1
    if updated:
        logger.info("Marked %d applications as NO_RESPONSE", updated)
    return updated


def cleanup_expired_browser_sessions(now: datetime | None = None) -> int:
    """Expire browser sessions past ``expires_at`` and drop their stored state."""
    now = now or utcnow()
    cleaned = 0
    with session_scope() as db:
        stmt = select(BrowserSession).where(
            BrowserSession.status == BrowserSessionStatus.ACTIVE,
            BrowserSession.expires_at.is_not(None),
            BrowserSession.expires_at < now,
        )
        for session_row in db.scalars(stmt):
            session_row.status = BrowserSessionStatus.EXPIRED
            session_row.encrypted_storage_state = None
            cleaned += 1
    if cleaned:
        logger.info("Expired %d browser session(s)", cleaned)
    return cleaned


# --------------------------------------------------------------------------- scheduler


def build_scheduler() -> BackgroundScheduler:
    """Wire the five jobs onto a UTC :class:`BackgroundScheduler` (not started)."""
    scheduler = BackgroundScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300})
    scheduler.add_job(
        tick_scheduled_runs,
        trigger="interval",
        seconds=TICK_SECONDS,
        id="tick_scheduled_runs",
        replace_existing=True,
        name="Start due automation runs",
    )
    scheduler.add_job(
        sync_gmail,
        trigger="interval",
        minutes=GMAIL_SYNC_MINUTES,
        id="sync_gmail",
        replace_existing=True,
        name="Sync connected Gmail accounts",
    )
    scheduler.add_job(
        sync_linkedin,
        trigger="interval",
        minutes=LINKEDIN_TICK_MINUTES,
        id="sync_linkedin",
        replace_existing=True,
        name="Check LinkedIn connections for changes (notify only)",
    )
    scheduler.add_job(
        mark_no_response,
        trigger="cron",
        hour=2,
        minute=0,
        id="mark_no_response",
        replace_existing=True,
        name="Mark silent applications as NO_RESPONSE",
    )
    scheduler.add_job(
        cleanup_expired_browser_sessions,
        trigger="cron",
        hour=3,
        minute=0,
        id="cleanup_expired_browser_sessions",
        replace_existing=True,
        name="Clean up expired browser sessions",
    )
    logger.info("Scheduler built with %d jobs", len(scheduler.get_jobs()))
    return scheduler
