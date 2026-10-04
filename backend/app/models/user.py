from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String, and_
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    SCHEMA_MASTER,
    Base,
    LifecycleMixin,
    TimestampMixin,
    UTCDateTime,
    UUIDMixin,
    soft_delete_where,
)
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.automation import AutomationConfig, ConnectedAccount
    from app.models.email import EmailIntegration
    from app.models.notification import Notification
    from app.models.profile import CompanyPreference, JobPreference, UserProfile
    from app.models.resume import Resume


#: The roles every JobPilot database starts with. The rows themselves are created by
#: the Alembic migration, so a freshly migrated database needs no seed run; this tuple is
#: the single description of them, re-used by the migration, the test fixtures and
#: ``auth.service.ensure_default_roles``.
DEFAULT_ROLES: tuple[tuple[str, str], ...] = (
    ("USER", "Standard JobPilot account"),
    ("ADMIN", "Full administrative access"),
)


class Role(UUIDMixin, TimestampMixin, LifecycleMixin, Base):
    """A named role. The row is the authority; :class:`~app.models.enums.UserRole` stays
    as the *vocabulary* of the well-known names the code guards on (``USER``, ``ADMIN``).

    A role is reached only through :class:`UserRoleAssignment` — never as a column on
    ``users`` — so a user can hold several at once and a new role is a row, not a migration.
    """

    __tablename__ = "roles"
    __table_args__ = (
        # Partial: a deleted role must not keep its name reserved (see LifecycleMixin).
        Index("uq_roles_name_active", "name", unique=True, **soft_delete_where()),
        {"schema": SCHEMA_MASTER},
    )

    name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Role {self.name}>"


class UserRoleAssignment(UUIDMixin, TimestampMixin, LifecycleMixin, Base):
    """The user↔role junction: one row per role a user holds. Nothing else lives here.

    The class is named ``UserRoleAssignment`` only because ``UserRole`` is already taken
    by the enum in :mod:`app.models.enums`, which stays the vocabulary of well-known role
    names. The *table* is ``master.user_roles``, named after both sides of the
    relationship as every junction table in this schema is.

    A generic "everything this user links to" hub table was considered and rejected: a
    user has many roles but one location and one team, so no single row shape fits both
    cardinalities, and squeezing them together would mean nullable foreign keys — which
    contradicts the rule that every link is an enforced uuid FK. One-to-many keys go on
    the owning row instead (a future ``user_profiles.location_id``), and each new
    many-to-many gets its own junction table. See ``docs/DATABASE.md``.
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        # Partial: revoking a role tombstones the row, and the same role must be
        # grantable again afterwards.
        Index("uq_user_roles_user_role_active", "user_id", "role_id", unique=True, **soft_delete_where()),
        {"schema": SCHEMA_MASTER},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.roles.id", ondelete="CASCADE"), index=True, nullable=False)

    role: Mapped[Role] = relationship(lazy="joined")


class User(UUIDMixin, TimestampMixin, LifecycleMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Partial unique: a soft-deleted account must not keep its address hostage, so
        # the same person can sign up again. Lookups by email always carry
        # ``deleted_at IS NULL`` (the global filter), so this index serves them too.
        Index("uq_users_email_active", "email", unique=True, **soft_delete_where()),
        {"schema": SCHEMA_MASTER},
    )

    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    #: Roles held *now*: the join deliberately skips tombstoned junction rows, because a
    #: revoked role is a soft-deleted ``user_roles`` row and the global ORM filter only
    #: reaches mapped entities, not a ``secondary`` table.
    roles: Mapped[list[Role]] = relationship(
        secondary="master.user_roles",
        primaryjoin=lambda: and_(User.id == UserRoleAssignment.user_id, UserRoleAssignment.deleted_at.is_(None)),
        secondaryjoin=lambda: Role.id == UserRoleAssignment.role_id,
        lazy="selectin",
        viewonly=False,
        order_by=lambda: Role.name,
        # Both this relationship (through ``secondary``) and ``UserRoleAssignment.role``
        # write ``user_roles.role_id``. That is intended — the junction rows are a mapped
        # entity in their own right so the service layer can tombstone one — and
        # ``overlaps`` is how SQLAlchemy is told the duplication is deliberate.
        overlaps="role",
    )

    profile: Mapped[UserProfile | None] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    job_preference: Mapped[JobPreference | None] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    company_preferences: Mapped[list[CompanyPreference]] = relationship(back_populates="user", cascade="all, delete-orphan")
    resumes: Mapped[list[Resume]] = relationship(back_populates="user", cascade="all, delete-orphan")
    applications: Mapped[list[Application]] = relationship(back_populates="user", cascade="all, delete-orphan")
    automation_config: Mapped[AutomationConfig | None] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    email_integration: Mapped[EmailIntegration | None] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    connected_accounts: Mapped[list[ConnectedAccount]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list[Notification]] = relationship(back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def role_names(self) -> list[str]:
        """The names of the roles currently held, sorted. Shape served by ``UserRead``."""
        return sorted(role.name for role in self.roles)

    @property
    def role(self) -> UserRole:
        """The single most privileged role held — the shape the guards and the API use.

        ``users.role`` used to be an enum column; it is now derived from ``user_roles``
        so that every RBAC call site (``require_roles``, ``UserRead.role``, the JWT claim)
        keeps reading one value while the storage underneath is many-to-many. A user with
        no role row at all is a plain ``USER``.
        """
        if UserRole.ADMIN.value in {role.name for role in self.roles}:
            return UserRole.ADMIN
        return UserRole.USER

    def has_role(self, name: str | UserRole) -> bool:
        wanted = name.value if isinstance(name, UserRole) else name
        return any(role.name == wanted for role in self.roles)


class RefreshToken(UUIDMixin, LifecycleMixin, Base):
    """Opaque refresh tokens, stored hashed. Rotated on every refresh."""

    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": SCHEMA_MASTER}

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    replaced_by_hash: Mapped[str | None] = mapped_column(String(128))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
