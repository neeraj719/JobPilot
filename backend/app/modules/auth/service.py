"""Authentication service: users, passwords, access + rotating refresh tokens (contract §2).

Security notes:

* Refresh tokens are opaque random strings; only their SHA-256 hash is stored.
* Every refresh rotates the token: the presented token is revoked and linked to its
  successor through ``replaced_by_hash``.
* Presenting an already revoked token is treated as theft: **every** token of that user
  is revoked and ``auth.refresh_reuse_detected`` is audited at ERROR level.
* Login failures never reveal whether the email exists ("Invalid email or password").

Active role (see ``docs/SECURITY.md``):

* A user may hold several roles. The access token's ``role`` claim is the one this
  session *acts as*; guards check it, not membership.
* An account with more than one role gets a 5-minute role-selection token from login
  instead of a session, and trades it for one at ``POST /auth/select-role``.
* The active role survives ``/auth/refresh`` because it is part of the opaque refresh
  token itself (``"<ROLE>.<random>"``), whose SHA-256 is what the database stores. The
  client cannot alter the prefix without changing the hash, so the lookup fails; no
  column is needed and nothing is kept in process memory.

Stay signed in (see ``docs/SECURITY.md``, "Sessions and remembered devices"):

* ``remember_me=true``: the refresh token lives ``REFRESH_TOKEN_EXPIRE_DAYS`` and the
  cookie is persistent (``Max-Age``). ``remember_me=false`` (the default): the token
  lives :data:`SHORT_SESSION_HOURS` and the cookie is a *session* cookie that dies with
  the browser.
* The choice survives rotation without a column: it is read back from the presented
  row's lifetime (``expires_at - created_at``), which this module alone sets and which
  differs by more than an order of magnitude between the two kinds. The same rule labels
  every row in the sessions list, including other devices whose raw token we never see.
* A session the user signs out from the device list (or that a password change signs
  out) is revoked **and** tombstoned. Presenting it later is answered with
  ``401 session_revoked`` and does not trip the reuse response, so signing out a lost
  laptop cannot, when that laptop next wakes up, sign out every other device too.
"""
from __future__ import annotations

import logging
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.actor import actor_context
from app.core.audit import audit
from app.core.config import settings
from app.core.database import restore, soft_delete
from app.core.deps import held_role_names, highest_role_name
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError, ValidationFailed
from app.core.rate_limit import rate_limiter
from app.core.security import (
    create_access_token,
    create_role_selection_token,
    decode_role_selection_token,
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
from app.models.user import DEFAULT_ROLES, RefreshToken, Role, User, UserRoleAssignment
from app.modules.auth.devices import device_label
from app.modules.auth.schemas import PASSWORD_POLICY, SessionRead, check_password_policy

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Invalid email or password"
REFRESH_COOKIE_NAME = "refresh_token"

#: Lifetime of the token handed out between the password check and the role choice.
#: Deliberately a constant here rather than a setting: it is a protocol detail, not a knob.
ROLE_SELECTION_TTL_SECONDS = 5 * 60

#: Lifetime of a session that did not ask to be remembered. A protocol constant of this
#: module (like the one above), not a setting: the remembered lifetime is the setting.
SHORT_SESSION_HOURS = 12

#: ``"<ROLE>.<random>"``: the active role travels inside the opaque refresh token. Role
#: names are upper-case identifiers and ``token_urlsafe`` never emits a ``.``, so the
#: first dot always separates the two.
_REFRESH_ROLE_SEPARATOR = "."
_ROLE_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,49}$")


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


