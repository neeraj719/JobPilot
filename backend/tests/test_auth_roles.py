"""Active role: choose a role at sign-in, switch later, and have every guard honour it.

A user can hold several roles (rows in ``master.user_roles``). The access token's
``role`` claim is the role the session *acts as*; these tests pin down how it is chosen,
switched, carried across refresh, and enforced.
"""
from __future__ import annotations

import time
import uuid

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import require_admin
from app.core.exceptions import register_exception_handlers
from app.core.security import create_access_token, create_role_selection_token, hash_token, refresh_token_expiry
from app.models.audit import AuditLog
from app.models.base import utcnow
from app.models.user import RefreshToken, User
from app.modules.auth import service

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
SELECT = "/api/v1/auth/select-role"
SWITCH = "/api/v1/auth/switch-role"
REFRESH = "/api/v1/auth/refresh"
ME = "/api/v1/auth/me"

CREDENTIALS = {"email": "owner@example.com", "password": "StrongPass123", "full_name": "Owner Person"}
LOGIN_BODY = {"email": CREDENTIALS["email"], "password": CREDENTIALS["password"]}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.core.rate_limit import rate_limiter

    hits = getattr(rate_limiter._backend, "_hits", None)
    if hits is not None:
        hits.clear()
    yield


# --------------------------------------------------------------------------- helpers


def _user(db: Session) -> User:
    db.expire_all()
    return db.scalars(select(User).where(User.email == CREDENTIALS["email"])).one()


