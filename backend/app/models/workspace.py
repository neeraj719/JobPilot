"""The multi-module workspace: the module catalog and each user's settings for it.

JobPilot is a suite of **modules** (Resume Studio, Job Apply, ...). After sign-in the user
lands on a launcher of module cards, opens one, and from then on sees that module's own
sidebar. Modules are data, not hard-coded menus:

* :class:`WorkspaceModule` (``master.modules``) — the catalog. One row per module code,
  seeded by migration ``f6b8d0c2e4a7`` (and by :func:`app.modules.workspace.service.
  ensure_catalog`, idempotent). ``is_enabled`` is the platform-wide switch, ``min_role`` the
  least role that may open it, ``status`` ``AVAILABLE`` / ``COMING_SOON``.
* :class:`UserModuleSetting` (``master.user_module_settings``) — one live row per
  (user, module), created lazily: ``is_enabled`` (an admin can switch a module off for one
  user), ``is_pinned``, the user's own ``sort_order``, ``last_opened_at``, ``open_count``.
* :class:`UserWorkspacePreference` (``master.user_workspace_preferences``) — one live row
  per user: ``landing`` (launcher or last module), ``last_module_id``, ``show_tips``.

The client renders modules from its own registry (icons, routes, sidebar sections); the
server decides which ones the user sees and in what order.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SCHEMA_MASTER, Base, StandardColumnsMixin, UTCDateTime, soft_delete_where
from app.models.enums import ModuleStatus, UserRole, WorkspaceLanding

#: The catalog every JobPilot database starts with, in launcher order. The migration
#: inserts a frozen copy of these rows; ``workspace.service.ensure_catalog`` creates any
#: that are **missing** (never overwriting an admin's later change) for the paths that build
#: from metadata (the seed). ``apply`` starts switched off platform-wide: the owner works on
#: Resume Studio only for now and turns Job Apply on from Settings › Admin when ready.
#: ``(code, name, tagline, description, icon, home_path, accent, sort_order, is_enabled, status)``
DEFAULT_MODULES: tuple[tuple[str, str, str, str, str, str | None, str, int, bool, ModuleStatus], ...] = (
    (
        "resume",
        "Resume Studio",
        "Build, score and tailor your resume",
        "Create and edit resumes, check them against a job description (an estimate, not a "
        "promise) and keep a tailored version per role.",
        "FileText",
        "/resume",
        "primary",
        10,
        True,
        ModuleStatus.AVAILABLE,
    ),
    (
        "apply",
        "Job Apply",
        "Discover jobs, apply with approval, track replies",
        "Matched jobs, the application queue you approve, applications, interviews, companies, "
        "the daily automation and the replies detected in Gmail.",
        "Briefcase",
        "/dashboard",
        "info",
        20,
        False,  # switched off platform-wide until an admin enables it
        ModuleStatus.AVAILABLE,
    ),
    (
        "insights",
        "Career Insights",
        "Market trends and salary signals - coming soon",
        "Hiring trends for your target roles and how your pipeline compares. Not available yet.",
        "LineChart",
        None,  # no route yet; it cannot be made AVAILABLE until it has one
        "warning",
        30,
        True,
        ModuleStatus.COMING_SOON,
    ),
)


class WorkspaceModule(StandardColumnsMixin, Base):
    """One module in the catalog. Named ``WorkspaceModule`` because ``Module`` reads as a
    Python module everywhere it is imported; the table is ``master.modules``."""

    __tablename__ = "modules"
    __table_args__ = (
        Index("uq_modules_code_active", "code", unique=True, **soft_delete_where()),
        {"schema": SCHEMA_MASTER},
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    tagline: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: A lucide icon name (``FileText``); the client maps it, unknown names fall back.
    icon: Mapped[str] = mapped_column(String(40), nullable=False)
    #: ``None`` for a module with no pages yet (``COMING_SOON``).
    home_path: Mapped[str | None] = mapped_column(String(200))
    #: A design-token name (``primary``, ``info``...), never a hex colour.
    accent: Mapped[str] = mapped_column(String(40), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Platform-wide switch: ``False`` hides the module from everybody.
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=20), default=UserRole.USER, nullable=False
    )
    status: Mapped[ModuleStatus] = mapped_column(
        Enum(ModuleStatus, native_enum=False, length=20), default=ModuleStatus.AVAILABLE, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<WorkspaceModule {self.code}>"


class UserModuleSetting(StandardColumnsMixin, Base):
    """A user's own settings for one module. Created on first write; no row = defaults."""

    __tablename__ = "user_module_settings"
    __table_args__ = (
        Index("uq_user_module_settings_user_module_active", "user_id", "module_id", unique=True, **soft_delete_where()),
        {"schema": SCHEMA_MASTER},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    module_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("master.modules.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Set by an admin (``PUT /workspace/admin/users/{id}/modules/{code}``), never by the user.
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: ``None`` = the catalog's order.
    sort_order: Mapped[int | None] = mapped_column(Integer)
    last_opened_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    module: Mapped[WorkspaceModule] = relationship(lazy="joined", foreign_keys=lambda: [UserModuleSetting.module_id])


class UserWorkspacePreference(StandardColumnsMixin, Base):
    """Workspace-wide preferences: one live row per user, created on first write."""

    __tablename__ = "user_workspace_preferences"
    __table_args__ = (
        Index("uq_user_workspace_preferences_user_active", "user_id", unique=True, **soft_delete_where()),
        {"schema": SCHEMA_MASTER},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    landing: Mapped[WorkspaceLanding] = mapped_column(
        Enum(WorkspaceLanding, native_enum=False, length=20), default=WorkspaceLanding.LAUNCHER, nullable=False
    )
    last_module_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("master.modules.id", ondelete="SET NULL"))
    show_tips: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


__all__ = ["DEFAULT_MODULES", "UserModuleSetting", "UserWorkspacePreference", "WorkspaceModule"]