def refresh_cookie_max_age(remember: bool = True) -> int | None:
    """``Max-Age`` of the refresh cookie; ``None`` makes it a browser-session cookie."""
    if not remember:
        return None
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def session_lifetime(remember: bool) -> timedelta:
    """How long a refresh token lives: remembered device vs this browser session only."""
    if remember:
        return timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return timedelta(hours=SHORT_SESSION_HOURS)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def is_remembered(token: RefreshToken) -> bool:
    """Was this refresh token minted for a remembered device?

    Read from the row's own lifetime: anything longer than halfway between the short and
    the remembered lifetime is remembered. The midpoint keeps the rule independent of the
    few milliseconds between ``created_at`` and ``expires_at`` being computed, and of
    ``REFRESH_TOKEN_EXPIRE_DAYS`` being tuned. Legacy rows (minted before the choice
    existed) all have the full lifetime, which is what they were: remembered.
    """
    if token.created_at is None or token.expires_at is None:
        return True
    span = _aware(token.expires_at) - _aware(token.created_at)
    threshold = (session_lifetime(True) + session_lifetime(False)) / 2
    return span > threshold


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

    # The id is generated here rather than left to the column default so the account can
    # be its own ``created_by``: registration has no acting user yet, and attributing the
    # row to "nobody" would read as a system write. Everything created for the account
    # below is attributed to it too, which is what ``actor_context`` is for.
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=True,
        is_verified=False,
    )
    user.created_by = user.updated_by = user.id
    db.add(user)
    db.flush()

    with actor_context(user.id):
        # The role is a row in ``master.user_roles``, not a column on ``users``.
        assign_role(db, user, role)

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
        # Flushed inside the block on purpose: the stamping listeners run at flush time,
        # so a row added here and flushed by the caller's commit would miss the actor.
        db.flush()
    logger.info("Registered user %s", email)
    return user


# --------------------------------------------------------------------------- roles


def ensure_default_roles(db: Session) -> list[Role]:
    """Create any missing row of :data:`app.models.user.DEFAULT_ROLES` (idempotent).

    Production never needs this — the migration inserts the rows. It exists for the
    paths that build the schema from ``Base.metadata`` instead of from the migration
    chain (the test fixtures), so that "the roles table is reference data" holds there too.
    """
    existing = {role.name for role in db.scalars(select(Role).execution_options(include_deleted=True))}
    created: list[Role] = []
    for name, description in DEFAULT_ROLES:
        if name in existing:
            continue
        role = Role(name=name, description=description)
        db.add(role)
        created.append(role)
    if created:
        db.flush()
    return created


def get_role(db: Session, name: str | UserRole) -> Role | None:
    """Look up a role by name. The rows are created by the migration, not by the seed,
    so a freshly migrated database already knows ``USER`` and ``ADMIN``."""
    wanted = name.value if isinstance(name, UserRole) else str(name)
    return db.scalars(select(Role).where(Role.name == wanted)).first()


def _require_role(db: Session, name: str | UserRole) -> Role:
    role = get_role(db, name)
    if role is None:
        raise ValidationFailed(f"Unknown role {name}", code="unknown_role")
    return role


def assign_role(db: Session, user: User, role_name: str | UserRole) -> UserRoleAssignment:
    """Link ``user`` to a role through ``user_roles`` (idempotent).

    A previously revoked link is *restored* rather than duplicated: the partial unique
    index only covers live rows, so a second INSERT would succeed and leave two mappings
    where the user sees one role.
    """
    role = _require_role(db, role_name)
    existing = db.scalars(
        select(UserRoleAssignment)
        .where(UserRoleAssignment.user_id == user.id, UserRoleAssignment.role_id == role.id)
        .order_by(UserRoleAssignment.created_at.desc())
        .execution_options(include_deleted=True)
    ).first()
    if existing is not None:
        restore(existing)
        mapping = existing
    else:
        mapping = UserRoleAssignment(user_id=user.id, role_id=role.id)
        db.add(mapping)
    db.flush()
    db.expire(user, ["roles"])
    return mapping


def revoke_role(db: Session, user: User, role_name: str | UserRole) -> bool:
    """Soft-delete the user's link to ``role_name``. Returns False if they did not hold it."""
    role = _require_role(db, role_name)
    mapping = db.scalars(
        select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id, UserRoleAssignment.role_id == role.id)
    ).first()
    if mapping is None:
        return False
    soft_delete(mapping)
    db.flush()
    db.expire(user, ["roles"])
    return True


