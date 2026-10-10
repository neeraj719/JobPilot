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
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session

from app.core.actor import actor_context
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
        # ``Thread.ident`` is None until ``start()`` runs. ``run_in_background`` claims the
        # slot *before* starting the thread, so testing ``is_alive()`` alone reported "not
        # running" and dropped the claim - which is exactly the duplicate run (and
        # duplicate submission) this registry exists to prevent.
        if thread.ident is not None and not thread.is_alive():
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


def _thread_target(application_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> None:
    # A new thread starts with an empty context, so the acting user has to be published
    # again inside it or every row the run writes would be filed as a system write.
    try:
        with actor_context(actor_id):
            _execute(application_id)
    except Exception:  # noqa: BLE001 - a background thread must never raise into the void
        logger.exception("Application run %s crashed", application_id)
    finally:
        _release(application_id)


def run_in_background(application_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> threading.Thread:
    """Start the run in a daemon thread with its own DB session.

    ``actor_id`` is the user the run acts for — the application's owner. It is carried
    across the thread boundary by hand because a ``ContextVar`` is not inherited by a new
    thread; without it the rows the run writes would have no ``created_by``.
    """
    thread = threading.Thread(
        target=_thread_target,
        args=(application_id, actor_id),
        name=f"jobpilot-apply-{_key(application_id)[:8]}",
        daemon=True,
    )
    _claim(application_id, thread)
    try:
        thread.start()
    except BaseException:  # a thread that never started must not hold the slot
        _release(application_id)
        raise
    logger.info("Application %s is running in the background", application_id)
    return thread


@contextmanager
def single_flight(application_id: uuid.UUID) -> Iterator[None]:
    """Hold this application's run slot for the duration of the block.

    ``is_running()`` on its own is only a *test*: two threads can both read "not running"
    and then both drive the adapter. ``_claim`` decides under the registry lock, so
    exactly one of them proceeds and every other caller gets ``ConflictError``.

    Deliberately not re-entrant - a claim is never nested in this codebase (approval and
    the runner are separate entry points), and allowing it would weaken the one guarantee
    the registry exists to give: at most one thing drives an application at a time.
    """
    _claim(application_id, threading.current_thread())
    try:
        yield
    finally:
        _release(application_id)


def run_now(application_id: uuid.UUID, db: Session | None = None) -> Any:
    """Run synchronously in the calling thread (tests, and the automation pipeline)."""
    with single_flight(application_id):
        return _execute(application_id, db)


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


__all__ = [
    "is_running",
    "reset",
    "run_in_background",
    "run_now",
    "running_ids",
    "single_flight",
    "wait_for",
]
