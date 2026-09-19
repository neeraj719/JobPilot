"""Authentication service: users, passwords, access + rotating refresh tokens (contract §2).

Security notes:

* Refresh tokens are opaque random strings; only their SHA-256 hash is stored.
* Every refresh rotates the token: the presented token is revoked and linked to its
  successor through ``replaced_by_hash``.
* Presenting an already revoked token is treated as theft: **every** token of that user
  is revoked and ``auth.refresh_reuse_detected`` is audited at ERROR level.
* Login failures never reveal whether the email exists ("Invalid email or password").
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError, ValidationFailed
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    refresh_token_expiry,
    verify_password,
)
from app.models.automation import AutomationConfig
from app.models.base import utcnow
from app.models.enums import Actor, AuditLevel, UserRole
from app.models.profile import JobPreference, UserProfile
from app.models.user import RefreshToken, User
from app.modules.auth.schemas import PASSWORD_POLICY, check_password_policy

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Invalid email or password"
REFRESH_COOKIE_NAME = "refresh_token"


# --------------------------------------------------------------------------- helpers


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_password(password: str) -> None:
    """Service-level password policy check (raises :class:`ValidationFailed`)."""
    try:
        check_password_policy(password)
    except ValueError as exc:
        raise ValidationFailed(str(exc) or PASSWORD_POLICY, code="weak_password") from exc


def access_token_ttl_seconds() -> int:
    return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def refresh_cookie_max_age() -> int:
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def refresh_cookie_path() -> str:
    return f"{settings.API_PREFIX}/auth"


def _persist(db: Session) -> None:
    """Commit work that must survive an error response (audit trail, revocations).

    ``get_db`` rolls the session back when the endpoint raises, so security evidence
    has to be committed before the exception leaves the service.
    """
    try:
        db.commit()
    except Exception:  # pragma: no cover - defensive
        db.rollback()
        logger.exception("Could not persist security audit record")


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == normalize_email(email))).first()


# --------------------------------------------------------------------------- users


def create_user(db: Session, email: str, password: str, full_name: str, *, role: UserRole = UserRole.USER) -> User:
    """Create a user plus the empty profile / preferences / automation config rows.

    Public helper - the seed script and other modules use it instead of the HTTP endpoint.
    """
    email = normalize_email(email)
    full_name = " ".join((full_name or "").split())
    if not full_name:
        raise ValidationFailed("full_name is required", code="invalid_full_name")
    validate_password(password)
    if get_user_by_email(db, email) is not None:
        raise ConflictError("An account with this email already exists", code="email_taken")

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    db.flush()

    db.add(UserProfile(user_id=user.id, full_name=full_name or None, email=email))
    db.add(
        JobPreference(
            user_id=user.id,
            currency="INR",
            min_match_score=settings.DEFAULT_MIN_MATCH_SCORE,
            only_posted_within_hours=24,
        )
    )
    db.add(
        AutomationConfig(
            user_id=user.id,
            daily_application_limit=settings.DEFAULT_DAILY_APPLICATION_LIMIT,
            min_match_score=settings.DEFAULT_MIN_MATCH_SCORE,
            retry_limit=settings.AUTOMATION_RETRY_LIMIT,
            delay_between_actions_seconds=settings.AUTOMATION_DELAY_SECONDS,
        )
    )
    db.flush()

    audit(db, action="auth.register", message=f"Account created for {email}", user_id=user.id, actor=Actor.USER)
    logger.info("Registered user %s", email)
    return user


def authenticate(db: Session, email: str, password: str, *, ip_address: str | None = None) -> User:
    """Return the user for valid credentials, else raise a *generic* 401."""
    email = normalize_email(email)
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        audit(
            db,
            action="auth.login_failed",
            message=f"Failed login attempt for {email}",
            user_id=user.id if user else None,
            actor=Actor.USER,
            level=AuditLevel.WARN,
            meta={"email": email, "reason": "unknown_email" if user is None else "bad_password"},
            ip_address=ip_address,
        )
        _persist(db)
        raise UnauthorizedError(INVALID_CREDENTIALS, code="invalid_credentials")
    if not user.is_active:
        audit(
            db,
            action="auth.login_failed",
            message=f"Disabled account login attempt for {email}",
            user_id=user.id,
            actor=Actor.USER,
            level=AuditLevel.WARN,
            meta={"email": email, "reason": "inactive"},
            ip_address=ip_address,
        )
        _persist(db)
        raise UnauthorizedError("This account is disabled", code="account_disabled")

    user.last_login_at = utcnow()
    audit(db, action="auth.login", message=f"Login for {email}", user_id=user.id, actor=Actor.USER, ip_address=ip_address)
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> User:
    if not verify_password(current_password, user.hashed_password):
        audit(
            db,
            action="auth.login_failed",
            message="Password change with wrong current password",
            user_id=user.id,
            actor=Actor.USER,
            level=AuditLevel.WARN,
            meta={"scope": "password_change"},
        )
        _persist(db)
        raise UnauthorizedError("Current password is incorrect", code="invalid_credentials")
    validate_password(new_password)
    user.hashed_password = hash_password(new_password)
    revoked = revoke_all_tokens(db, user.id)
    audit(
        db,
        action="auth.password_changed",
        message="Password changed",
        user_id=user.id,
        actor=Actor.USER,
        meta={"sessions_revoked": revoked},
    )
    logger.info("Password changed for user %s", user.email)
    return user


# --------------------------------------------------------------------------- tokens


def issue_access_token(user: User) -> str:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return create_access_token(user.id, role)


def create_refresh_token(db: Session, user: User, *, user_agent: str | None = None) -> str:
    raw = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=refresh_token_expiry(),
            user_agent=(user_agent or "")[:512] or None,
            created_at=utcnow(),
        )
    )
    db.flush()
    return raw


def get_refresh_token(db: Session, raw_token: str) -> RefreshToken | None:
    if not raw_token:
        return None
    return db.scalars(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))).first()


def revoke_all_tokens(db: Session, user_id: uuid.UUID) -> int:
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.flush()
    return int(result.rowcount or 0)


def _is_expired(token: RefreshToken) -> bool:
    expires_at = token.expires_at
    if expires_at.tzinfo is None:  # SQLite hands back naive datetimes
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def rotate_refresh_token(
    db: Session,
    raw_token: str | None,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[User, str]:
    """Validate and rotate a refresh token. Returns ``(user, new_raw_token)``.

    Reuse of an already revoked token revokes the whole family (token theft response).
    """
    if not raw_token:
        raise UnauthorizedError("Missing refresh token", code="missing_refresh_token")
    token = get_refresh_token(db, raw_token)
    if token is None:
        raise UnauthorizedError("Invalid refresh token", code="invalid_refresh_token")

    if token.revoked_at is not None:
        revoked = revoke_all_tokens(db, token.user_id)
        audit(
            db,
            action="auth.refresh_reuse_detected",
            message="Revoked refresh token presented - all sessions revoked",
            user_id=token.user_id,
            actor=Actor.USER,
            level=AuditLevel.ERROR,
            meta={"sessions_revoked": revoked},
            ip_address=ip_address,
        )
        _persist(db)
        logger.error("Refresh token reuse detected for user %s", token.user_id)
        raise UnauthorizedError("Refresh token has been revoked", code="refresh_token_reused")

    if _is_expired(token):
        token.revoked_at = utcnow()
        _persist(db)
        raise UnauthorizedError("Refresh token expired", code="refresh_token_expired")

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive", code="invalid_refresh_token")

    new_raw = create_refresh_token(db, user, user_agent=user_agent)
    token.revoked_at = utcnow()
    token.replaced_by_hash = hash_token(new_raw)
    db.flush()
    return user, new_raw


def revoke_refresh_token(db: Session, raw_token: str | None, *, ip_address: str | None = None) -> User | None:
    """Revoke the presented refresh token (logout). Unknown tokens are ignored."""
    token = get_refresh_token(db, raw_token or "")
    if token is None:
        return None
    if token.revoked_at is None:
        token.revoked_at = utcnow()
    audit(
        db,
        action="auth.logout",
        message="Logout",
        user_id=token.user_id,
        actor=Actor.USER,
        ip_address=ip_address,
    )
    db.flush()
    return db.get(User, token.user_id)