def _register(client: TestClient, *, admin: bool, db: Session) -> User:
    response = client.post(REGISTER, json=CREDENTIALS)
    assert response.status_code == 201, response.text
    client.cookies.clear()
    user = _user(db)
    if admin:
        service.assign_role(db, user, "ADMIN")
        db.commit()
    return _user(db)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _claims(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def _sign_in_as(client: TestClient, role: str) -> dict:
    challenge = client.post(LOGIN, json=LOGIN_BODY)
    assert challenge.status_code == 200, challenge.text
    chosen = client.post(SELECT, json={"selection_token": challenge.json()["selection_token"], "role": role})
    assert chosen.status_code == 200, chosen.text
    return chosen.json()


def _audit_actions(db: Session, user: User) -> list[str]:
    return list(db.scalars(select(AuditLog.action).where(AuditLog.user_id == user.id)))


# --------------------------------------------------------------------------- login


def test_single_role_login_is_unchanged(client: TestClient, db: Session) -> None:
    _register(client, admin=False, db=db)

    response = client.post(LOGIN, json=LOGIN_BODY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requires_role_selection"] is False
    assert body["access_token"] and body["token_type"] == "bearer" and body["expires_in"] > 0
    assert body["active_role"] == "USER"
    assert body["available_roles"] == ["USER"]
    assert body["user"]["role"] == "USER"
    assert body["user"]["active_role"] == "USER"
    assert "refresh_token=" in response.headers.get("set-cookie", "")
    assert _claims(body["access_token"])["role"] == "USER"


def test_register_of_a_new_account_returns_tokens_with_the_active_role(client: TestClient) -> None:
    response = client.post(REGISTER, json=CREDENTIALS)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["requires_role_selection"] is False
    assert body["active_role"] == "USER" and body["available_roles"] == ["USER"]
    assert "refresh_token" in client.cookies


def test_multi_role_login_asks_for_a_role_and_sets_no_cookie(client: TestClient, db: Session) -> None:
    _register(client, admin=True, db=db)

    response = client.post(LOGIN, json=LOGIN_BODY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requires_role_selection"] is True
    assert body["available_roles"] == ["ADMIN", "USER"]
    assert body["selection_token"]
    assert "access_token" not in body
    assert body["user"]["email"] == CREDENTIALS["email"]
    assert sorted(body["user"]["roles"]) == ["ADMIN", "USER"]
    assert "set-cookie" not in response.headers
    assert "refresh_token" not in client.cookies

    claims = _claims(body["selection_token"])
    assert claims["type"] == "role_selection"
    assert claims["exp"] - claims["iat"] == service.ROLE_SELECTION_TTL_SECONDS
    # The selection token is not an access token and cannot call the API.
    assert client.get(ME, headers=_bearer(body["selection_token"])).status_code == 401


# --------------------------------------------------------------------------- select-role


def test_select_role_issues_a_session_acting_as_that_role(client: TestClient, db: Session) -> None:
    user = _register(client, admin=True, db=db)
    challenge = client.post(LOGIN, json=LOGIN_BODY).json()

    response = client.post(SELECT, json={"selection_token": challenge["selection_token"], "role": "USER", "remember": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_role"] == "USER"
    assert body["available_roles"] == ["ADMIN", "USER"]
    assert _claims(body["access_token"])["role"] == "USER"
    cookie_header = response.headers.get("set-cookie", "")
    assert "refresh_token=" in cookie_header and "HttpOnly" in cookie_header and "Path=/api/v1/auth" in cookie_header

    me = client.get(ME, headers=_bearer(body["access_token"])).json()
    assert me["active_role"] == "USER"
    assert me["role"] == "ADMIN"  # still the most privileged role *held*
    assert me["roles"] == ["ADMIN", "USER"]

    entry = db.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "auth.role_selected")).one()
    assert entry.meta["role"] == "USER" and entry.meta["remember"] is True

    # Single use: the same selection token cannot mint a second session.
    replay = client.post(SELECT, json={"selection_token": challenge["selection_token"], "role": "ADMIN"})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "selection_token_used"


def test_select_role_refuses_a_role_that_was_not_offered(client: TestClient, db: Session) -> None:
    _register(client, admin=True, db=db)
    token = client.post(LOGIN, json=LOGIN_BODY).json()["selection_token"]

    response = client.post(SELECT, json={"selection_token": token, "role": "SUPERUSER"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_not_held"
    assert "refresh_token" not in client.cookies

    # A refused attempt does not burn the token.
    assert client.post(SELECT, json={"selection_token": token, "role": "ADMIN"}).status_code == 200


def test_select_role_refuses_an_expired_or_foreign_token(client: TestClient, db: Session) -> None:
    user = _register(client, admin=True, db=db)

    expired = create_role_selection_token(user.id, ["ADMIN", "USER"], ttl_seconds=-30)
    response = client.post(SELECT, json={"selection_token": expired, "role": "USER"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "selection_token_expired"

    access = create_access_token(user.id, "ADMIN")
    response = client.post(SELECT, json={"selection_token": access, "role": "ADMIN"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_selection_token"


def test_select_role_refuses_a_role_revoked_after_the_password_step(client: TestClient, db: Session) -> None:
    user = _register(client, admin=True, db=db)
    token = client.post(LOGIN, json=LOGIN_BODY).json()["selection_token"]

    service.revoke_role(db, user, "ADMIN")
    db.commit()

    response = client.post(SELECT, json={"selection_token": token, "role": "ADMIN"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_not_held"


# --------------------------------------------------------------------------- switch-role


def test_switch_role_rotates_the_session_into_the_new_role(client: TestClient, db: Session) -> None:
    user = _register(client, admin=True, db=db)
    first = _sign_in_as(client, "USER")
    first_cookie = client.cookies.get("refresh_token")

    response = client.post(SWITCH, json={"role": "ADMIN"}, headers=_bearer(first["access_token"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_role"] == "ADMIN"
    assert _claims(body["access_token"])["role"] == "ADMIN"
    second_cookie = client.cookies.get("refresh_token")
    assert second_cookie and second_cookie != first_cookie

    assert client.get(ME, headers=_bearer(body["access_token"])).json()["active_role"] == "ADMIN"

    old_row = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == hash_token(first_cookie))).one()
    assert old_row.revoked_at is not None and old_row.replaced_by_hash == hash_token(second_cookie)

    entry = db.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "auth.role_switched")).one()
    assert entry.meta == {"from": "USER", "to": "ADMIN"}


def test_switch_role_to_a_role_not_held_is_403(client: TestClient, db: Session) -> None:
    _register(client, admin=False, db=db)
    token = client.post(LOGIN, json=LOGIN_BODY).json()["access_token"]

    response = client.post(SWITCH, json={"role": "ADMIN"}, headers=_bearer(token))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_not_held"


def test_switch_to_the_current_role_is_a_no_op(client: TestClient, db: Session) -> None:
    user = _register(client, admin=True, db=db)
    session = _sign_in_as(client, "USER")
    cookie = client.cookies.get("refresh_token")

    response = client.post(SWITCH, json={"role": "USER"}, headers=_bearer(session["access_token"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_role"] == "USER"
    assert body["access_token"] == session["access_token"]
    assert 0 < body["expires_in"] <= settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert "set-cookie" not in response.headers
    assert client.cookies.get("refresh_token") == cookie
    assert "auth.role_switched" not in _audit_actions(db, user)


def test_switch_role_needs_the_refresh_cookie(client: TestClient, db: Session) -> None:
    _register(client, admin=True, db=db)
    session = _sign_in_as(client, "USER")
    client.cookies.clear()

    response = client.post(SWITCH, json={"role": "ADMIN"}, headers=_bearer(session["access_token"]))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_refresh_token"


# --------------------------------------------------------------------------- refresh


def test_refresh_keeps_the_active_role(client: TestClient, db: Session) -> None:
    _register(client, admin=True, db=db)
    session = _sign_in_as(client, "USER")

    refreshed = client.post(REFRESH)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["active_role"] == "USER"
    assert _claims(refreshed.json()["access_token"])["role"] == "USER"

    switched = client.post(SWITCH, json={"role": "ADMIN"}, headers=_bearer(session["access_token"]))
    assert switched.status_code == 200, switched.text

    refreshed = client.post(REFRESH)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["active_role"] == "ADMIN"
    assert client.get(ME, headers=_bearer(refreshed.json()["access_token"])).json()["active_role"] == "ADMIN"


def test_a_tampered_refresh_role_prefix_is_rejected(client: TestClient, db: Session) -> None:
    _register(client, admin=True, db=db)
    _sign_in_as(client, "USER")
    cookie = client.cookies.get("refresh_token")
    assert cookie.startswith("USER.")

    forged = "ADMIN." + cookie.split(".", 1)[1]
    client.cookies.clear()
    response = client.post(REFRESH, headers={"Cookie": f"refresh_token={forged}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"


def test_a_legacy_refresh_token_without_a_role_still_refreshes(client: TestClient, db: Session) -> None:
    user = _register(client, admin=True, db=db)
    legacy = "legacyTokenWithoutRolePrefix_" + uuid.uuid4().hex
    db.add(RefreshToken(user_id=user.id, token_hash=hash_token(legacy), expires_at=refresh_token_expiry(), created_at=utcnow()))
    db.commit()

    response = client.post(REFRESH, headers={"Cookie": f"refresh_token={legacy}"})
    assert response.status_code == 200, response.text
    assert response.json()["active_role"] == "ADMIN"  # what the old token meant: the highest role


# --------------------------------------------------------------------------- tokens + guards


def test_an_access_token_without_a_role_claim_still_works(client: TestClient, db: Session) -> None:
    user = _register(client, admin=True, db=db)
    now = int(time.time())
    legacy = jwt.encode(
        {"sub": str(user.id), "type": "access", "iat": now, "exp": now + 600, "jti": "legacy"},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = client.get(ME, headers=_bearer(legacy))
    assert response.status_code == 200, response.text
    assert response.json()["active_role"] == "ADMIN"


def test_a_role_revoked_mid_session_kills_the_access_token_and_the_refresh(client: TestClient, db: Session) -> None:
    user = _register(client, admin=True, db=db)
    session = _sign_in_as(client, "ADMIN")
    assert client.get(ME, headers=_bearer(session["access_token"])).status_code == 200

    service.revoke_role(db, user, "ADMIN")
    db.commit()

    me = client.get(ME, headers=_bearer(session["access_token"]))
    assert me.status_code == 401
    assert me.json()["error"]["code"] == "role_revoked"

    refreshed = client.post(REFRESH)
    assert refreshed.status_code == 401
    assert refreshed.json()["error"]["code"] == "role_revoked"


@pytest.fixture
def guarded_client() -> TestClient:
    """A minimal app with one ``require_admin`` endpoint, sharing the test database."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/admin-only")
    def _admin_only(user: User = Depends(require_admin)) -> dict:
        return {"ok": True, "active_role": user.active_role}

    with TestClient(app) as c:
        yield c


def test_require_roles_checks_the_active_role_not_membership(
    client: TestClient, guarded_client: TestClient, db: Session
) -> None:
    _register(client, admin=True, db=db)
    as_user = _sign_in_as(client, "USER")

    refused = guarded_client.get("/admin-only", headers=_bearer(as_user["access_token"]))
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["message"] == "Insufficient permissions"

    as_admin = client.post(SWITCH, json={"role": "ADMIN"}, headers=_bearer(as_user["access_token"])).json()
    allowed = guarded_client.get("/admin-only", headers=_bearer(as_admin["access_token"]))
    assert allowed.status_code == 200, allowed.text
    assert allowed.json() == {"ok": True, "active_role": "ADMIN"}
