"""Workspace logic: which modules a user sees, in what order, and whether they may open one.

One rule set, used by the launcher, the switcher, the API guard and the scheduler. A module
is **unavailable** for the first of these reasons that applies, checked in this order:

1. ``platform_disabled`` — the catalog row is switched off (``is_enabled = False``), or is
   inactive / tombstoned: an admin turned the module off for everybody;
2. ``coming_soon`` — the module is not finished (``status = COMING_SOON``);
3. ``disabled_for_user`` — an admin turned it off for this account;
4. ``role_required`` — the module's ``min_role`` is above the session's **active** role.

What the user *sees* (``GET /workspace/modules``): every active catalog row except those
above their role (a USER is not told that admin-only modules exist). Platform-disabled,
coming-soon and per-user-disabled modules are listed with ``available = false`` and the
reason, so the launcher can show a muted card instead of things silently vanishing.

:func:`ensure_module_access` backs ``app.core.deps.require_module``: any reason answers
``403 module_disabled``. A code the catalog has never heard of (a database the catalog was
never seeded into) is allowed, so a missing seed can never lock everybody out; a tombstoned
row is refused. :func:`module_available` is the same check for background work.

Per-user rows (:class:`UserModuleSetting`, :class:`UserWorkspacePreference`) are created on
first write only; no row means the defaults. Services never commit (``get_db`` does).
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from app.models.base import utcnow
from app.models.enums import Actor, ModuleStatus, UserRole, WorkspaceLanding
from app.models.user import User
from app.models.workspace import DEFAULT_MODULES, UserModuleSetting, UserWorkspacePreference, WorkspaceModule
from app.modules.workspace.schemas import (
    AdminCatalogModule,
    AdminCatalogUpdate,
    AdminModuleState,
    AdminUserModules,
    AdminUserRef,
    ModuleRead,
    ModuleStat,
    ModuleUpdate,
    PreferencesRead,
    PreferencesUpdate,
)

logger = logging.getLogger(__name__)

MODULE_DISABLED = "module_disabled"

PLATFORM_DISABLED = "platform_disabled"
COMING_SOON = "coming_soon"
DISABLED_FOR_USER = "disabled_for_user"
ROLE_REQUIRED = "role_required"


# --------------------------------------------------------------------------- catalog


def ensure_catalog(db: Session) -> list[WorkspaceModule]:
    """Insert any row of :data:`DEFAULT_MODULES` whose code is missing (idempotent).

    **Inserts only.** An existing row — including a tombstoned one — is never touched, so an
    admin's later change to ``is_enabled`` / ``status`` / ``sort_order`` survives every
    re-run. Production gets the rows from migration ``f6b8d0c2e4a7``; this serves the paths
    that build the schema from ``Base.metadata`` (the seed).
    """
    existing = {m.code for m in db.scalars(select(WorkspaceModule).execution_options(include_deleted=True))}
    created: list[WorkspaceModule] = []
    for code, name, tagline, description, icon, home_path, accent, sort_order, is_enabled, status in DEFAULT_MODULES:
        if code in existing:
            continue
        module = WorkspaceModule(
            code=code,
            name=name,
            tagline=tagline,
            description=description,
            icon=icon,
            home_path=home_path,
            accent=accent,
            sort_order=sort_order,
            is_enabled=is_enabled,
            min_role=UserRole.USER,
            status=status,
        )
        db.add(module)
        created.append(module)
    if created:
        db.flush()
    return created


def _catalog(db: Session) -> list[WorkspaceModule]:
    """Every live catalog row (the global filter hides tombstones), in catalog order."""
    return list(db.scalars(select(WorkspaceModule).order_by(WorkspaceModule.sort_order, WorkspaceModule.code)))


def _catalog_row(db: Session, code: str) -> WorkspaceModule | None:
    """The row for ``code`` *including* a tombstone; the live row wins over a tombstone."""
    return db.scalars(
        select(WorkspaceModule)
        .where(WorkspaceModule.code == code)
        .order_by(WorkspaceModule.deleted_at.desc().nulls_first())
        .execution_options(include_deleted=True)
    ).first()


def _session_role(user: User) -> str:
    from app.core.deps import active_role_of

    return active_role_of(user)


def _role_allows(module: WorkspaceModule, role: str) -> bool:
    required = module.min_role.value if hasattr(module.min_role, "value") else str(module.min_role)
    if required == UserRole.ADMIN.value:
        return role == UserRole.ADMIN.value
    return True


def unavailable_reason(module: WorkspaceModule, setting: UserModuleSetting | None, role: str) -> str | None:
    """The first reason ``module`` cannot be used, in the documented order, else ``None``."""
    if module.deleted_at is not None or not module.is_active or not module.is_enabled:
        return PLATFORM_DISABLED
    if module.status != ModuleStatus.AVAILABLE:
        return COMING_SOON
    if setting is not None and not setting.is_enabled:
        return DISABLED_FOR_USER
    if not _role_allows(module, role):
        return ROLE_REQUIRED
    return None


# --------------------------------------------------------------------------- per-user state


@dataclass
class ModuleState:
    module: WorkspaceModule
    setting: UserModuleSetting | None
    role: str

    @property
    def unavailable_reason(self) -> str | None:
        return unavailable_reason(self.module, self.setting, self.role)

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    @property
    def is_pinned(self) -> bool:
        return bool(self.setting and self.setting.is_pinned)

    @property
    def sort_order(self) -> int:
        if self.setting is not None and self.setting.sort_order is not None:
            return int(self.setting.sort_order)
        return int(self.module.sort_order)


def _settings_by_module(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, UserModuleSetting]:
    rows = db.scalars(select(UserModuleSetting).where(UserModuleSetting.user_id == user_id))
    return {row.module_id: row for row in rows}


def module_states(db: Session, user: User) -> list[ModuleState]:
    """The user's visible modules: pinned first, then the user's order, then the catalog's."""
    role = _session_role(user)
    settings = _settings_by_module(db, user.id)
    states = [
        ModuleState(m, settings.get(m.id), role) for m in _catalog(db) if m.is_active and _role_allows(m, role)
    ]
    states.sort(key=lambda s: (not s.is_pinned, s.sort_order, s.module.sort_order, s.module.code))
    return states


