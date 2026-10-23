"""The multi-module workspace: catalog, per-user settings, launcher data and module guards.

Covers ``/api/v1/workspace`` (``app.modules.workspace``) and ``app.core.deps.require_module``
on the module routers (``resume``: resumes, ats; ``apply``: jobs, applications, automation,
interviews, emails, companies, matching, dashboard), the platform-wide admin catalog and the
scheduler's module check.

The fixtures seed every module **enabled** (``tests/conftest.py``); production starts with
``apply`` switched off, which ``test_the_seed_*`` checks against ``DEFAULT_MODULES``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from app.models.workspace import DEFAULT_MODULES, UserModuleSetting, WorkspaceModule
from app.modules.automation import service as automation_service
from app.modules.auth import service as auth_service
from app.modules.workspace import service as workspace_service

API = "/api/v1"
MODULES = f"{API}/workspace/modules"
PREFS = f"{API}/workspace/preferences"
ADMIN = f"{API}/workspace/admin/users"
CATALOG = f"{API}/workspace/admin/modules"


def _bearer(user: User, role: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, role or user.role.value)}"}


@pytest.fixture
def member(db: Session) -> User:
    user = auth_service.create_user(db, "member@example.com", "StrongPass123", "Module Member")
    db.commit()
    return user


@pytest.fixture
def other(db: Session) -> User:
    user = auth_service.create_user(db, "other@example.com", "StrongPass123", "Other Member")
    db.commit()
    return user


@pytest.fixture
def admin(db: Session) -> User:
    user = auth_service.create_user(db, "admin@example.com", "StrongPass123", "Module Admin", role=UserRole.ADMIN)
    db.commit()
    return user


def _codes(body: list[dict]) -> list[str]:
    return [m["code"] for m in body]


def _set_module(db: Session, code: str, **values) -> None:
    db.execute(update(WorkspaceModule).where(WorkspaceModule.code == code).values(**values))
    db.commit()


def _reason(response) -> str:
    return response.json()["error"]["details"]["reason"]


# --------------------------------------------------------------------------- catalog seed


def test_the_seed_starts_with_job_apply_switched_off() -> None:
    rows = {row[0]: row for row in DEFAULT_MODULES}
    assert list(rows) == ["resume", "apply", "insights"]
    # (code, name, tagline, description, icon, home_path, accent, sort_order, is_enabled, status)
    assert rows["resume"][8] is True and rows["resume"][9].value == "AVAILABLE"
    assert rows["apply"][8] is False and rows["apply"][9].value == "AVAILABLE"  # finished, switched off
    assert rows["insights"][9].value == "COMING_SOON" and rows["insights"][5] is None


def test_the_seed_inserts_missing_rows_only_and_never_overwrites(db: Session) -> None:
    db.execute(text('DELETE FROM "master"."modules"'))
    created = workspace_service.ensure_catalog(db)
    db.commit()
    by_code = {m.code: m for m in created}
    assert list(by_code) == ["resume", "apply", "insights"]
    assert by_code["resume"].is_enabled is True
    assert by_code["apply"].is_enabled is False
    assert by_code["insights"].status.value == "COMING_SOON" and by_code["insights"].home_path is None

    # An admin's later decisions survive every re-run of the seed.
    _set_module(db, "apply", is_enabled=True, sort_order=99)
    assert workspace_service.ensure_catalog(db) == []
    db.commit()
    db.expire_all()
    apply = db.scalars(select(WorkspaceModule).where(WorkspaceModule.code == "apply")).one()
    assert apply.is_enabled is True and apply.sort_order == 99

    # A missing code is inserted with its default; the existing rows stay as they are.
    db.execute(text("DELETE FROM \"master\".\"modules\" WHERE code = 'insights'"))
    assert [m.code for m in workspace_service.ensure_catalog(db)] == ["insights"]
    db.commit()
    db.expire_all()
    assert db.scalars(select(WorkspaceModule).where(WorkspaceModule.code == "apply")).one().is_enabled is True


def test_list_modules_default_order_and_availability(client: TestClient, member: User) -> None:
    r = client.get(MODULES, headers=_bearer(member))
    assert r.status_code == 200, r.text
    body = r.json()
    assert _codes(body) == ["resume", "apply", "insights"]
    resume, apply, insights = body
    assert resume["available"] is True and resume["unavailable_reason"] is None
    assert resume["home_path"] == "/resume" and apply["home_path"] == "/dashboard"
    assert resume["icon"] == "FileText" and resume["accent"] == "primary"
    assert insights["available"] is False
    assert insights["unavailable_reason"] == "coming_soon"
    assert insights["status"] == "COMING_SOON"
    assert insights["home_path"] is None
    # No summary unless asked for: the shell polls this list, the launcher asks for numbers.
    assert all(m["summary"] == [] for m in body)
    assert all(m["is_pinned"] is False and m["open_count"] == 0 for m in body)


def test_summary_numbers_come_from_the_module_services(client: TestClient, member: User) -> None:
    r = client.get(MODULES, params={"summary": "true"}, headers=_bearer(member))
    assert r.status_code == 200, r.text
    by_code = {m["code"]: m for m in r.json()}
    resume_keys = [s["key"] for s in by_code["resume"]["summary"]]
    assert resume_keys == ["resumes", "drafts", "latest_ats"]
    ats = by_code["resume"]["summary"][2]
    assert ats["value"] is None and "estimate" in ats["hint"].lower()
    assert [s["key"] for s in by_code["apply"]["summary"]] == ["applied_week", "queued", "replies_week"]
    assert all(s["value"] == 0 for s in by_code["apply"]["summary"])
    assert by_code["insights"]["summary"] == []  # not available: no numbers


def test_unauthenticated_requests_are_401_not_403(client: TestClient) -> None:
    assert client.get(MODULES).status_code == 401
    # The module guard never runs before authentication.
    assert client.get(f"{API}/jobs").status_code == 401
    assert client.get(f"{API}/resumes").status_code == 401


# --------------------------------------------------------------------------- open / pin / order


def test_open_records_last_opened_and_the_last_module(client: TestClient, member: User) -> None:
    headers = _bearer(member)
    first = client.post(f"{MODULES}/resume/open", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["open_count"] == 1 and first.json()["last_opened_at"] is not None
    second = client.post(f"{MODULES}/resume/open", headers=headers)
    assert second.json()["open_count"] == 2

    prefs = client.get(PREFS, headers=headers).json()
    assert prefs["last_module_code"] == "resume"
    assert prefs["last_module_home_path"] == "/resume"
    assert prefs["landing"] == "LAUNCHER"

    client.post(f"{MODULES}/apply/open", headers=headers)
    assert client.get(PREFS, headers=headers).json()["last_module_code"] == "apply"


def test_open_refuses_coming_soon_and_unknown_modules(client: TestClient, member: User) -> None:
    headers = _bearer(member)
    soon = client.post(f"{MODULES}/insights/open", headers=headers)
    assert soon.status_code == 403
    assert soon.json()["error"]["code"] == "module_disabled"
    assert _reason(soon) == "coming_soon"
    assert "Career Insights" in soon.json()["error"]["message"]
    assert client.post(f"{MODULES}/nope/open", headers=headers).status_code == 404


def test_pin_and_reorder_change_the_users_order_only(client: TestClient, member: User, other: User) -> None:
    headers = _bearer(member)
    pinned = client.put(f"{MODULES}/apply", json={"is_pinned": True}, headers=headers)
    assert pinned.status_code == 200 and pinned.json()["is_pinned"] is True
    assert _codes(client.get(MODULES, headers=headers).json()) == ["apply", "resume", "insights"]

    client.put(f"{MODULES}/apply", json={"is_pinned": False}, headers=headers)
    client.put(f"{MODULES}/insights", json={"sort_order": 1}, headers=headers)
    body = client.get(MODULES, headers=headers).json()
    assert _codes(body) == ["insights", "resume", "apply"]
    assert body[0]["sort_order"] == 1

    # Another user's launcher is untouched.
    assert _codes(client.get(MODULES, headers=_bearer(other)).json()) == ["resume", "apply", "insights"]


@pytest.mark.parametrize(
    "payload",
    [{}, {"is_pinned": True, "is_enabled": False}, {"sort_order": -1}, {"sort_order": "first"}],
)
def test_module_update_validation(client: TestClient, member: User, payload: dict) -> None:
    r = client.put(f"{MODULES}/resume", json=payload, headers=_bearer(member))
    assert r.status_code == 422, r.text


def test_users_cannot_switch_a_module_on_for_themselves(client: TestClient, admin: User, member: User) -> None:
    client.put(f"{ADMIN}/{member.id}/modules/apply", json={"is_enabled": False}, headers=_bearer(admin))
    # ``is_enabled`` is not a user field: extra keys are refused outright.
    r = client.put(f"{MODULES}/apply", json={"is_enabled": True}, headers=_bearer(member))
    assert r.status_code == 422
    assert client.get(f"{API}/jobs", headers=_bearer(member)).status_code == 403


# --------------------------------------------------------------------------- preferences


def test_preferences_default_and_update(client: TestClient, member: User) -> None:
    headers = _bearer(member)
    assert client.get(PREFS, headers=headers).json() == {
        "landing": "LAUNCHER",
        "show_tips": True,
        "last_module_code": None,
        "last_module_home_path": None,
    }
    r = client.put(PREFS, json={"landing": "LAST_MODULE", "show_tips": False}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["landing"] == "LAST_MODULE" and r.json()["show_tips"] is False
    assert client.put(PREFS, json={"landing": "SOMEWHERE"}, headers=headers).status_code == 422
    assert client.put(PREFS, json={}, headers=headers).status_code == 422


# --------------------------------------------------------------------------- admin: one user


def test_admin_routes_need_the_active_admin_role(client: TestClient, member: User, admin: User) -> None:
    assert client.get(f"{ADMIN}/{member.id}/modules", headers=_bearer(member)).status_code == 403
    assert (
        client.put(f"{ADMIN}/{member.id}/modules/apply", json={"is_enabled": False}, headers=_bearer(member)).status_code
        == 403
    )
    assert client.get(ADMIN, params={"email": "member@example.com"}, headers=_bearer(member)).status_code == 403
    # An account acting as USER is refused too (here: a role it does not hold -> 401).
    assert client.get(f"{ADMIN}/{member.id}/modules", headers=_bearer(admin, "USER")).status_code in (401, 403)


def test_admin_finds_users_by_exact_email(client: TestClient, member: User, admin: User) -> None:
    r = client.get(ADMIN, params={"email": "  MEMBER@example.com "}, headers=_bearer(admin))
    assert r.status_code == 200, r.text
    assert r.json() == {"id": str(member.id), "email": "member@example.com", "full_name": "Module Member"}
    assert client.get(ADMIN, params={"email": "member@"}, headers=_bearer(admin)).status_code == 404


def test_admin_toggle_disables_the_module_end_to_end(client: TestClient, db: Session, member: User, admin: User) -> None:
    view = client.get(f"{ADMIN}/{member.id}/modules", headers=_bearer(admin))
    assert view.status_code == 200
    assert {m["code"]: m["enabled_for_user"] for m in view.json()["modules"]} == {
        "resume": True,
        "apply": True,
        "insights": True,
    }

    client.post(f"{MODULES}/apply/open", headers=_bearer(member))
    off = client.put(f"{ADMIN}/{member.id}/modules/apply", json={"is_enabled": False}, headers=_bearer(admin))
    assert off.status_code == 200, off.text
    assert {m["code"]: m["enabled_for_user"] for m in off.json()["modules"]}["apply"] is False

    headers = _bearer(member)
    for path in (
        "/jobs",
        "/applications",
        "/dashboard/stats",
        "/companies",
        "/interviews",
        "/emails",
        "/automation/config",
        "/matching/summary",
    ):
        r = client.get(f"{API}{path}", headers=headers)
        assert r.status_code == 403, (path, r.status_code, r.text)
        error = r.json()["error"]
        assert error["code"] == "module_disabled"
        assert "Job Apply" in error["message"]
        assert error["details"] == {"module": "apply", "module_name": "Job Apply", "reason": "disabled_for_user"}
    # The other module, the account pages and the admin's own access are unaffected.
    assert client.get(f"{API}/resumes", headers=headers).status_code == 200
    assert client.get(f"{API}/ats/summary", headers=headers).status_code == 200
    assert client.get(f"{API}/profile", headers=headers).status_code == 200
    assert client.get(f"{API}/notifications", headers=headers).status_code == 200
    assert client.get(f"{API}/jobs", headers=_bearer(admin)).status_code == 200

    listed = {m["code"]: m for m in client.get(MODULES, headers=headers).json()}
    assert listed["apply"]["available"] is False
    assert listed["apply"]["unavailable_reason"] == "disabled_for_user"
    assert client.post(f"{MODULES}/apply/open", headers=headers).status_code == 403
    # The last module is no longer offered as a landing target.
    assert client.get(PREFS, headers=headers).json()["last_module_code"] is None

    logs = list(db.scalars(select(AuditLog).where(AuditLog.action == "workspace.module_toggled")))
    assert len(logs) == 1
    assert logs[0].user_id == member.id
    assert logs[0].meta == {"module": "apply", "is_enabled": False, "admin_id": str(admin.id)}

    # Same value again: no second audit row. Back on: access returns.
    client.put(f"{ADMIN}/{member.id}/modules/apply", json={"is_enabled": False}, headers=_bearer(admin))
    on = client.put(f"{ADMIN}/{member.id}/modules/apply", json={"is_enabled": True}, headers=_bearer(admin))
    assert on.status_code == 200
    assert client.get(f"{API}/jobs", headers=headers).status_code == 200
    db.expire_all()
    assert len(list(db.scalars(select(AuditLog).where(AuditLog.action == "workspace.module_toggled")))) == 2


def test_disabling_resume_guards_resumes_and_ats(client: TestClient, member: User, admin: User) -> None:
    client.put(f"{ADMIN}/{member.id}/modules/resume", json={"is_enabled": False}, headers=_bearer(admin))
    headers = _bearer(member)
    for path in ("/resumes", "/resumes/summary", "/ats/summary", "/ats/targets"):
        r = client.get(f"{API}{path}", headers=headers)
        assert r.status_code == 403, path
        assert "Resume Studio" in r.json()["error"]["message"]
    assert client.get(f"{API}/jobs", headers=headers).status_code == 200


def test_admin_unknown_user_or_module_is_404(client: TestClient, member: User, admin: User) -> None:
    headers = _bearer(admin)
    stranger = uuid.uuid4()
    assert client.get(f"{ADMIN}/{stranger}/modules", headers=headers).status_code == 404
    assert client.put(f"{ADMIN}/{stranger}/modules/apply", json={"is_enabled": False}, headers=headers).status_code == 404
    assert client.put(f"{ADMIN}/{member.id}/modules/nope", json={"is_enabled": False}, headers=headers).status_code == 404
    assert client.put(f"{ADMIN}/{member.id}/modules/apply", json={}, headers=headers).status_code == 422


# --------------------------------------------------------------------------- platform switch / roles / order


def test_a_platform_disabled_module_is_listed_muted_and_refused(client: TestClient, db: Session, member: User) -> None:
    _set_module(db, "resume", is_enabled=False)
    headers = _bearer(member)
    listed = {m["code"]: m for m in client.get(MODULES, params={"summary": "true"}, headers=headers).json()}
    assert list(listed) == ["resume", "apply", "insights"]
    assert listed["resume"]["available"] is False
    assert listed["resume"]["unavailable_reason"] == "platform_disabled"
    assert listed["resume"]["summary"] == []
    r = client.get(f"{API}/resumes", headers=headers)
    assert r.status_code == 403
    assert _reason(r) == "platform_disabled"
    assert "not available right now" in r.json()["error"]["message"]
    assert client.post(f"{MODULES}/resume/open", headers=headers).status_code == 403
    # Still the user's to order and pin, like any visible module.
    assert client.put(f"{MODULES}/resume", json={"is_pinned": True}, headers=headers).status_code == 200


def test_guard_order_is_platform_then_user_then_role(client: TestClient, db: Session, member: User, admin: User) -> None:
    client.put(f"{ADMIN}/{member.id}/modules/apply", json={"is_enabled": False}, headers=_bearer(admin))
    _set_module(db, "apply", min_role="ADMIN")
    assert _reason(client.get(f"{API}/jobs", headers=_bearer(member))) == "disabled_for_user"  # user before role
    _set_module(db, "apply", is_enabled=False)
    assert _reason(client.get(f"{API}/jobs", headers=_bearer(member))) == "platform_disabled"  # platform first


def test_min_role_hides_a_module_from_users_but_not_admins(client: TestClient, db: Session, member: User, admin: User) -> None:
    _set_module(db, "apply", min_role="ADMIN")
    assert _codes(client.get(MODULES, headers=_bearer(member)).json()) == ["resume", "insights"]
    refused = client.get(f"{API}/jobs", headers=_bearer(member))
    assert refused.status_code == 403
    assert _reason(refused) == "role_required"
    assert "apply" in _codes(client.get(MODULES, headers=_bearer(admin)).json())
    assert client.get(f"{API}/jobs", headers=_bearer(admin)).status_code == 200


def test_a_catalog_without_the_code_never_locks_users_out(client: TestClient, db: Session, member: User) -> None:
    db.execute(text("DELETE FROM \"master\".\"modules\" WHERE code = 'apply'"))
    db.commit()
    assert client.get(f"{API}/jobs", headers=_bearer(member)).status_code == 200


def test_a_tombstoned_catalog_row_is_refused(client: TestClient, db: Session, member: User) -> None:
    _set_module(db, "apply", deleted_at=text("now()"), is_active=False)
    r = client.get(f"{API}/jobs", headers=_bearer(member))
    assert r.status_code == 403
    assert _reason(r) == "platform_disabled"
    assert "apply" not in _codes(client.get(MODULES, headers=_bearer(member)).json())


def test_settings_rows_are_scoped_to_their_user(client: TestClient, db: Session, member: User, other: User, admin: User) -> None:
    client.put(f"{ADMIN}/{member.id}/modules/apply", json={"is_enabled": False}, headers=_bearer(admin))
    client.put(f"{MODULES}/resume", json={"is_pinned": True}, headers=_bearer(member))
    assert client.get(f"{API}/jobs", headers=_bearer(other)).status_code == 200
    other_view = {m["code"]: m for m in client.get(MODULES, headers=_bearer(other)).json()}
    assert other_view["apply"]["available"] is True and other_view["resume"]["is_pinned"] is False
    rows = list(db.scalars(select(UserModuleSetting)))
    assert {row.user_id for row in rows} == {member.id}


# --------------------------------------------------------------------------- admin: platform catalog


def test_admin_catalog_needs_admin(client: TestClient, member: User, admin: User) -> None:
    assert client.get(CATALOG, headers=_bearer(member)).status_code == 403
    assert client.put(f"{CATALOG}/apply", json={"is_enabled": False}, headers=_bearer(member)).status_code == 403
    r = client.get(CATALOG, headers=_bearer(admin))
    assert r.status_code == 200
    assert [(m["code"], m["is_enabled"], m["status"]) for m in r.json()] == [
        ("resume", True, "AVAILABLE"),
        ("apply", True, "AVAILABLE"),
        ("insights", True, "COMING_SOON"),
    ]


def test_platform_switch_end_to_end_with_audit(client: TestClient, db: Session, member: User, admin: User) -> None:
    off = client.put(f"{CATALOG}/apply", json={"is_enabled": False}, headers=_bearer(admin))
    assert off.status_code == 200, off.text
    assert off.json()["is_enabled"] is False

    # Everybody, admins included, gets the muted card and a 403 from the API.
    for who in (member, admin):
        listed = {m["code"]: m for m in client.get(MODULES, headers=_bearer(who)).json()}
        assert listed["apply"]["available"] is False
        assert listed["apply"]["unavailable_reason"] == "platform_disabled"
        r = client.get(f"{API}/jobs", headers=_bearer(who))
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "module_disabled"
        assert _reason(r) == "platform_disabled"
    # Manual pipeline triggers go through the automation router: refused too.
    assert client.post(f"{API}/automation/run", json={}, headers=_bearer(member)).status_code == 403

    on = client.put(f"{CATALOG}/apply", json={"is_enabled": True, "sort_order": 5}, headers=_bearer(admin))
    assert on.status_code == 200 and on.json()["sort_order"] == 5
    assert client.get(f"{API}/jobs", headers=_bearer(member)).status_code == 200

    logs = list(
        db.scalars(
            select(AuditLog).where(AuditLog.action == "workspace.module_catalog_updated").order_by(AuditLog.created_at)
        )
    )
    assert [log.meta for log in logs] == [
        {
            "module": "apply",
            "before": {"is_enabled": True, "status": "AVAILABLE", "sort_order": 20},
            "after": {"is_enabled": False, "status": "AVAILABLE", "sort_order": 20},
        },
        {
            "module": "apply",
            "before": {"is_enabled": False, "status": "AVAILABLE", "sort_order": 20},
            "after": {"is_enabled": True, "status": "AVAILABLE", "sort_order": 5},
        },
    ]
    assert all(log.user_id == admin.id for log in logs)

    # A no-op PUT writes no audit row.
    client.put(f"{CATALOG}/apply", json={"is_enabled": True}, headers=_bearer(admin))
    db.expire_all()
    assert len(list(db.scalars(select(AuditLog).where(AuditLog.action == "workspace.module_catalog_updated")))) == 2


def test_catalog_validation(client: TestClient, admin: User) -> None:
    headers = _bearer(admin)
    assert client.put(f"{CATALOG}/apply", json={"is_enabled": False}, headers=headers).status_code == 200

    # resume is now the last module anybody can use.
    last = client.put(f"{CATALOG}/resume", json={"is_enabled": False}, headers=headers)
    assert last.status_code == 409
    assert last.json()["error"]["code"] == "last_enabled_module"
    assert client.put(f"{CATALOG}/resume", json={"status": "COMING_SOON"}, headers=headers).status_code == 409
    assert client.put(f"{CATALOG}/resume", json={"sort_order": 1}, headers=headers).status_code == 200

    # A coming-soon module without a home page cannot be made available.
    no_home = client.put(f"{CATALOG}/insights", json={"status": "AVAILABLE"}, headers=headers)
    assert no_home.status_code == 422
    assert no_home.json()["error"]["code"] == "home_path_required"

    assert client.put(f"{CATALOG}/nope", json={"is_enabled": True}, headers=headers).status_code == 404
    for payload in ({}, {"is_enabled": True, "home_path": "/x"}, {"status": "LATER"}, {"sort_order": -3}):
        assert client.put(f"{CATALOG}/apply", json=payload, headers=headers).status_code == 422, payload


# --------------------------------------------------------------------------- background work


def test_module_available_matches_the_guard(db: Session, member: User, admin: User) -> None:
    assert workspace_service.module_available(db, member.id, "apply") is True
    _set_module(db, "apply", is_enabled=False)
    assert workspace_service.module_available(db, member.id, "apply") is False
    _set_module(db, "apply", is_enabled=True, min_role="ADMIN")
    assert workspace_service.module_available(db, member.id, "apply") is False
    assert workspace_service.module_available(db, admin.id, "apply") is True
    assert workspace_service.module_available(db, uuid.uuid4(), "apply") is False
    assert workspace_service.module_available(db, member.id, "never-seeded") is True


def test_the_scheduler_skips_users_while_job_apply_is_off(db: Session, member: User, admin: User) -> None:
    from app.worker import scheduler

    config = automation_service.get_config(db, member.id)
    config.enabled = True
    config.schedule_time = "09:00"
    config.timezone = "UTC"
    config.last_run_at = None
    db.commit()
    due_at = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
    assert member.id in scheduler.due_users(db, due_at)

    _set_module(db, "apply", is_enabled=False)  # platform-wide
    assert member.id not in scheduler.due_users(db, due_at)

    _set_module(db, "apply", is_enabled=True)
    workspace_service.admin_toggle_module(db, admin, member.id, "apply", is_enabled=False)  # just this user
    db.commit()
    assert member.id not in scheduler.due_users(db, due_at)

    workspace_service.admin_toggle_module(db, admin, member.id, "apply", is_enabled=True)
    db.commit()
    assert member.id in scheduler.due_users(db, due_at)
