"""Playwright browser sessions (CONTRACTS.md section 12).

Threading contract -- IMPORTANT
-------------------------------
The Playwright **sync** API is bound to the thread that started it: a ``Playwright``
instance, its ``Browser``, ``BrowserContext`` and ``Page`` objects may only be used from
the thread that created them, and they may never be used from inside a running asyncio
event loop. Therefore:

* ``ApplicationRunner`` (and any other caller) MUST create the
  :class:`BrowserSessionHandle` **inside the worker thread that will drive the page** --
  do not build a handle in one thread and hand the page to another.
* FastAPI endpoints that touch Playwright must be declared ``def`` (not ``async def``)
  so Starlette runs them in a worker thread.
* Each handle therefore starts its own ``sync_playwright()`` instance; that is cheap
  compared to the browser launch itself and keeps threads fully isolated.

Every (user, source) pair gets an **isolated** ``BrowserContext``. Cookies / localStorage
are persisted Fernet-encrypted on the ``BrowserSession`` row and restored on the next
open, so one user's logged-in state is never shared with another user.

No stealth plugins, no bot-detection evasion, no CAPTCHA/OTP solving: when the detector
finds a blocker the automation pauses and asks the human (see ``detector.py``).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_str, encrypt_str
from app.models.automation import BrowserSession
from app.models.base import utcnow
from app.models.enums import BrowserSessionStatus, JobSourceType

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 JobPilotAI/0.1"
)
VIEWPORT = {"width": 1366, "height": 768}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

_availability_lock = threading.Lock()
_availability: bool | None = None


# --------------------------------------------------------------------------- availability


def is_browser_available(force: bool = False) -> bool:
    """Return True when a Chromium build can actually be launched.

    The answer is cached for the life of the process (launching Chromium costs ~1s);
    pass ``force=True`` to re-probe. Callers and tests use this to degrade gracefully
    when ``playwright install chromium`` has not been run.
    """
    global _availability
    with _availability_lock:
        if _availability is not None and not force:
            return _availability
        available = False
        try:
            from playwright.sync_api import sync_playwright

            pw = sync_playwright().start()
            try:
                browser = pw.chromium.launch(headless=True)
                browser.close()
                available = True
            finally:
                pw.stop()
        except Exception as exc:  # pragma: no cover - depends on the local install
            logger.warning("Chromium is not available for automation: %s", exc)
            available = False
        _availability = available
        return available


def reset_browser_availability_cache() -> None:
    """Testing helper - forget the cached probe result."""
    global _availability
    with _availability_lock:
        _availability = None


# --------------------------------------------------------------------------- screenshots


def screenshot_path_for(name: str, application_id: uuid.UUID | str | None = None) -> Path:
    """``UPLOAD_DIR/screenshots/<application_id>/<name>.png`` (directory created)."""
    safe_name = _SAFE_NAME.sub("-", str(name)).strip("-.") or "screenshot"
    folder = Path(settings.UPLOAD_DIR) / "screenshots" / (str(application_id) if application_id else "misc")
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{safe_name}.png"


def save_screenshot(page: Any, name: str, application_id: uuid.UUID | str | None = None) -> str:
    """Capture ``page`` to the screenshots folder. Returns "" if it could not be saved.

    Usable by callers that only hold a Playwright ``Page`` (adapters, the runner) rather
    than a :class:`BrowserSessionHandle`.
    """
    path = screenshot_path_for(name, application_id)
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Screenshot %s failed: %s", path, exc)
        return ""
    logger.debug("Screenshot saved to %s", path)
    return str(path)


# --------------------------------------------------------------------------- session handle


class BrowserSessionHandle:
    """Context manager owning one isolated Chromium context for one (user, source).

    Usage, from the thread that will drive the page::

        with BrowserSessionHandle(user_id, JobSourceType.DEMO_ATS, db) as handle:
            handle.page.goto(url)
            handle.screenshot("after_fill", application_id)
    """

    def __init__(
        self,
        user_id: uuid.UUID | str,
        source: JobSourceType,
        db: Session | None = None,
        *,
        headless: bool | None = None,
        persist_state: bool = True,
        commit_on_exit: bool = False,
    ) -> None:
        self.user_id = uuid.UUID(str(user_id))
        self.source = source
        self.db = db
        self.headless = settings.PLAYWRIGHT_HEADLESS if headless is None else headless
        self.persist_state = persist_state and db is not None
        self.commit_on_exit = commit_on_exit
        self.thread_id = threading.get_ident()
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._row: BrowserSession | None = None

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> BrowserSessionHandle:
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        self.close()
        return False

    def start(self) -> BrowserSessionHandle:
        from playwright.sync_api import sync_playwright

        self.thread_id = threading.get_ident()
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        storage_state = self._load_storage_state()
        self._context = self._browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            viewport=VIEWPORT,
            accept_downloads=False,
            storage_state=storage_state,
        )
        self._context.set_default_timeout(settings.BROWSER_TIMEOUT_MS)
        self._context.set_default_navigation_timeout(settings.BROWSER_TIMEOUT_MS)
        logger.info(
            "Browser context opened (user=%s source=%s headless=%s restored_state=%s)",
            self.user_id,
            self.source,
            self.headless,
            storage_state is not None,
        )
        return self

    def close(self) -> None:
        try:
            self._save_storage_state()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not persist browser storage state: %s", exc)
        for closer, label in (
            (getattr(self._page, "close", None), "page"),
            (getattr(self._context, "close", None), "context"),
            (getattr(self._browser, "close", None), "browser"),
            (getattr(self._pw, "stop", None), "playwright"),
        ):
            if closer is None:
                continue
            try:
                closer()
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Error closing %s: %s", label, exc)
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None
        logger.info("Browser context closed (user=%s source=%s)", self.user_id, self.source)

    # -- accessors ---------------------------------------------------------

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser session is not started -- use it as a context manager")
        return self._context

    @property
    def page(self) -> Page:
        """The working page (created on first access)."""
        if self._page is None:
            self._page = self.context.new_page()
        return self._page

    def new_page(self) -> Page:
        return self.context.new_page()

    # -- helpers -----------------------------------------------------------

    def screenshot(self, name: str, application_id: uuid.UUID | str | None = None) -> str:
        """Save a PNG under ``UPLOAD_DIR/screenshots/<application_id>/<name>.png``."""
        return save_screenshot(self.page, name, application_id)

    def storage_state_dict(self) -> dict[str, Any]:
        return dict(self.context.storage_state())

    # -- persistence -------------------------------------------------------

    def _session_row(self) -> BrowserSession | None:
        if self.db is None:
            return None
        if self._row is None:
            self._row = self.db.scalars(
                select(BrowserSession).where(
                    BrowserSession.user_id == self.user_id,
                    BrowserSession.source == self.source,
                )
            ).first()
        return self._row

    def _load_storage_state(self) -> dict[str, Any] | None:
        if not self.persist_state:
            return None
        row = self._session_row()
        if row is None or not row.encrypted_storage_state or row.status != BrowserSessionStatus.ACTIVE:
            return None
        try:
            state = json.loads(decrypt_str(row.encrypted_storage_state))
        except Exception as exc:
            logger.warning("Stored browser state for %s/%s is unreadable (%s); starting fresh", self.user_id, self.source, exc)
            return None
        return state if isinstance(state, dict) else None

    def _save_storage_state(self) -> None:
        if not self.persist_state or self._context is None or self.db is None:
            return
        state = json.dumps(self._context.storage_state())
        row = self._session_row()
        now = utcnow()
        if row is None:
            row = BrowserSession(user_id=self.user_id, source=self.source, created_at=now, updated_at=now)
            self.db.add(row)
            self._row = row
        row.encrypted_storage_state = encrypt_str(state)
        row.status = BrowserSessionStatus.ACTIVE
        row.user_agent = DEFAULT_USER_AGENT
        row.last_used_at = now
        self.db.flush()
        if self.commit_on_exit:
            self.db.commit()


# --------------------------------------------------------------------------- manager


class BrowserManager:
    """Factory for per-(user, source) contexts.

    Deliberately thin: because the sync API cannot cross threads, the manager does not
    cache Playwright instances -- each :class:`BrowserSessionHandle` owns its own (see
    the module docstring).
    """

    @staticmethod
    def available() -> bool:
        return is_browser_available()

    @staticmethod
    def open_context(
        user_id: uuid.UUID | str,
        source: JobSourceType,
        db: Session | None = None,
        **kwargs: Any,
    ) -> BrowserSessionHandle:
        """Return a *started* handle. The caller closes it (or uses ``with``)."""
        return BrowserSessionHandle(user_id, source, db, **kwargs).start()


browser_manager = BrowserManager()