#: Bcrypt hash of an unguessable string, used to keep the "unknown email" path as slow
#: as the "wrong password" path (otherwise response time enumerates registered accounts).
_DUMMY_HASH = hash_password(secrets.token_urlsafe(24))


def authenticate(db: Session, email: str, password: str, *, ip_address: str | None = None) -> User:
    """Return the user for valid credentials, else raise a *generic* 401."""
    email = normalize_email(email)
    user = get_user_by_email(db, email)
    password_ok = verify_password(password, user.hashed_password if user is not None else _DUMMY_HASH)
    if user is None or not password_ok:
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


@dataclass
class PasswordChanged:
    """What ``change_password`` hands the router: the rotated cookie of *this* device.

    ``refresh_token`` is ``None`` when the request carried no usable refresh cookie; the
    router then clears the cookie and this device signs in again like the others.
    """

    user: User
    refresh_token: str | None
    remembered: bool
    sessions_revoked: int


def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    *,
    raw_refresh_token: str | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> PasswordChanged:
    """Change the password, sign out every *other* session and rotate this one.

    Other sessions are revoked and tombstoned (see the module docstring), so a device
    signed out here that later presents its old cookie is told ``session_revoked``
    rather than triggering the theft response against the session that is still in use.
    """
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

    current = current_session_token(db, user, raw_refresh_token)
    revoked = sign_out_sessions(db, user, keep=current)
    new_raw: str | None = None
    remembered = False
    if current is not None:
        try:
            rotation = rotate(db, raw_refresh_token, user_agent=user_agent, ip_address=ip_address, expected_user_id=user.id)
        except UnauthorizedError:
            # E.g. the role this session acted as was revoked: sign this device out too.
            revoked += sign_out_sessions(db, user)
        else:
            new_raw, remembered = rotation.refresh_token, rotation.remembered
    audit(
        db,
        action="auth.password_changed",
        message="Password changed",
        user_id=user.id,
        actor=Actor.USER,
        meta={"sessions_revoked": revoked, "current_session_kept": new_raw is not None},
        ip_address=ip_address,
    )
    logger.info("Password changed for user %s", user.email)
    return PasswordChanged(user=user, refresh_token=new_raw, remembered=remembered, sessions_revoked=revoked)


# --------------------------------------------------------------------------- tokens


def normalize_role_name(role: str | UserRole) -> str:
    value = role.value if isinstance(role, UserRole) else str(role or "")
    return value.strip().upper()


def issue_access_token(user: User, active_role: str | None = None) -> str:
    """Access token acting as ``active_role`` (default: the highest role held)."""
    return create_access_token(user.id, active_role or highest_role_name(user))


def refresh_token_role(raw_token: str | None) -> str | None:
    """The active role encoded in a refresh token, or ``None`` for a legacy token."""
    if not raw_token or _REFRESH_ROLE_SEPARATOR not in raw_token:
        return None
    prefix = raw_token.split(_REFRESH_ROLE_SEPARATOR, 1)[0]
    return prefix if _ROLE_NAME_RE.match(prefix) else None


def create_refresh_token(
    db: Session,
    user: User,
    *,
    user_agent: str | None = None,
    active_role: str | None = None,
    remember: bool = True,
) -> str:
    """Create and store (hashed) a refresh token whose session acts as ``active_role``.

    ``remember`` picks the lifetime (:func:`session_lifetime`); ``created_at`` is set
    from the same clock reading so :func:`is_remembered` can read the choice back.
    """
    role = normalize_role_name(active_role or highest_role_name(user))
    raw = f"{role}{_REFRESH_ROLE_SEPARATOR}{generate_refresh_token()}"
    now = utcnow()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=refresh_token_expiry() if remember else now + session_lifetime(False),
            user_agent=(user_agent or "")[:512] or None,
            created_at=now,
        )
    )
    db.flush()
    return raw


