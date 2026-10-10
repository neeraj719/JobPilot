"""HTTP access to the public ATS job board APIs, with a small per-process cache.

Every board adapter goes through :func:`fetch_json`, so the politeness rules live in one
place:

* a descriptive ``User-Agent`` (:data:`USER_AGENT`) so the vendor can tell who is calling;
* a 15 second timeout - one slow board must not stall a discovery run;
* an in-memory cache keyed by URL with a 30 minute TTL, so several users' runs (or a
  manual "discover" right after the daily run) do not fetch the same board again.

Only ``GET`` requests to the four vendors' documented, unauthenticated endpoints are
ever made from here; nothing logs in, nothing posts.

Tests swap the network out with :func:`set_transport` (an ``httpx.MockTransport``) and
reset the cache with :func:`clear_cache`. Board auto-detection (``companies.board_detect``)
runs its probes inside :func:`request_timeout` to use a shorter timeout than discovery.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import httpx

from app import __version__

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15.0
CACHE_TTL_SECONDS = 30 * 60
#: Upper bound on cached responses. A large board is a few MB of JSON; this keeps the
#: worst case bounded however many companies are configured.
CACHE_MAX_ENTRIES = 128
USER_AGENT = f"JobPilot/{__version__} (+https://github.com/jobpilot-ai/jobpilot)"


class BoardFetchError(Exception):
    """A board could not be read (network error, 5xx, timeout)."""


class BoardNotFound(BoardFetchError):
    """The vendor answered 404: there is no public board under that token."""


class BoardPayloadError(BoardFetchError):
    """The vendor answered, but not with the JSON shape its API documents."""


_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_lock = threading.Lock()
_transport: httpx.BaseTransport | None = None
#: A caller-scoped timeout that replaces :data:`TIMEOUT_SECONDS` (see :func:`request_timeout`).
_timeout_override: ContextVar[float | None] = ContextVar("board_request_timeout", default=None)


def set_transport(transport: httpx.BaseTransport | None) -> None:
    """Route every board request through ``transport`` (tests); ``None`` restores the network."""
    global _transport
    _transport = transport


@contextmanager
def request_timeout(seconds: float) -> Iterator[None]:
    """Use ``seconds`` instead of :data:`TIMEOUT_SECONDS` for board requests made inside the block."""
    token = _timeout_override.set(float(seconds))
    try:
        yield
    finally:
        _timeout_override.reset(token)


def current_timeout() -> float:
    return _timeout_override.get() or TIMEOUT_SECONDS


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _cached(url: str, now: float) -> tuple[bool, Any]:
    with _lock:
        entry = _cache.get(url)
        if entry is None:
            return False, None
        stored_at, payload = entry
        if now - stored_at > CACHE_TTL_SECONDS:
            del _cache[url]
            return False, None
        _cache.move_to_end(url)
        return True, payload


def _store(url: str, payload: Any, now: float) -> None:
    with _lock:
        _cache[url] = (now, payload)
        _cache.move_to_end(url)
        while len(_cache) > CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def cached_json(url: str) -> Any | None:
    """The cached payload for ``url`` if there is a fresh one; never makes a request."""
    hit, payload = _cached(url, time.monotonic())
    return payload if hit else None


def fetch_json(url: str, *, use_cache: bool = True) -> Any:
    """``GET url`` and return the decoded JSON body.

    Raises :class:`BoardNotFound` on 404, :class:`BoardPayloadError` on a body that is
    not JSON, and :class:`BoardFetchError` on anything else that went wrong. Successful
    responses are cached for :data:`CACHE_TTL_SECONDS`.
    """
    now = time.monotonic()
    if use_cache:
        hit, payload = _cached(url, now)
        if hit:
            logger.debug("Board cache hit: %s", url)
            return payload

    try:
        with httpx.Client(
            timeout=current_timeout(),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
            transport=_transport,
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        raise BoardFetchError(f"Could not reach {url}: {type(exc).__name__}: {exc}") from exc

    if response.status_code == 404:
        raise BoardNotFound(f"No public board at {url} (HTTP 404)")
    if response.status_code >= 400:
        raise BoardFetchError(f"{url} answered HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise BoardPayloadError(f"{url} did not return JSON") from exc

    _store(url, payload, time.monotonic())
    return payload