def _visible_state(db: Session, user: User, code: str) -> ModuleState:
    """The visible module ``code`` for this user, else ``404`` (hidden reads as unknown)."""
    for state in module_states(db, user):
        if state.module.code == code:
            return state
    raise NotFoundError("Module not found", code="module_not_found")


def _get_or_create_setting(db: Session, user_id: uuid.UUID, module_id: uuid.UUID) -> UserModuleSetting:
    stmt = select(UserModuleSetting).where(UserModuleSetting.user_id == user_id, UserModuleSetting.module_id == module_id)
    setting = db.scalars(stmt).first()
    if setting is not None:
        return setting
    try:
        with db.begin_nested():
            setting = UserModuleSetting(user_id=user_id, module_id=module_id, is_enabled=True, is_pinned=False, open_count=0)
            db.add(setting)
            db.flush()
    except IntegrityError:  # a concurrent request created it first (partial unique index)
        setting = db.scalars(stmt).one()
    return setting


def _get_preferences(db: Session, user_id: uuid.UUID) -> UserWorkspacePreference | None:
    return db.scalars(select(UserWorkspacePreference).where(UserWorkspacePreference.user_id == user_id)).first()


def _get_or_create_preferences(db: Session, user_id: uuid.UUID) -> UserWorkspacePreference:
    prefs = _get_preferences(db, user_id)
    if prefs is not None:
        return prefs
    try:
        with db.begin_nested():
            prefs = UserWorkspacePreference(user_id=user_id, landing=WorkspaceLanding.LAUNCHER, show_tips=True)
            db.add(prefs)
            db.flush()
    except IntegrityError:
        prefs = _get_preferences(db, user_id)
        assert prefs is not None
    return prefs


# --------------------------------------------------------------------------- access guard


def _refusal_message(module: WorkspaceModule, reason: str) -> str:
    if reason == PLATFORM_DISABLED:
        return f"{module.name} is not available right now."
    if reason == COMING_SOON:
        return f"{module.name} is not available yet."
    if reason == DISABLED_FOR_USER:
        return f"{module.name} is turned off for your account. Ask an administrator to turn it back on."
    return f"{module.name} needs the Admin role."


