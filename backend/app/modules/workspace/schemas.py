"""Workspace schemas (``/api/v1/workspace``, see ``docs/CONTRACTS.md``)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ModuleStatus, UserRole, WorkspaceLanding

#: Why a visible module cannot be opened, in the order the guard checks them:
#: ``platform_disabled`` (an admin switched it off for everybody), ``coming_soon``,
#: ``disabled_for_user`` (an admin switched it off for this account). A module above the
#: session's role is not returned at all; its API answers ``role_required``.
UnavailableReason = Literal["platform_disabled", "coming_soon", "disabled_for_user"]

#: ``details.reason`` of a ``403 module_disabled``.
RefusalReason = Literal["platform_disabled", "coming_soon", "disabled_for_user", "role_required"]


class ModuleStat(BaseModel):
    """One live number on a launcher card. ``value`` is ``None`` when there is nothing to
    show yet (rendered as a dash)."""

    key: str
    label: str
    value: int | None = None
    unit: str | None = None
    hint: str | None = None


class ModuleRead(BaseModel):
    code: str
    name: str
    tagline: str
    description: str | None = None
    icon: str
    #: ``None`` for a module with no pages yet.
    home_path: str | None = None
    accent: str
    status: ModuleStatus
    min_role: UserRole
    #: Enabled platform-wide, ``AVAILABLE``, enabled for this user and role allowed.
    available: bool
    unavailable_reason: UnavailableReason | None = None
    is_pinned: bool = False
    #: The effective position (the user's own order, else the catalog's).
    sort_order: int
    last_opened_at: datetime | None = None
    open_count: int = 0
    #: Card numbers, only when asked for (``?summary=true``) and only for available modules.
    summary: list[ModuleStat] = Field(default_factory=list)


class ModuleUpdate(BaseModel):
    """``PUT /workspace/modules/{code}`` — the user's own pin and order."""

    model_config = ConfigDict(extra="forbid")

    is_pinned: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)

    @model_validator(mode="after")
    def _something(self) -> ModuleUpdate:
        if self.is_pinned is None and self.sort_order is None:
            raise ValueError("Send is_pinned and/or sort_order")
        return self


class PreferencesRead(BaseModel):
    landing: WorkspaceLanding = WorkspaceLanding.LAUNCHER
    show_tips: bool = True
    #: The module opened last, only while the user can still open it.
    last_module_code: str | None = None
    last_module_home_path: str | None = None


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    landing: WorkspaceLanding | None = None
    show_tips: bool | None = None

    @model_validator(mode="after")
    def _something(self) -> PreferencesUpdate:
        if self.landing is None and self.show_tips is None:
            raise ValueError("Send landing and/or show_tips")
        return self


class AdminUserRef(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str


class AdminModuleState(BaseModel):
    code: str
    name: str
    status: ModuleStatus
    min_role: UserRole
    #: The platform-wide switch.
    platform_enabled: bool
    #: The per-user switch an admin controls.
    enabled_for_user: bool


class AdminUserModules(BaseModel):
    user: AdminUserRef
    modules: list[AdminModuleState] = Field(default_factory=list)


class AdminModuleToggle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_enabled: bool


class AdminCatalogModule(BaseModel):
    """One catalog row as the platform admin sees it (``GET /workspace/admin/modules``)."""

    code: str
    name: str
    tagline: str
    icon: str
    home_path: str | None = None
    status: ModuleStatus
    min_role: UserRole
    #: The platform-wide switch: off hides the module's pages for everyone and its API
    #: answers ``403 module_disabled``.
    is_enabled: bool
    sort_order: int


class AdminCatalogUpdate(BaseModel):
    """``PUT /workspace/admin/modules/{code}`` — the platform-wide switch, status, order."""

    model_config = ConfigDict(extra="forbid")

    is_enabled: bool | None = None
    status: ModuleStatus | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)

    @model_validator(mode="after")
    def _something(self) -> AdminCatalogUpdate:
        if self.is_enabled is None and self.status is None and self.sort_order is None:
            raise ValueError("Send is_enabled, status and/or sort_order")
        return self


__all__ = [
    "AdminCatalogModule",
    "AdminCatalogUpdate",
    "AdminModuleState",
    "AdminModuleToggle",
    "AdminUserModules",
    "AdminUserRef",
    "ModuleRead",
    "ModuleStat",
    "ModuleUpdate",
    "PreferencesRead",
    "PreferencesUpdate",
    "RefusalReason",
    "UnavailableReason",
]
