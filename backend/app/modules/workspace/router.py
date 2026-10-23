"""Workspace endpoints, mounted at ``/api/v1/workspace`` (``docs/CONTRACTS.md``).

Thin: visibility, ordering, access and the card numbers live in ``service``. Everything a
user reads or writes is their own (``user.id``); the ``/admin`` routes need the active
ADMIN role: ``/admin/modules`` is the platform-wide catalog (switching a module off hides it
for everyone and its API answers ``403 module_disabled``), ``/admin/users/...`` the per-user
switch, with ``404`` for an unknown user.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.modules.workspace import service
from app.modules.workspace.schemas import (
    AdminCatalogModule,
    AdminCatalogUpdate,
    AdminModuleToggle,
    AdminUserModules,
    AdminUserRef,
    ModuleRead,
    ModuleUpdate,
    PreferencesRead,
    PreferencesUpdate,
)

router = APIRouter()


@router.get("/modules", response_model=list[ModuleRead], summary="Your modules, in your order")
def list_modules(
    summary: bool = Query(False, description="Include the launcher card numbers (slower)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ModuleRead]:
    return service.list_modules(db, user, include_summary=summary)


@router.post("/modules/{code}/open", response_model=ModuleRead, summary="Record that you opened a module")
def open_module(code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ModuleRead:
    return service.open_module(db, user, code)


@router.put("/modules/{code}", response_model=ModuleRead, summary="Pin or reorder one of your modules")
def update_module(
    code: str,
    payload: ModuleUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ModuleRead:
    return service.update_module(db, user, code, payload)


@router.get("/preferences", response_model=PreferencesRead, summary="Your workspace preferences")
def get_preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> PreferencesRead:
    return service.get_preferences(db, user)


@router.put("/preferences", response_model=PreferencesRead, summary="Change where you land after sign-in, tips")
def update_preferences(
    payload: PreferencesUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PreferencesRead:
    return service.update_preferences(db, user, payload)


# --------------------------------------------------------------------------- admin: platform catalog


@router.get("/admin/modules", response_model=list[AdminCatalogModule], summary="Admin: the module catalog")
def admin_catalog(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[AdminCatalogModule]:
    return service.admin_catalog(db)


@router.put(
    "/admin/modules/{code}",
    response_model=AdminCatalogModule,
    summary="Admin: switch a module on or off for everyone, change its status or order",
)
def admin_update_catalog(
    code: str,
    payload: AdminCatalogUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminCatalogModule:
    return service.admin_update_catalog(db, admin, code, payload)


# --------------------------------------------------------------------------- admin: one user


@router.get("/admin/users", response_model=AdminUserRef, summary="Admin: find an account by exact email")
def admin_find_user(
    email: str = Query(..., min_length=3, max_length=255),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserRef:
    return service.find_user_by_email(db, email)


@router.get("/admin/users/{user_id}/modules", response_model=AdminUserModules, summary="Admin: a user's modules")
def admin_user_modules(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserModules:
    return service.admin_user_modules(db, user_id)


@router.put(
    "/admin/users/{user_id}/modules/{code}",
    response_model=AdminUserModules,
    summary="Admin: turn a module on or off for one user",
)
def admin_toggle_module(
    user_id: uuid.UUID,
    code: str,
    payload: AdminModuleToggle,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserModules:
    return service.admin_toggle_module(db, admin, user_id, code, is_enabled=payload.is_enabled)
