"""Common FastAPI dependencies: current user, RBAC guards, re-authentication.

The access token's ``role`` claim is the session's **active role** (the role the user
chose to act as when they hold several). Guards check that, never mere membership.

Sensitive actions (changing the password, signing sessions out) additionally depend on
:func:`require_recent_auth`: a fresh access token, or the password again.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from urllib.parse import unquote

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.actor import set_session_actor
from app.core.audit import audit
from app.core.database import get_db
from app.core.exceptions import ForbiddenError, RateLimitedError, UnauthorizedError
from app.core.rate_limit import client_ip, rate_limiter
from app.core.security import decode_access_token, verify_password
from app.models.enums import Actor, AuditLevel
from app.models.user import User, UserRole
from app.modules.ai.context import AiUserSlot, bind_request_user, request_ai_context

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

#: An access token younger than this may perform a sensitive action without a password.
REAUTH_MAX_AGE_SECONDS = 10 * 60
#: Header carrying the current password when the access token is older than that.
REAUTH_HEADER = "X-Reauth-Password"
#: Password confirmations allowed per user per window before ``429``.
REAUTH_MAX_ATTEMPTS = 5
REAUTH_WINDOW_SECONDS = 15 * 60
#: Same cap as the password policy: bcrypt work is not spent on an oversized header.
_REAUTH_MAX_LENGTH = 128 * 3


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    ai_slot: AiUserSlot = Depends(request_ai_context),
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Missing credentials")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token expired", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid token") from exc
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Invalid token subject") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    request.state.user_id = str(user.id)
    active_role = resolve_active_role(user, payload.get("role"))
    request.state.active_role = active_role
    request.state.access_token_exp = payload.get("exp")
    request.state.access_token_iat = payload.get("iat")
    # Non-persisted: ``User`` has no such column. It lives on this instance for the
    # length of the request so guards and ``UserRead`` can see which role is acting.
    user.active_role = active_role
    # Everything this request writes through this session is attributed to this user:
    # ``created_by`` / ``updated_by`` are stamped at flush time by ``app.core.actor``.
    # The session rather than a ContextVar because a ContextVar set here would be
    # discarded — Starlette runs sync dependencies in a copy of the request's context.
    set_session_actor(db, user.id)
    # Whose AI provider settings apply to this request (``app.modules.ai.context``).
    bind_request_user(ai_slot, user.id)
    return user


def held_role_names(user: User) -> list[str]:
    """Names of the roles ``user`` holds right now, sorted.

    Mirrors ``User.role``: an account with no ``user_roles`` row at all is a plain
    ``USER``, so it can still act as one.
    """
    names = sorted({role.name for role in user.roles})
    return names or [UserRole.USER.value]


def highest_role_name(user: User) -> str:
    role = user.role
    return role.value if hasattr(role, "value") else str(role)


def resolve_active_role(user: User, claimed: object) -> str:
    """The role this request acts as: the token's ``role`` claim, if still held.

    * No claim (a token minted before the active role existed): the highest role held,
      which is exactly what those tokens used to mean, so old sessions keep working.
    * A claim the user no longer holds (revoked mid-session): ``401 role_revoked``. The
      access token dies at once rather than at expiry, and refresh refuses it too.
    """
    if claimed is None or claimed == "":
        return highest_role_name(user)
    if not isinstance(claimed, str) or claimed not in held_role_names(user):
        raise UnauthorizedError("The role this session was using has been revoked", code="role_revoked")
    return claimed


def active_role_of(user: User) -> str:
    """The active role set by :func:`get_current_user`, else the highest role held."""
    return getattr(user, "active_role", None) or highest_role_name(user)


def require_roles(*roles: UserRole) -> Callable[..., User]:
    """Guard on the **active** role, not on membership: an ADMIN+USER account that
    signed in as USER is refused by an ADMIN guard until it switches role."""
    allowed = {role.value if hasattr(role, "value") else str(role) for role in roles}

    def _guard(user: User = Depends(get_current_user)) -> User:
        if active_role_of(user) not in allowed:
            raise ForbiddenError("Insufficient permissions")
        return user

    return _guard


require_admin = require_roles(UserRole.ADMIN)


def require_module(code: str) -> Callable[..., None]:
    """Guard a whole router on a workspace module (``app.modules.workspace``).

    Mounted once per router in ``app.main`` (``dependencies=[Depends(require_module("resume"))]``).
    A module switched off platform-wide, switched off for this user by an admin, above the
    session's active role, or not available yet answers ``403 module_disabled`` with the
    module's name in the message and ``details.module`` / ``details.reason``. Authentication
    still comes first: no token is ``401`` exactly as before.
    """

    def _guard(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
        from app.modules.workspace.service import ensure_module_access  # lazy: avoids an import cycle

        ensure_module_access(db, user, code)

    _guard.__name__ = f"require_module_{code}"
    return _guard


def _token_is_fresh(issued_at: object) -> bool:
    if isinstance(issued_at, bool) or not isinstance(issued_at, (int, float)):
        return False  # a token without ``iat`` is never fresh
    age = time.time() - float(issued_at)
    return -60 <= age < REAUTH_MAX_AGE_SECONDS  # a minute of clock skew either way


def _reauth_password_matches(supplied: str, hashed: str) -> bool:
    """Compare the header value with the password hash.

    Header values are Latin-1 and stripped of surrounding whitespace, so the web client
    percent-encodes (UTF-8) a password that is not plain printable ASCII. The literal
    value is tried first, so an ASCII password containing ``%`` works either way.
    """
    if verify_password(supplied, hashed):
        return True
    if "%" not in supplied:
        return False
    try:
        decoded = unquote(supplied, encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    return decoded != supplied and verify_password(decoded, hashed)


def require_recent_auth(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Gate for sensitive actions: recent sign-in, or the password again.

    Passes when the access token was issued less than :data:`REAUTH_MAX_AGE_SECONDS` ago
    (its ``iat`` claim), or when the request carries :data:`REAUTH_HEADER` with the
    current password. Otherwise ``401 reauth_required`` (``details.reason`` is
    ``stale_token`` or ``invalid_password``). Password attempts are rate limited per user
    (``429`` after :data:`REAUTH_MAX_ATTEMPTS` in :data:`REAUTH_WINDOW_SECONDS`) and every
    wrong one is audited as ``auth.reauth_failed``.

    The client must not answer ``reauth_required`` by refreshing the access token: it
    asks the user for the password instead (see ``frontend/src/lib/api.ts``).
    """
    if _token_is_fresh(getattr(request.state, "access_token_iat", None)):
        return user

    supplied = request.headers.get(REAUTH_HEADER)
    if not supplied:
        raise UnauthorizedError(
            "Confirm your password to continue.", code="reauth_required", details={"reason": "stale_token"}
        )

    allowed, _ = rate_limiter.check(f"auth:reauth:{user.id}", REAUTH_MAX_ATTEMPTS, REAUTH_WINDOW_SECONDS)
    if not allowed:
        raise RateLimitedError("Too many password confirmations. Try again in a few minutes.")

    if len(supplied) > _REAUTH_MAX_LENGTH or not _reauth_password_matches(supplied, user.hashed_password):
        ip = client_ip(request)
        audit(
            db,
            action="auth.reauth_failed",
            message="Wrong password while confirming a sensitive action",
            user_id=user.id,
            actor=Actor.USER,
            level=AuditLevel.WARN,
            meta={"path": request.url.path},
            ip_address=ip if ip != "unknown" else None,
        )
        try:  # ``get_db`` rolls back on the error below; the evidence must survive it
            db.commit()
        except Exception:  # pragma: no cover - defensive
            db.rollback()
            logger.exception("Could not persist the reauth failure audit record")
        raise UnauthorizedError(
            "That password is not correct.", code="reauth_required", details={"reason": "invalid_password"}
        )
    return user