def get_refresh_token(db: Session, raw_token: str, *, include_deleted: bool = False) -> RefreshToken | None:
    if not raw_token:
        return None
    statement = select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    if include_deleted:
        statement = statement.execution_options(include_deleted=True)
    return db.scalars(statement).first()


def _active_tokens_query(user_id: uuid.UUID):
    return select(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > utcnow(),
    )


def current_session_token(db: Session, user: User, raw_token: str | None) -> RefreshToken | None:
    """The live refresh-token row behind the cookie on this request, if it is ``user``'s."""
    token = get_refresh_token(db, raw_token or "")
    if token is None or token.user_id != user.id or token.revoked_at is not None or _is_expired(token):
        return None
    return token


def sign_out_sessions(db: Session, user: User, *, keep: RefreshToken | None = None) -> int:
    """Revoke and tombstone every live session of ``user`` except ``keep``.

    Used for "sign out of all other devices" and by a password change. Tombstoning is
    what tells a signed-out device's later refresh apart from token theft.
    """
    statement = _active_tokens_query(user.id)
    if keep is not None:
        statement = statement.where(RefreshToken.id != keep.id)
    now = utcnow()
    count = 0
    for token in db.scalars(statement):
        token.revoked_at = now
        soft_delete(token, when=now)
        count += 1
    db.flush()
    return count


def revoke_all_tokens(db: Session, user_id: uuid.UUID) -> int:
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.flush()
    return int(result.rowcount or 0)


def _is_expired(token: RefreshToken) -> bool:
    return _aware(token.expires_at) <= datetime.now(timezone.utc)


@dataclass
class Rotation:
    """Outcome of :func:`rotate`: the successor token and what it carries over."""

    user: User
    refresh_token: str
    active_role: str
    remembered: bool


def rotate(
    db: Session,
    raw_token: str | None,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
    active_role: str | None = None,
    expected_user_id: uuid.UUID | None = None,
    remember: bool | None = None,
) -> Rotation:
    """Validate and rotate a refresh token.

    The successor keeps the presented token's active role unless ``active_role`` says
    otherwise (``switch-role``), and keeps its remember choice (read from the presented
    row's lifetime, see :func:`is_remembered`) unless ``remember`` says otherwise (the
    "keep this device signed in" switch in Settings): a remembered session stays
    remembered, a short one stays short. A role the user no longer holds is refused with
    ``401 role_revoked`` and the token is left as it is (revoking it would make a second
    tab's retry look like token theft). ``expected_user_id`` ties the cookie to the
    caller's access token when both are presented.

    Order of the checks:

    * a token the user signed out from the device list -> ``401 session_revoked``;
    * an expired token -> ``401 refresh_token_expired``. Checked before reuse so a
      browser left open past a 12-hour session cannot, by retrying its dead cookie,
      look like a thief and sign the user out everywhere;
    * reuse of an already revoked or replaced token revokes the whole family
      (token theft response) -> ``401 refresh_token_reused``.
    """
    if not raw_token:
        raise UnauthorizedError("Missing refresh token", code="missing_refresh_token")
    token = get_refresh_token(db, raw_token, include_deleted=True)
    if token is None:
        raise UnauthorizedError("Invalid refresh token", code="invalid_refresh_token")

    if token.deleted_at is not None:
        audit(
            db,
            action="auth.signed_out_session_presented",
            message="A session that was signed out from the device list tried to refresh",
            user_id=token.user_id,
            actor=Actor.USER,
            level=AuditLevel.WARN,
            ip_address=ip_address,
        )
        _persist(db)
        raise UnauthorizedError("This device was signed out. Sign in again.", code="session_revoked")

    if _is_expired(token):
        if token.revoked_at is None:
            token.revoked_at = utcnow()
        _persist(db)
        raise UnauthorizedError("Refresh token expired", code="refresh_token_expired")

    if token.revoked_at is not None or token.replaced_by_hash is not None:
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

    if expected_user_id is not None and token.user_id != expected_user_id:
        raise UnauthorizedError("Invalid refresh token", code="invalid_refresh_token")

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive", code="invalid_refresh_token")

    # Legacy tokens (minted before the active role existed) carry no prefix and keep
    # meaning what they always did: the highest role held.
    role = normalize_role_name(active_role or refresh_token_role(raw_token) or highest_role_name(user))
    if role not in held_role_names(user):
        raise UnauthorizedError("The role this session was using has been revoked", code="role_revoked")

    remembered = is_remembered(token) if remember is None else bool(remember)
    new_raw = create_refresh_token(db, user, user_agent=user_agent, active_role=role, remember=remembered)
    token.revoked_at = utcnow()
    token.replaced_by_hash = hash_token(new_raw)
    db.flush()
    user.active_role = role
    return Rotation(user=user, refresh_token=new_raw, active_role=role, remembered=remembered)


