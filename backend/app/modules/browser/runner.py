"""``ApplicationRunner`` - one automated application attempt (CONTRACTS.md section 12).

The runner is the only place that drives an adapter end to end::

    load application -> pick adapter -> (browser session) -> start_application
        -> fill_application -> interpret the ApplyStepResult

and it always ends in one of four states:

``REQUIRES_USER``  a blocker (CAPTCHA/OTP/login) or a question the profile cannot answer.
                   The automation stops and creates ``NEEDS_USER_INPUT`` answers so the
                   user can finish it in the UI. Nothing is ever bypassed.
``PAUSED``         the form is filled and waiting for a human to approve submission.
``SUCCESS``        auto-submit was explicitly enabled for this source, so it went out.
``FAILED``         everything else, with a retry for genuinely temporary errors.

No exception escapes :meth:`ApplicationRunner.run` - a crash is recorded on the
application and audited instead of killing the worker thread.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import audit
from app.core.config import settings
from app.core.database import session_scope
from app.models.application import Application
from app.models.enums import (
    Actor,
    AnswerStatus,
    ApplicationEventType,
    AutomationState,
    JobSourceType,
    PauseReason,
)

logger = logging.getLogger(__name__)

#: Seconds to wait between retries of a temporary error (short, bounded).
RETRY_BACKOFF_SECONDS: float = 1.0


def temporary_errors() -> tuple[type[BaseException], ...]:
    """Error types worth retrying (network hiccups, page timeouts)."""
    errors: list[type[BaseException]] = [ConnectionError, TimeoutError, OSError]
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        errors.extend([PlaywrightTimeoutError, PlaywrightError])
    except Exception:  # pragma: no cover - Playwright is optional at import time
        logger.debug("Playwright is not importable; retrying only on stdlib network errors")
    return tuple(errors)


def snapshot_summary(snapshot: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """``(detected field labels, filled field keys)`` for the audit trail."""
    if not isinstance(snapshot, dict):
        return [], []
    detected: list[str] = []
    filled: list[str] = []
    for row in snapshot.get("fields") or []:
        if not isinstance(row, dict):
            continue
        detected.append(str(row.get("key") or row.get("mapped_to") or row.get("label") or "unnamed"))
        if row.get("status") == "filled" and row.get("value") not in (None, ""):
            filled.append(str(row.get("key") or row.get("label") or "unnamed"))
    for row in snapshot.get("filled") or []:
        if isinstance(row, dict):
            filled.append(str(row.get("key") or row.get("selector") or "unnamed"))
    # keep the order but drop duplicates
    return list(dict.fromkeys(detected)), list(dict.fromkeys(filled))


class ApplicationRunner:
    """Run one application attempt. Build it in the thread that will drive the page."""

    def __init__(self, application_id: uuid.UUID | str, db: Session | None = None) -> None:
        self.application_id = uuid.UUID(str(application_id))
        self._db = db
        self._owns_session = db is None

    # -- entry point -------------------------------------------------------

    def run(self) -> Application | None:
        """Execute the attempt. Never raises."""
        if self._db is not None:
            return self._run_with(self._db)
        with session_scope() as db:
            return self._run_with(db)

    # -- plumbing ----------------------------------------------------------

    def _load(self, db: Session) -> Application | None:
        return db.scalars(
            select(Application)
            .where(Application.id == self.application_id)
            .options(selectinload(Application.answers), selectinload(Application.events))
        ).first()

    def _run_with(self, db: Session) -> Application | None:
        from app.modules.applications import service as applications_service

        application = self._load(db)
        if application is None:
            logger.warning("Application %s no longer exists; nothing to run", self.application_id)
            return None
        try:
            self._execute(db, application)
        except Exception as exc:  # noqa: BLE001 - the runner absorbs everything
            logger.exception("Application run %s failed", self.application_id)
            try:
                applications_service.mark_failed(db, application, f"{type(exc).__name__}: {exc}", final=True)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Could not record the failure for application %s", self.application_id)
        db.flush()
        return application

    # -- the attempt loop --------------------------------------------------

    def _execute(self, db: Session, application: Application) -> None:
        from app.modules.adapters.registry import get_adapter
        from app.modules.applications import service as applications_service

        config = applications_service.get_automation_config(db, application.user_id)
        source = application.source or applications_service.pick_apply_source(application.job)
        if source is None:
            applications_service.mark_failed(db, application, "This job has no source to apply through", final=True)
            return
        application.source = source
        adapter = get_adapter(source)

        retry_limit = max(1, int(config.retry_limit or 1))
        retryable = temporary_errors()
        for attempt in range(1, retry_limit + 1):
            application.automation_state = AutomationState.RUNNING
            db.flush()
            try:
                self._attempt(db, application, adapter, source, config)
                return
            except retryable as exc:  # noqa: PERF203 - the retry is the point
                if attempt >= retry_limit:
                    applications_service.mark_failed(db, application, f"{type(exc).__name__}: {exc}", final=True)
                    return
                application.automation_state = AutomationState.RETRYING
                application.retry_count = int(application.retry_count or 0) + 1
                application.last_error = f"{type(exc).__name__}: {exc}"[:4000]
                applications_service.record_event(
                    db,
                    application,
                    ApplicationEventType.AUTOMATION,
                    f"Temporary error on attempt {attempt}, retrying: {exc}",
                    actor=Actor.AUTOMATION,
                    meta={"attempt": attempt, "error": type(exc).__name__},
                )
                db.flush()
                logger.warning("Application %s attempt %d failed (%s); retrying", application.id, attempt, exc)
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    def _attempt(self, db: Session, application: Application, adapter: Any, source: JobSourceType, config: Any) -> None:
        from app.modules.adapters.base import ApplyContext
        from app.modules.applications import service as applications_service
        from app.modules.profiles.service import build_candidate_context

        candidate = build_candidate_context(db, application.user_id, application.resume_id)
        ctx = ApplyContext(
            application=application,
            job=application.job,
            candidate=candidate,
            answers=list(application.answers or []),
            page=None,
            db=db,
            settings=settings,
        )

        if not adapter.uses_browser:
            self._steps(db, application, adapter, ctx, None, config)
            return

        from app.modules.browser.session import BrowserSessionHandle, is_browser_available

        if not is_browser_available():
            applications_service.mark_failed(
                db,
                application,
                "This application needs a browser but Chromium is not installed on this machine",
                final=True,
            )
            return

        with BrowserSessionHandle(application.user_id, source, db) as handle:
            ctx.page = handle.page
            self._steps(db, application, adapter, ctx, handle, config)

    # -- the steps ---------------------------------------------------------

    def _steps(self, db: Session, application: Application, adapter: Any, ctx: Any, handle: Any, config: Any) -> None:
        from app.modules.applications import service as applications_service

        opened = adapter.start_application(ctx)
        if opened.state != AutomationState.SUCCESS:
            self._interpret(db, application, opened, adapter, ctx, handle, config, step="start")
            return
        applications_service.record_event(
            db,
            application,
            ApplicationEventType.AUTOMATION,
            opened.message or "Opened the application form",
            actor=Actor.AUTOMATION,
            meta={"step": "start_application", "url": (opened.form_snapshot or {}).get("url")},
        )
        db.flush()

        filled = adapter.fill_application(ctx)
        self._interpret(db, application, filled, adapter, ctx, handle, config, step="fill")

    def _interpret(
        self,
        db: Session,
        application: Application,
        result: Any,
        adapter: Any,
        ctx: Any,
        handle: Any,
        config: Any,
        *,
        step: str,
    ) -> None:
        from app.modules.applications import service as applications_service

        if result.state == AutomationState.REQUIRES_USER:
            self._pause_for_user(db, application, result, handle)
            return

        if result.state != AutomationState.SUCCESS:
            applications_service.mark_failed(db, application, result.message or f"The {step} step failed")
            return

        if step != "fill":  # a successful non-fill step is just progress
            return

        snapshot = self._record_fill(db, application, result, handle)

        if self._auto_submit_allowed(application, config):
            self._submit(db, application, adapter, ctx, handle)
            return

        applications_service.await_review(
            db,
            application,
            "Your application is filled in and ready for review",
            form_snapshot=snapshot,
        )

    def _record_fill(self, db: Session, application: Application, result: Any, handle: Any) -> dict[str, Any]:
        """Persist the form snapshot and write the detected/filled event + audit trail.

        Runs whether the attempt goes on to submit or pauses: the reviewer must be able to
        see what the automation read off the page and what it typed, either way.
        """
        from app.modules.applications import service as applications_service

        snapshot = dict(result.form_snapshot or {})
        detected, filled_keys = snapshot_summary(snapshot)
        screenshot = result.screenshot_path
        if handle is not None and not screenshot:
            screenshot = handle.screenshot("after_fill", application.id) or None
        if screenshot:
            snapshot["screenshot_path"] = screenshot
        application.form_snapshot = snapshot

        applications_service.record_event(
            db,
            application,
            ApplicationEventType.FORM_FILLED,
            result.message or f"Filled {len(filled_keys)} fields",
            actor=Actor.AUTOMATION,
            meta={"detected": len(detected), "filled": len(filled_keys), "screenshot_path": screenshot},
        )
        audit(
            db,
            action="application.form_detected",
            message=f"Detected {len(detected)} fields on the application form",
            user_id=application.user_id,
            application_id=application.id,
            actor=Actor.AUTOMATION,
            meta={"url": snapshot.get("url"), "fields": detected},
        )
        audit(
            db,
            action="application.field_filled",
            message=f"Filled {len(filled_keys)} fields from your profile",
            user_id=application.user_id,
            application_id=application.id,
            actor=Actor.AUTOMATION,
            meta={"keys": filled_keys},
        )
        db.flush()
        return snapshot

    def _pause_for_user(self, db: Session, application: Application, result: Any, handle: Any) -> None:
        from app.modules.applications import service as applications_service

        snapshot = dict(result.form_snapshot or {})
        if snapshot.get("fields"):
            # The form was read (and partly filled) before we stopped — record that first so the
            # review screen and the audit trail show what the automation actually did.
            snapshot = self._record_fill(db, application, result, handle)
        if handle is not None and not snapshot.get("screenshot_path"):
            shot = handle.screenshot("paused", application.id)
            if shot:
                snapshot["screenshot_path"] = shot
        reason = result.pause_reason or PauseReason.UNKNOWN_QUESTION
        applications_service.pause(
            db,
            application,
            reason,
            result.message or "The application needs your input",
            form_snapshot=snapshot,
        )
        # Give the user something to answer in the UI for every unanswered required field.
        try:
            applications_service.record_snapshot_questions(db, application, snapshot)
        except Exception as exc:  # noqa: BLE001 - the pause itself must survive
            logger.warning("Could not record the paused form's questions for %s: %s", application.id, exc)
        db.flush()

    # -- submission --------------------------------------------------------

    @staticmethod
    def _auto_submit_allowed(application: Application, config: Any) -> bool:
        """Auto-submit is opt-in per application *and* per source, and never with gaps."""
        if not application.auto_submit or not getattr(config, "auto_submit_enabled", False):
            return False
        allowed = {str(s).upper() for s in (getattr(config, "auto_submit_sources", None) or [])}
        source = application.source
        if source is None or source.value.upper() not in allowed:
            return False
        for answer in application.answers or []:
            if answer.is_sensitive and answer.status == AnswerStatus.NEEDS_USER_INPUT:
                logger.info("Auto-submit refused for %s: a sensitive question is unanswered", application.id)
                return False
            if answer.required and answer.status == AnswerStatus.NEEDS_USER_INPUT:
                return False
        return True

    def _submit(self, db: Session, application: Application, adapter: Any, ctx: Any, handle: Any) -> None:
        from app.modules.applications import service as applications_service

        result = adapter.submit_application(ctx)
        if handle is not None:
            shot = handle.screenshot("after_submit", application.id)
            if shot:
                snapshot = dict(application.form_snapshot or {})
                snapshot["submit_screenshot_path"] = shot
                application.form_snapshot = snapshot

        if result.state == AutomationState.SUCCESS:
            applications_service.mark_submitted(
                db,
                application,
                external_application_id=result.external_application_id,
                confirmation_message=result.confirmation_message or result.message,
                via="AUTOMATION",
            )
            return
        if result.state == AutomationState.REQUIRES_USER:
            self._pause_for_user(db, application, result, handle)
            return
        applications_service.mark_failed(db, application, result.message or "Submission failed")


def run_application(application_id: uuid.UUID | str, db: Session | None = None) -> Application | None:
    """Convenience wrapper used by the automation pipeline."""
    return ApplicationRunner(application_id, db=db).run()


__all__ = ["ApplicationRunner", "RETRY_BACKOFF_SECONDS", "run_application", "snapshot_summary", "temporary_errors"]
