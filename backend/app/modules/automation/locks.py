"""Per-user automation lock (contract §14).

Only one automation pipeline may run for a user at a time — the API and the worker
both go through this module before starting one. The primary implementation is a
Redis ``SET NX EX`` (so several processes / containers agree); when Redis is not
reachable the module falls back to a process-local dictionary guarded by a
``threading.Lock`` so a single-process deployment (and the test-suite) still get
mutual exclusion.

Usage::

    from app.modules.automation import locks

    with locks.user_lock(user_id):           # raises ConflictError when already held
        run_pipeline(...)
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from app.core.config import settings
from app.core.exceptions import ConflictError

logger = logging.getLogger(__name__)

#: Key template required by the contract.
LOCK_KEY_TEMPLATE = "automation:lock:{user_id}"
#: The lock auto-expires so a crashed worker can never block a user forever.
DEFAULT_TTL_SECONDS = 3600

_memory_locks: dict[str, tuple[str, float]] = {}
_memory_guard = threading.Lock()

_redis_client: Any | None = None
_redis_tried = False
_redis_guard = threading.Lock()


def lock_key(user_id: uuid.UUID | str) -> str:
    return LOCK_KEY_TEMPLATE.format(user_id=user_id)


# --------------------------------------------------------------------------- redis


def _get_redis() -> Any | None:
    """A connected Redis client, or ``None`` when Redis is unavailable.

    The probe happens once per process; afterwards the in-memory fallback is used
    without further connection attempts (so tests never wait on a socket timeout).
    """
    global _redis_client, _redis_tried
    with _redis_guard:
        if _redis_tried:
            return _redis_client
        _redis_tried = True
        if settings.ENV == "test":
            logger.debug("Redis lock backend disabled in tests; using the in-memory fallback")
            _redis_client = None
            return None
        try:
            import redis  # imported lazily: the fallback must work without the package

            client = redis.Redis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
                decode_responses=True,
            )
            client.ping()
        except Exception as exc:  # pragma: no cover - depends on the local environment
            logger.warning("Redis unavailable for automation locks (%s); using in-memory fallback", exc)
            _redis_client = None
        else:
            logger.info("Automation locks use Redis at %s", settings.REDIS_URL)
            _redis_client = client
        return _redis_client


def reset_backend_cache() -> None:
    """Testing helper — forget the cached Redis probe."""
    global _redis_client, _redis_tried
    with _redis_guard:
        _redis_client = None
        _redis_tried = False


# --------------------------------------------------------------------------- memory fallback


def _memory_acquire(key: str, token: str, ttl: int) -> bool:
    now = time.time()
    with _memory_guard:
        held = _memory_locks.get(key)
        if held is not None and held[1] > now:
            return False
        _memory_locks[key] = (token, now + ttl)
        return True


def _memory_release(key: str, token: str | None) -> bool:
    with _memory_guard:
        held = _memory_locks.get(key)
        if held is None:
            return False
        if token is not None and held[0] != token:
            return False
        _memory_locks.pop(key, None)
        return True


def _memory_held(key: str) -> bool:
    now = time.time()
    with _memory_guard:
        held = _memory_locks.get(key)
        if held is None:
            return False
        if held[1] <= now:
            _memory_locks.pop(key, None)
            return False
        return True


# --------------------------------------------------------------------------- public API


def acquire_lock(user_id: uuid.UUID | str, ttl: int = DEFAULT_TTL_SECONDS) -> str | None:
    """Try to take the user's automation lock.

    Returns the lock token when acquired (pass it back to :func:`release_lock`) and
    ``None`` when somebody else already holds it.
    """
    key = lock_key(user_id)
    token = secrets.token_hex(16)
    client = _get_redis()
    if client is not None:
        try:
            if client.set(key, token, nx=True, ex=ttl):
                logger.debug("Acquired redis automation lock %s", key)
                return token
            return None
        except Exception as exc:  # pragma: no cover - redis died mid-flight
            logger.warning("Redis lock failed (%s); falling back to the in-memory lock", exc)
    if _memory_acquire(key, token, ttl):
        logger.debug("Acquired in-memory automation lock %s", key)
        return token
    return None


def release_lock(user_id: uuid.UUID | str, token: str | None = None) -> bool:
    """Release the lock. ``token=None`` force-releases (used by cancel)."""
    key = lock_key(user_id)
    client = _get_redis()
    released = False
    if client is not None:
        try:
            if token is None:
                released = bool(client.delete(key))
            else:
                current = client.get(key)
                if current == token:
                    released = bool(client.delete(key))
        except Exception as exc:  # pragma: no cover - redis died mid-flight
            logger.warning("Redis unlock failed: %s", exc)
    released = _memory_release(key, token) or released
    if released:
        logger.debug("Released automation lock %s", key)
    return released


def is_locked(user_id: uuid.UUID | str) -> bool:
    """True when an automation run currently holds this user's lock."""
    key = lock_key(user_id)
    client = _get_redis()
    if client is not None:
        try:
            return bool(client.exists(key))
        except Exception as exc:  # pragma: no cover - redis died mid-flight
            logger.warning("Redis lock probe failed: %s", exc)
    return _memory_held(key)


@contextmanager
def user_lock(user_id: uuid.UUID | str, ttl: int = DEFAULT_TTL_SECONDS) -> Generator[str, None, None]:
    """Context manager raising :class:`ConflictError` when the lock is already held."""
    token = acquire_lock(user_id, ttl)
    if token is None:
        raise ConflictError("An automation run is already in progress for this account", code="automation_running")
    try:
        yield token
    finally:
        release_lock(user_id, token)


def reset_locks() -> None:
    """Testing helper — drop every in-memory lock."""
    with _memory_guard:
        _memory_locks.clear()


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "LOCK_KEY_TEMPLATE",
    "acquire_lock",
    "is_locked",
    "lock_key",
    "release_lock",
    "reset_backend_cache",
    "reset_locks",
    "user_lock",
]