def rotate_refresh_token(
    db: Session,
    raw_token: str | None,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
    active_role: str | None = None,
    expected_user_id: uuid.UUID | None = None,
) -> tuple[User, str, str]:
    """:func:`rotate`, returning ``(user, new_raw_token, active_role)``."""
    rotation = rotate(
        db,
        raw_token,
        user_agent=user_agent,
        ip_address=ip_address,
        active_role=active_role,
        expected_user_id=expected_user_id,
    )
    return rotation.user, rotation.refresh_token, rotation.active_role


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


# --------------------------------------------------------------------------- sessions + active role


@dataclass
class IssuedSession:
    """What a successful sign-in, role choice, switch or refresh hands back to the router.

    ``refresh_token`` is ``None`` when no new refresh token was minted (a no-op switch),
    in which case the router leaves the cookie alone. ``remembered`` decides whether the
    router sets a persistent cookie or a browser-session one.
    """

    user: User
    active_role: str
    access_token: str
    expires_in: int
    available_roles: list[str]
    refresh_token: str | None
    remembered: bool = True


@dataclass
class RoleSelectionChallenge:
    """Login succeeded but the account holds several roles: the client must pick one."""

    user: User
    selection_token: str
    available_roles: list[str]


def _issue(user: User, role: str, refresh_raw: str | None, *, remembered: bool = True) -> IssuedSession:
    user.active_role = role
    return IssuedSession(
        user=user,
        active_role=role,
        access_token=issue_access_token(user, role),
        expires_in=access_token_ttl_seconds(),
        available_roles=held_role_names(user),
        refresh_token=refresh_raw,
        remembered=remembered,
    )


def start_session(
    db: Session,
    user: User,
    *,
    active_role: str,
    user_agent: str | None = None,
    remember_me: bool = False,
) -> IssuedSession:
    """Mint access + refresh tokens for ``user`` acting as ``active_role``."""
    role = normalize_role_name(active_role)
    raw = create_refresh_token(db, user, user_agent=user_agent, active_role=role, remember=remember_me)
    return _issue(user, role, raw, remembered=remember_me)


def begin_session(
    db: Session, user: User, *, user_agent: str | None = None, remember_me: bool = False
) -> IssuedSession | RoleSelectionChallenge:
    """After the password check: a session for a single-role account, else a challenge.

    The challenge creates no refresh token, so no cookie is set until a role is chosen;
    the client repeats ``remember_me`` on ``/auth/select-role``.
    """
    roles = held_role_names(user)
    if len(roles) == 1:
        return start_session(db, user, active_role=roles[0], user_agent=user_agent, remember_me=remember_me)
    user.active_role = None
    token = create_role_selection_token(user.id, roles, ttl_seconds=ROLE_SELECTION_TTL_SECONDS)
    return RoleSelectionChallenge(user=user, selection_token=token, available_roles=roles)


