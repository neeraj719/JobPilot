"""Fixed-window rate limiting with Redis backend and in-memory fallback.

Applied as middleware for the whole API (per client IP / user) and available as a
dependency for stricter limits on auth endpoints.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import RateLimitedError

logger = logging.getLogger(__name__)


class _MemoryBackend:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            bucket = [t for t in self._hits[key] if t > now - window]
            bucket.append(now)
            self._hits[key] = bucket
            remaining = max(0, limit - len(bucket))
            return len(bucket) <= limit, remaining


class _RedisBackend:
    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)

    def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        pipe = self._client.pipeline()
        pipe.incr(key)
        # NX: the window starts at the first hit. Re-arming it on every hit meant a client
        # that never paused for a full window was never let back in.
        pipe.expire(key, window, nx=True)
        count, _ = pipe.execute()
        return int(count) <= limit, max(0, limit - int(count))


class RateLimiter:
    def __init__(self) -> None:
        self._backend = _MemoryBackend()
        self._tried_redis = False

    def _ensure_backend(self) -> None:
        if self._tried_redis or settings.ENV == "test":
            return
        self._tried_redis = True
        try:
            backend = _RedisBackend(settings.REDIS_URL)
            backend._client.ping()
            self._backend = backend  # type: ignore[assignment]
            logger.info("Rate limiter using Redis backend")
        except Exception as exc:  # pragma: no cover - depends on infra
            logger.warning("Redis unavailable for rate limiting (%s); using in-memory backend", exc)

    def check(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
        self._ensure_backend()
        try:
            return self._backend.hit(key, limit, window)
        except Exception as exc:  # pragma: no cover
            logger.warning("Rate limit backend error: %s", exc)
            return True, limit


rate_limiter = RateLimiter()


def client_ip(request: Request) -> str:
    """The client address used for rate limiting and audit records.

    Forwarding headers are attacker-controlled unless a reverse proxy rewrites them,
    so they are ignored unless ``TRUST_PROXY_HEADERS`` is on — otherwise a client
    could pick a fresh bucket per request and walk straight past the login limit.

    When they *are* trusted (single-hop proxy, e.g. the bundled Nginx):

    * ``X-Real-IP`` is preferred: the proxy sets it from the real peer and a client
      cannot append to it;
    * for ``X-Forwarded-For`` the **right-most** entry is used. Nginx appends the peer
      address to whatever the client sent, so the left-most entry is exactly the part
      an attacker controls.
    """
    if settings.TRUST_PROXY_HEADERS:
        real_ip = (request.headers.get("x-real-ip") or "").strip()
        if real_ip:
            return real_ip[:64]
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            parts = [part.strip() for part in forwarded.split(",") if part.strip()]
            if parts:
                return parts[-1][:64]
    return (request.client.host if request.client else "unknown")[:64]


def _client_key(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"rl:user:{user_id}"
    return f"rl:ip:{client_ip(request)}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN201
        if request.url.path.startswith(("/demo-ats", "/health", "/docs", "/openapi.json", "/redoc")):
            return await call_next(request)
        allowed, remaining = rate_limiter.check(_client_key(request), settings.RATE_LIMIT_PER_MINUTE)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Too many requests, slow down."}},
                headers={"Retry-After": "60"},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


def auth_rate_limit(request: Request) -> None:
    """Stricter dependency for login/register/refresh."""
    allowed, _ = rate_limiter.check(f"auth:{_client_key(request)}", settings.AUTH_RATE_LIMIT_PER_MINUTE)
    if not allowed:
        raise RateLimitedError("Too many authentication attempts. Try again in a minute.")
