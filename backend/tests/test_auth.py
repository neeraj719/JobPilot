"""Auth flow tests (contract §2): registration, login, refresh rotation, password change."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models.audit import AuditLog
from app.models.automation import AutomationConfig
from app.models.profile import JobPreference, UserProfile
from app.models.user import RefreshToken, User

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
PASSWORD = "/api/v1/auth/me/password"

CREDENTIALS = {"email": "pilot@example.com", "password": "StrongPass123", "full_name": "Pilot User"}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.core.rate_limit import rate_limiter

    hits = getattr(rate_limiter._backend, "_hits", None)
    if hits is not None:
        hits.clear()
    yield


def _register(client: TestClient, **overrides) -> dict:
    payload = {**CREDENTIALS, **overrides}
    response = client.post(REGISTER, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_register_creates_user_profile_preferences_and_config(client: TestClient, db: Session) -> None:
    body = _register(client)

    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0
    assert body["user"]["email"] == CREDENTIALS["email"]
    assert body["user"]["role"] == "USER"
    assert "hashed_password" not in body["user"]
    assert "refresh_token" in client.cookies

    user = db.scalars(select(User).where(User.email == CREDENTIALS["email"])).one()
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == user.id)).one()
    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == user.id)).one()
    config = db.scalars(select(AutomationConfig).where(AutomationConfig.user_id == user.id)).one()

    assert profile.full_name == CREDENTIALS["full_name"]
    assert profile.email == CREDENTIALS["email"]
    assert preference.currency == "INR"
    assert preference.min_match_score == 75
    assert preference.only_posted_within_hours == 24
    assert config.daily_application_limit == 20
    assert config.min_match_score == 75
    assert config.auto_submit_enabled is False

    actions = set(db.scalars(select(AuditLog.action).where(AuditLog.user_id == user.id)))
    assert "auth.register" in actions


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    _register(client)
    response = client.post(REGISTER, json=CREDENTIALS)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


@pytest.mark.parametrize("password", ["short1", "nodigitshere", "12345678", ""])
def test_register_enforces_password_policy(client: TestClient, password: str) -> None:
    response = client.post(REGISTER, json={**CREDENTIALS, "password": password})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] in {"weak_password", "validation_error"}


def test_register_rejects_blank_full_name(client: TestClient) -> None:
    response = client.post(REGISTER, json={**CREDENTIALS, "full_name": "   "})
    assert response.status_code == 422, response.text


def test_register_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(REGISTER, json={**CREDENTIALS, "email": "not-an-email"})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"


def test_login_sets_refresh_cookie_and_updates_last_login(client: TestClient, db: Session) -> None:
    _register(client)
    client.cookies.clear()

    response = client.post(LOGIN, json={"email": CREDENTIALS["email"], "password": CREDENTIALS["password"]})
    assert response.status_code == 200, response.text
    assert response.json()["user"]["last_login_at"] is not None

    cookie_header = response.headers.get("set-cookie", "")
    assert "refresh_token=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Path=/api/v1/auth" in cookie_header

    user = db.scalars(select(User).where(User.email == CREDENTIALS["email"])).one()
    assert user.last_login_at is not None
    assert db.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "auth.login")).first()


def test_login_with_wrong_password_is_generic_401_and_audited(client: TestClient, db: Session) -> None:
    _register(client)

    response = client.post(LOGIN, json={"email": CREDENTIALS["email"], "password": "WrongPass123"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password"

    unknown = client.post(LOGIN, json={"email": "nobody@example.com", "password": "WrongPass123"})
    assert unknown.status_code == 401
    assert unknown.json()["error"]["message"] == "Invalid email or password"

    failures = db.scalars(select(AuditLog).where(AuditLog.action == "auth.login_failed")).all()
    assert len(failures) == 2
    assert {f.level.value for f in failures} == {"WARN"}


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get(ME).status_code == 401
    assert client.get(ME, headers={"Authorization": "Bearer not-a-token"}).status_code == 401

    body = _register(client)
    response = client.get(ME, headers={"Authorization": f"Bearer {body['access_token']}"})
    assert response.status_code == 200
    assert response.json()["email"] == CREDENTIALS["email"]
    assert "hashed_password" not in response.json()


def test_refresh_rotates_token_and_reuse_revokes_every_session(client: TestClient, db: Session) -> None:
    _register(client)
    client.cookies.clear()
    client.post(LOGIN, json={"email": CREDENTIALS["email"], "password": CREDENTIALS["password"]})
    first_token = client.cookies.get("refresh_token")
    assert first_token

    rotated = client.post(REFRESH)
    assert rotated.status_code == 200, rotated.text
    second_token = client.cookies.get("refresh_token")
    assert second_token and second_token != first_token
    assert rotated.json()["access_token"]

    user = db.scalars(select(User).where(User.email == CREDENTIALS["email"])).one()
    old_row = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_not(None))).first()
    assert old_row is not None and old_row.replaced_by_hash

    # Replaying the retired token is treated as theft: 401 + every session revoked.
    reuse = client.post(REFRESH, headers={"Cookie": f"refresh_token={first_token}"})
    assert reuse.status_code == 401, reuse.text
    assert reuse.json()["error"]["code"] == "refresh_token_reused"

    db.expire_all()
    tokens = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)).all()
    assert tokens and all(t.revoked_at is not None for t in tokens)
    assert db.scalars(select(AuditLog).where(AuditLog.action == "auth.refresh_reuse_detected")).first() is not None

    # ...including the token that was still valid a moment ago.
    assert client.post(REFRESH).status_code == 401


def test_refresh_without_cookie_is_401(client: TestClient) -> None:
    response = client.post(REFRESH)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_refresh_token"


def test_logout_revokes_the_refresh_token(client: TestClient, db: Session) -> None:
    _register(client)
    token = client.cookies.get("refresh_token")
    assert token

    response = client.post(LOGOUT)
    assert response.status_code == 200
    assert response.json()["ok"] is True

    db.expire_all()
    assert db.scalars(select(AuditLog).where(AuditLog.action == "auth.logout")).first() is not None
    row = db.scalars(select(RefreshToken)).one()
    assert row.revoked_at is not None
    assert client.post(REFRESH, headers={"Cookie": f"refresh_token={token}"}).status_code == 401


def test_change_password_flow(client: TestClient, db: Session) -> None:
    body = _register(client)
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    first_cookie = client.cookies.get("refresh_token")

    assert client.put(PASSWORD, json={"current_password": "x", "new_password": "AnotherPass1"}, headers=headers).status_code == 401
    weak = client.put(
        PASSWORD,
        json={"current_password": CREDENTIALS["password"], "new_password": "weak"},
        headers=headers,
    )
    assert weak.status_code == 422

    changed = client.put(
        PASSWORD,
        json={"current_password": CREDENTIALS["password"], "new_password": "AnotherPass1"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text

    db.expire_all()
    assert db.scalars(select(AuditLog).where(AuditLog.action == "auth.password_changed")).first() is not None
    # This device's session is rotated (not ended); every other session is signed out
    # (see tests/test_auth_sessions.py for the multi-device version).
    new_cookie = client.cookies.get("refresh_token")
    assert new_cookie and new_cookie != first_cookie
    live = [t for t in db.scalars(select(RefreshToken)).all() if t.revoked_at is None]
    assert [t.token_hash for t in live] == [hash_token(new_cookie)]

    assert client.post(LOGIN, json={"email": CREDENTIALS["email"], "password": CREDENTIALS["password"]}).status_code == 401
    assert client.post(LOGIN, json={"email": CREDENTIALS["email"], "password": "AnotherPass1"}).status_code == 200


def test_create_user_service_is_reusable(db: Session) -> None:
    from app.modules.auth.service import authenticate, create_user

    user = create_user(db, "Service.User@Example.com ", "ServicePass1", "  Service   User ")
    db.commit()
    assert user.email == "service.user@example.com"
    assert user.full_name == "Service User"
    assert user.hashed_password != "ServicePass1"

    assert authenticate(db, "service.user@example.com", "ServicePass1").id == user.id