def select_role(
    db: Session,
    selection_token: str,
    role: str,
    *,
    remember: bool = False,
    remember_me: bool = False,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> IssuedSession:
    """Trade a role-selection token for a session acting as ``role``.

    ``remember`` is the client's per-device *role* preference (audited only);
    ``remember_me`` is "stay signed in on this device" and sets the session lifetime.

    The token is single-use: once it has produced a session, presenting it again is
    refused. The used-token marker goes through the rate limiter's backend (Redis when
    available, so it holds across workers; in-process otherwise).
    """
    try:
        payload = decode_role_selection_token(selection_token)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError(
            "The role selection timed out. Sign in again.", code="selection_token_expired"
        ) from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid role selection token", code="invalid_selection_token") from exc

    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Invalid role selection token", code="invalid_selection_token") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive", code="invalid_selection_token")

    wanted = normalize_role_name(role)
    offered = {normalize_role_name(name) for name in payload.get("roles", [])}
    if wanted not in offered:
        raise ForbiddenError(f"You cannot sign in as {wanted}", code="role_not_held")
    if wanted not in held_role_names(user):
        raise ForbiddenError(f"You no longer hold the {wanted} role", code="role_not_held")

    jti = str(payload.get("jti") or "")
    first_use, _ = rate_limiter.check(f"auth:selection-used:{jti}", 1, ROLE_SELECTION_TTL_SECONDS)
    if not jti or not first_use:
        raise UnauthorizedError(
            "This role selection has already been used. Sign in again.", code="selection_token_used"
        )

    session = start_session(db, user, active_role=wanted, user_agent=user_agent, remember_me=remember_me)
    audit(
        db,
        action="auth.role_selected",
        message=f"Signed in as {wanted}",
        user_id=user.id,
        actor=Actor.USER,
        meta={
            "role": wanted,
            "available_roles": session.available_roles,
            "remember": bool(remember),
            "remember_me": bool(remember_me),
        },
        ip_address=ip_address,
    )
    return session


