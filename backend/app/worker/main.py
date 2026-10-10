"""Worker entry point: ``python -m app.worker.main`` (the docker ``worker`` service).

Runs the APScheduler jobs in the foreground and shuts them down cleanly on
SIGTERM / SIGINT so ``docker stop`` never leaves a half-finished automation run.
"""
from __future__ import annotations

import logging
import signal
import threading
from types import FrameType

from app.core.config import settings
from app.core.logging import configure_logging
from app.worker.scheduler import build_scheduler

logger = logging.getLogger(__name__)

_stop = threading.Event()


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    logger.info("Received signal %s — shutting the worker down", signum)
    _stop.set()


def install_signal_handlers() -> None:
    """Best-effort signal wiring (SIGTERM does not exist on every platform)."""
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):  # pragma: no cover - not the main thread / unsupported
            logger.debug("Could not install a handler for %s", name)


def main() -> int:
    configure_logging()
    install_signal_handlers()
    scheduler = build_scheduler()
    scheduler.start()
    logger.info(
        "%s worker started (env=%s, jobs=%s)",
        settings.APP_NAME,
        settings.ENV,
        ", ".join(job.id for job in scheduler.get_jobs()),
    )
    try:
        _stop.wait()
    except KeyboardInterrupt:  # pragma: no cover - interactive runs
        logger.info("Keyboard interrupt — shutting down")
    finally:
        scheduler.shutdown(wait=True)
        logger.info("Worker stopped")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