def _refuse(module: WorkspaceModule, reason: str) -> ForbiddenError:
    return ForbiddenError(
        _refusal_message(module, reason),
        code=MODULE_DISABLED,
        details={"module": module.code, "module_name": module.name, "reason": reason},
    )


def _access_reason(db: Session, user_id: uuid.UUID, role: str, code: str) -> tuple[WorkspaceModule | None, str | None]:
    module = _catalog_row(db, code)
    if module is None:
        return None, None  # never seeded with this code: nothing can have switched it off
    setting = db.scalars(
        select(UserModuleSetting).where(UserModuleSetting.user_id == user_id, UserModuleSetting.module_id == module.id)
    ).first()
    return module, unavailable_reason(module, setting, role)


def ensure_module_access(db: Session, user: User, code: str) -> None:
    """Raise ``403 module_disabled`` unless ``user`` may use module ``code`` right now."""
    module, reason = _access_reason(db, user.id, _session_role(user), code)
    if module is not None and reason is not None:
        raise _refuse(module, reason)


def module_available(db: Session, user_id: uuid.UUID, code: str) -> bool:
    """Whether ``user_id`` may use module ``code`` — the API guard's rule, for background
    work (the scheduler). There is no session, so the role is the highest one held."""
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return False
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    _, reason = _access_reason(db, user.id, role, code)
    return reason is None


# --------------------------------------------------------------------------- summaries


def _resume_summary(db: Session, user_id: uuid.UUID) -> list[ModuleStat]:
    from app.modules.ats import service as ats_service
    from app.modules.resumes import service as resume_service

    resumes = resume_service.summary(db, user_id)
    latest = next((a for a in ats_service.list_analyses(db, user_id, limit=5) if a.overall_score is not None), None)
    return [
        ModuleStat(key="resumes", label="Resumes", value=resumes.total),
        ModuleStat(key="drafts", label="Unsaved drafts", value=resumes.drafts_pending),
        ModuleStat(
            key="latest_ats",
            label="Latest ATS estimate",
            value=latest.overall_score if latest else None,
            unit="/100",
            hint="An estimate of how an ATS may read your resume, not a promise of a shortlist.",
        ),
    ]


def _apply_summary(db: Session, user_id: uuid.UUID) -> list[ModuleStat]:
    from app.modules.dashboard.service import build_stats

    stats = build_stats(db, user_id)
    return [
        ModuleStat(key="applied_week", label="Applied this week", value=stats.week.applications),
        ModuleStat(key="queued", label="In the queue", value=stats.totals.queued),
        ModuleStat(key="replies_week", label="Replies this week", value=stats.week.responses),
    ]


#: Card numbers per module code. Each one calls the owning module's service; nothing here
#: re-implements a query.
SUMMARIES: dict[str, Callable[[Session, uuid.UUID], list[ModuleStat]]] = {
    "resume": _resume_summary,
    "apply": _apply_summary,
}


def _summary(db: Session, user_id: uuid.UUID, code: str) -> list[ModuleStat]:
    builder = SUMMARIES.get(code)
    if builder is None:
        return []
    try:
        with db.begin_nested():  # a failing stats service must not poison the request
            return builder(db, user_id)
    except Exception:  # pragma: no cover - defensive: the launcher still renders
        logger.exception("Workspace summary for module %s failed", code)
        return []


# --------------------------------------------------------------------------- reads


def _to_read(state: ModuleState, *, summary: list[ModuleStat] | None = None) -> ModuleRead:
    module, setting = state.module, state.setting
    return ModuleRead(
        code=module.code,
        name=module.name,
        tagline=module.tagline,
        description=module.description,
        icon=module.icon,
        home_path=module.home_path,
        accent=module.accent,
        status=module.status,
        min_role=module.min_role,
        available=state.available,
        unavailable_reason=state.unavailable_reason,  # type: ignore[arg-type]  # role-blocked rows are never listed
        is_pinned=state.is_pinned,
        sort_order=state.sort_order,
        last_opened_at=setting.last_opened_at if setting else None,
        open_count=int(setting.open_count) if setting else 0,
        summary=summary or [],
    )