def switch_role(
    db: Session,
    user: User,
    role: str,
    *,
    current_role: str,
    current_access_token: str,
    current_access_exp: int | None,
    raw_refresh_token: str | None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> IssuedSession:
    """Change the active role of the caller's session without signing out.

    * ``403 role_not_held`` for a role the user does not hold.
    * Switching to the current role is a no-op: the presented access token is handed
      back unchanged and the refresh token is not rotated. (Minting a fresh access token
      here would let a bare access token renew itself forever without the cookie.)
    * Otherwise the refresh cookie is rotated through :func:`rotate_refresh_token` - so
      a stolen or reused cookie trips the usual theft response - and the new access and
      refresh tokens both carry the new role. No cookie, no switch: an access token alone
      must not be able to mint a long-lived session.
    """
    wanted = normalize_role_name(role)
    available = held_role_names(user)
    if wanted not in available:
        raise ForbiddenError(f"You do not hold the {wanted} role", code="role_not_held")

    if wanted == current_role:
        now = int(datetime.now(timezone.utc).timestamp())
        remaining = max(0, int(current_access_exp) - now) if current_access_exp else access_token_ttl_seconds()
        user.active_role = wanted
        return IssuedSession(
            user=user,
            active_role=wanted,
            access_token=current_access_token,
            expires_in=remaining,
            available_roles=available,
            refresh_token=None,
        )

    rotation = rotate(
        db,
        raw_refresh_token,
        user_agent=user_agent,
        ip_address=ip_address,
        active_role=wanted,
        expected_user_id=user.id,
    )
    audit(
        db,
        action="auth.role_switched",
        message=f"Switched role from {current_role} to {wanted}",
        user_id=user.id,
        actor=Actor.USER,
        meta={"from": current_role, "to": wanted},
        ip_address=ip_address,
    )
    return _issue(user, wanted, rotation.refresh_token, remembered=rotation.remembered)


# --------------------------------------------------------------------------- sessions and devices


def list_sessions(db: Session, user: User, raw_token: str | None) -> list[SessionRead]:
    """Every live session (unrevoked, unexpired refresh token) of ``user``, newest first.

    A session's ``id`` is its current refresh-token row, so it changes each time that
    device refreshes (every access-token lifetime); clients re-fetch after acting on one.
    """
    current = current_session_token(db, user, raw_token)
    tokens = db.scalars(_active_tokens_query(user.id).order_by(RefreshToken.created_at.desc())).all()
    return [_session_read(token, is_current=current is not None and token.id == current.id) for token in tokens]


def _session_read(token: RefreshToken, *, is_current: bool) -> SessionRead:
    return SessionRead(
        id=token.id,
        created_at=token.created_at,
        expires_at=token.expires_at,
        user_agent=token.user_agent,
        device_label=device_label(token.user_agent),
        is_current=is_current,
        remembered=is_remembered(token),
    )


def set_current_session_remembered(
    db: Session,
    user: User,
    raw_token: str | None,
    remember: bool,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[Rotation, SessionRead]:
    """Turn "stay signed in" on or off for the session making the request.

    Rotates this device's refresh token into one with the chosen lifetime (the password
    is never needed or kept: the session itself is the proof, plus the re-authentication
    gate on the endpoint). The router sets the matching cookie.
    """
    if current_session_token(db, user, raw_token) is None:
        raise UnauthorizedError("This browser has no active session to remember. Sign in again.", code="missing_refresh_token")
    rotation = rotate(
        db, raw_token, user_agent=user_agent, ip_address=ip_address, expected_user_id=user.id, remember=remember
    )
    audit(
        db,
        action="auth.session_remember_changed",
        message="Stay signed in turned on for this device" if remember else "Stay signed in turned off for this device",
        user_id=user.id,
        actor=Actor.USER,
        meta={"remembered": bool(remember)},
        ip_address=ip_address,
    )
    db.flush()
    row = get_refresh_token(db, rotation.refresh_token)
    assert row is not None  # just created in this transaction
    return rotation, _session_read(row, is_current=True)


def revoke_session(
    db: Session, user: User, session_id: uuid.UUID, raw_token: str | None, *, ip_address: str | None = None
) -> bool:
    """Sign out one of ``user``'s sessions. Returns whether it was the caller's own.

    ``404`` for an id that is not one of the user's live sessions: another user's id and
    a made-up one look the same.
    """
    token = db.scalars(_active_tokens_query(user.id).where(RefreshToken.id == session_id)).first()
    if token is None:
        raise NotFoundError("Session not found", code="session_not_found")
    current = current_session_token(db, user, raw_token)
    is_current = current is not None and current.id == token.id
    token.revoked_at = utcnow()
    soft_delete(token, when=token.revoked_at)
    audit(
        db,
        action="auth.session_revoked",
        message=f"Signed out {device_label(token.user_agent)}",
        user_id=user.id,
        actor=Actor.USER,
        meta={"session_id": str(token.id), "current": is_current, "remembered": is_remembered(token)},
        ip_address=ip_address,
    )
    db.flush()
    return is_current


def revoke_other_sessions(db: Session, user: User, raw_token: str | None, *, ip_address: str | None = None) -> int:
    """Sign out every session of ``user`` except the one making the request."""
    current = current_session_token(db, user, raw_token)
    revoked = sign_out_sessions(db, user, keep=current)
    audit(
        db,
        action="auth.sessions_revoked_others",
        message=f"Signed out {revoked} other session(s)",
        user_id=user.id,
        actor=Actor.USER,
        meta={"sessions_revoked": revoked, "current_session_kept": current is not None},
        ip_address=ip_address,
    )
    db.flush()
    return revoked


def refresh_session(
    db: Session, raw_token: str | None, *, user_agent: str | None = None, ip_address: str | None = None
) -> IssuedSession:
    """``POST /auth/refresh``: rotate the cookie, keep the session's active role and lifetime."""
    rotation = rotate(db, raw_token, user_agent=user_agent, ip_address=ip_address)
    return _issue(rotation.user, rotation.active_role, rotation.refresh_token, remembered=rotation.remembered)
