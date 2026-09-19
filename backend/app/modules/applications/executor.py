"""Background execution of one application run (CONTRACTS.md sections 11-12).

The Playwright sync API is bound to the thread that started it, so the runner is always
built **inside** the thread that will drive the page - never handed a page from another
thread. A module-level registry makes a second concurrent run of the same application
impossible, which matters because a duplicate run would mean a duplicate submission.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import session_scope
from app.core.exceptions import ConflictError

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_running: dict[str, threading.Thread] = {}


def _key(application_id: uuid.UUID | str) -> str:
    return str(application_id)


def is_running(application_id: uuid.UUID | str) -> bool:
    """True while a run for this application is in flight in this process."""
    key = _key(application_id)
    with _lock:
        thread = _running.get(key)
        if thread is None:
            return False
        if thread is threading.current_thread():
            return True
        if not thread.is_alive():
            _running.pop(key, None)
            return False
        return True


def running_ids() -> list[str]:
    with _lock:
        return [key for key in list(_running) if is_running(key)]


def _claim(application_id: uuid.UUID | str, thread: threading.Thread) -> None:
    key = _key(application_id)
    with _lock:
        if is_running(key):
            raise ConflictError("This application is already being processed", code="already_running")
        _running[key] = thread


def _release(application_id: uuid.UUID | str) -> None:
    with _lock:
        _running.pop(_key(application_id), None)


def _execute(application_id: uuid.UUID, db: Session | None = None) -> Any:
    from app.modules.browser.runner import ApplicationRunner

    if db is not None:
        return ApplicationRunner(application_id, db=db).run()
    with session_scope() as session:
        return ApplicationRunner(application_id, db=session).run()


def _thread_target(application_id: uuid.UUID) -> None:
    try:
        _execute(application_id)
    except Exception:  # noqa: BLE001 - a background thread must never raise into the void
        logger.exception("Application run %s crashed", application_id)
    finally:
        _release(application_id)


def run_in_background(application_id: uuid.UUID) -> threading.Thread:
    """Start the run in a daemon thread with its own DB session."""
    thread = threading.Thread(
        target=_thread_target,
        args=(application_id,),
        name=f"jobpilot-apply-{_key(application_id)[:8]}",
        daemon=True,
    )
    _claim(application_id, thread)
    thread.start()
    logger.info("Application %s is running in the background", application_id)
    return thread


def run_now(application_id: uuid.UUID, db: Session | None = None) -> Any:
    """Run synchronously in the calling thread (tests, and the automation pipeline)."""
    _claim(application_id, threading.current_thread())
    try:
        return _execute(application_id, db)
    finally:
        _release(application_id)


def wait_for(application_id: uuid.UUID, timeout: float = 30.0) -> bool:
    """Block until the background run finishes. Returns False on timeout."""
    with _lock:
        thread = _running.get(_key(application_id))
    if thread is None or thread is threading.current_thread():
        return True
    thread.join(timeout=timeout)
    finished = not thread.is_alive()
    if finished:
        _release(application_id)
    return finished


def reset() -> None:
    """Testing helper - forget every tracked run."""
    with _lock:
        _running.clear()


__all__ = ["is_running", "reset", "run_in_background", "run_now", "running_ids", "wait_for"]