def list_modules(db: Session, user: User, *, include_summary: bool = False) -> list[ModuleRead]:
    return [
        _to_read(
            state,
            summary=_summary(db, user.id, state.module.code) if include_summary and state.available else None,
        )
        for state in module_states(db, user)
    ]


def open_module(db: Session, user: User, code: str) -> ModuleRead:
    """Record that the user opened ``code``: last opened, open count, last module."""
    state = _visible_state(db, user, code)
    reason = state.unavailable_reason
    if reason is not None:
        raise _refuse(state.module, reason)
    setting = _get_or_create_setting(db, user.id, state.module.id)
    setting.last_opened_at = utcnow()
    setting.open_count = int(setting.open_count or 0) + 1
    prefs = _get_or_create_preferences(db, user.id)
    prefs.last_module_id = state.module.id
    db.flush()
    return _to_read(ModuleState(state.module, setting, state.role))


def update_module(db: Session, user: User, code: str, payload: ModuleUpdate) -> ModuleRead:
    """The user's own pin / order. Works on any visible module, available or not."""
    state = _visible_state(db, user, code)
    setting = _get_or_create_setting(db, user.id, state.module.id)
    if payload.is_pinned is not None:
        setting.is_pinned = payload.is_pinned
    if payload.sort_order is not None:
        setting.sort_order = payload.sort_order
    db.flush()
    return _to_read(ModuleState(state.module, setting, state.role))


def get_preferences(db: Session, user: User) -> PreferencesRead:
    prefs = _get_preferences(db, user.id)
    if prefs is None:
        return PreferencesRead()
    last_code: str | None = None
    last_home: str | None = None
    if prefs.last_module_id is not None:
        for state in module_states(db, user):
            if state.module.id == prefs.last_module_id and state.available:
                last_code, last_home = state.module.code, state.module.home_path
                break
    return PreferencesRead(
        landing=prefs.landing, show_tips=prefs.show_tips, last_module_code=last_code, last_module_home_path=last_home
    )


def update_preferences(db: Session, user: User, payload: PreferencesUpdate) -> PreferencesRead:
    prefs = _get_or_create_preferences(db, user.id)
    if payload.landing is not None:
        prefs.landing = payload.landing
    if payload.show_tips is not None:
        prefs.show_tips = payload.show_tips
    db.flush()
    return get_preferences(db, user)


# --------------------------------------------------------------------------- admin: one user


def _target_user(db: Session, user_id: uuid.UUID) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found", code="user_not_found")
    return target


def _admin_view(db: Session, target: User) -> AdminUserModules:
    settings = _settings_by_module(db, target.id)
    modules = [
        AdminModuleState(
            code=m.code,
            name=m.name,
            status=m.status,
            min_role=m.min_role,
            platform_enabled=bool(m.is_active and m.is_enabled),
            enabled_for_user=bool(settings[m.id].is_enabled) if m.id in settings else True,
        )
        for m in _catalog(db)
    ]
    return AdminUserModules(user=AdminUserRef(id=target.id, email=target.email, full_name=target.full_name), modules=modules)


def find_user_by_email(db: Session, email: str) -> AdminUserRef:
    wanted = email.strip().lower()
    target = db.scalars(select(User).where(func.lower(User.email) == wanted)).first() if wanted else None
    if target is None:
        raise NotFoundError("No account with that email", code="user_not_found")
    return AdminUserRef(id=target.id, email=target.email, full_name=target.full_name)


def admin_user_modules(db: Session, user_id: uuid.UUID) -> AdminUserModules:
    return _admin_view(db, _target_user(db, user_id))


def admin_toggle_module(db: Session, admin: User, user_id: uuid.UUID, code: str, *, is_enabled: bool) -> AdminUserModules:
    target = _target_user(db, user_id)
    module = db.scalars(select(WorkspaceModule).where(WorkspaceModule.code == code)).first()
    if module is None:
        raise NotFoundError("Module not found", code="module_not_found")
    setting = _get_or_create_setting(db, target.id, module.id)
    changed = bool(setting.is_enabled) != is_enabled
    setting.is_enabled = is_enabled
    db.flush()
    if changed:
        audit(
            db,
            action="workspace.module_toggled",
            message=f"{module.name} {'enabled' if is_enabled else 'disabled'} for {target.email} by an administrator",
            user_id=target.id,
            actor=Actor.USER,
            meta={"module": module.code, "is_enabled": is_enabled, "admin_id": str(admin.id)},
        )
    return _admin_view(db, target)


# --------------------------------------------------------------------------- admin: platform catalog


def _catalog_read(module: WorkspaceModule) -> AdminCatalogModule:
    return AdminCatalogModule(
        code=module.code,
        name=module.name,
        tagline=module.tagline,
        icon=module.icon,
        home_path=module.home_path,
        status=module.status,
        min_role=module.min_role,
        is_enabled=bool(module.is_enabled),
        sort_order=int(module.sort_order),
    )


def _usable(is_active: bool, is_enabled: bool, status: ModuleStatus) -> bool:
    """Can anybody use this module at all (ignoring per-user switches and roles)?"""
    return is_active and is_enabled and status == ModuleStatus.AVAILABLE


def admin_catalog(db: Session) -> list[AdminCatalogModule]:
    return [_catalog_read(m) for m in _catalog(db)]


def admin_update_catalog(db: Session, admin: User, code: str, payload: AdminCatalogUpdate) -> AdminCatalogModule:
    """Platform-wide switch / status / order of one module, validated and audited.

    * the last usable module (enabled and ``AVAILABLE``) cannot be switched off or made
      ``COMING_SOON``: ``409 last_enabled_module``;
    * a module cannot become usable without a ``home_path`` to open: ``422 home_path_required``.
    """
    module = db.scalars(select(WorkspaceModule).where(WorkspaceModule.code == code)).first()
    if module is None:
        raise NotFoundError("Module not found", code="module_not_found")

    before = {"is_enabled": bool(module.is_enabled), "status": module.status.value, "sort_order": int(module.sort_order)}
    is_enabled = before["is_enabled"] if payload.is_enabled is None else payload.is_enabled
    status = module.status if payload.status is None else payload.status
    sort_order = before["sort_order"] if payload.sort_order is None else payload.sort_order

    if _usable(module.is_active, is_enabled, status) and not module.home_path:
        raise ValidationFailed(
            f"{module.name} has no home page yet, so it cannot be made available.", code="home_path_required"
        )
    if _usable(module.is_active, before["is_enabled"], module.status) and not _usable(module.is_active, is_enabled, status):
        others = [m for m in _catalog(db) if m.id != module.id and _usable(m.is_active, m.is_enabled, m.status)]
        if not others:
            raise ConflictError(
                f"{module.name} is the last module anybody can use; enable another one first.",
                code="last_enabled_module",
            )

    module.is_enabled = is_enabled
    module.status = status
    module.sort_order = sort_order
    db.flush()
    after = {"is_enabled": bool(is_enabled), "status": status.value, "sort_order": int(sort_order)}
    if after != before:
        changes = ", ".join(f"{key} {before[key]} -> {after[key]}" for key in after if after[key] != before[key])
        audit(
            db,
            action="workspace.module_catalog_updated",
            message=f"{module.name}: {changes} (platform-wide)",
            user_id=admin.id,
            actor=Actor.USER,
            meta={"module": module.code, "before": before, "after": after},
        )
    return _catalog_read(module)


__all__ = [
    "COMING_SOON",
    "DISABLED_FOR_USER",
    "MODULE_DISABLED",
    "PLATFORM_DISABLED",
    "ROLE_REQUIRED",
    "SUMMARIES",
    "admin_catalog",
    "admin_toggle_module",
    "admin_update_catalog",
    "admin_user_modules",
    "ensure_catalog",
    "ensure_module_access",
    "find_user_by_email",
    "get_preferences",
    "list_modules",
    "module_available",
    "module_states",
    "open_module",
    "unavailable_reason",
    "update_module",
    "update_preferences",
]
