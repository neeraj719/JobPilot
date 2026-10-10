"""Stay signed in: session lifetime, rotation, the device list and re-authentication.

"Save my login" is implemented without ever storing the password: a remember-me choice
that sets how long the refresh cookie lives, the browser's own password manager on the
client, and a list of signed-in devices the user can sign out. These tests pin down the
server half.
"""
from __future__ import annotations

import time
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import REAUTH_HEADER, REAUTH_MAX_ATTEMPTS
from app.core.security import create_access_token, hash_token
from app.models.audit import AuditLog
from app.models.user import RefreshToken, User
from app.modules.auth import service
from app.modules.auth.devices import device_label

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
SELECT = "/api/v1/auth/select-role"
SWITCH = "/api/v1/auth/switch-role"
REFRESH = "/api/v1/auth/refresh"
PASSWORD = "/api/v1/auth/me/password"
SESSIONS = "/api/v1/auth/sessions"
REVOKE_OTHERS = "/api/v1/auth/sessions/revoke-others"

CREDENTIALS = {"email": "device.owner@example.com", "password": "StrongPass123", "full_name": "Device Owner"}
LOGIN_BODY = {"email": CREDENTIALS["email"], "password": CREDENTIALS["password"]}

CHROME_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.5 Mobile/15E148 Safari/604.1"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0"

REMEMBERED_MAX_AGE = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.core.rate_limit import rate_limiter

    hits = getattr(rate_limiter._backend, "_hits", None)
    if hits is not None:
        hits.clear()
    yield


@pytest.fixture
def device():
    """Factory for extra browsers: each TestClient has its own cookie jar and user agent."""
    from app.main import app

    opened: list[TestClient] = []

    def _open(user_agent: str) -> TestClient:
        c = TestClient(app, headers={"User-Agent": user_agent})
        c.__enter__()
        opened.append(c)
        return c

    yield _open
    for c in opened:
        c.__exit__(None, None, None)


# --------------------------------------------------------------------------- helpers


def _register(client: TestClient, db: Session, *, admin: bool = False) -> User:
    response = client.post(REGISTER, json=CREDENTIALS)
    assert response.status_code == 201, response.text
    # Sign the registration session out so each test starts from the devices it opens.
    assert client.post("/api/v1/auth/logout").status_code == 200
    client.cookies.clear()
    user = _user(db)
    if admin:
        service.assign_role(db, user, "ADMIN")
        db.commit()
    return _user(db)


def _user(db: Session) -> User:
    db.expire_all()
    return db.scalars(select(User).where(User.email == CREDENTIALS["email"])).one()


def _login(client: TestClient, *, remember_me: bool) -> dict:
    response = client.post(LOGIN, json={**LOGIN_BODY, "remember_me": remember_me})
    assert response.status_code == 200, response.text
    return {"body": response.json(), "set_cookie": response.headers.get("set-cookie", "")}


def _bearer(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _row(db: Session, raw_cookie: str) -> RefreshToken:
    db.expire_all()
    return db.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_cookie)).execution_options(include_deleted=True)
    ).one()


def _lifetime(row: RefreshToken) -> timedelta:
    return row.expires_at - row.created_at


def _stale_token(user: User, role: str = "USER") -> str:
    """An access token that is still valid but was issued an hour ago."""
    return create_access_token(user.id, role, extra={"iat": int(time.time()) - 3600})


def _actions(db: Session, user: User) -> list[str]:
    db.expire_all()
    return list(db.scalars(select(AuditLog.action).where(AuditLog.user_id == user.id)))


def _assert_session_cookie(set_cookie: str) -> None:
    lowered = set_cookie.lower()
    assert "refresh_token=" in set_cookie
    assert "max-age" not in lowered and "expires" not in lowered, set_cookie
    assert "httponly" in lowered and "samesite=lax" in lowered and "path=/api/v1/auth" in lowered


def _assert_persistent_cookie(set_cookie: str) -> None:
    lowered = set_cookie.lower()
    assert "refresh_token=" in set_cookie
    assert f"max-age={REMEMBERED_MAX_AGE}" in lowered, set_cookie
    assert "httponly" in lowered and "samesite=lax" in lowered and "path=/api/v1/auth" in lowered


# --------------------------------------------------------------------------- lifetime


def test_login_without_remember_me_is_a_short_browser_session(client: TestClient, db: Session) -> None:
    _register(client, db)

    login = _login(client, remember_me=False)
    _assert_session_cookie(login["set_cookie"])
    row = _row(db, client.cookies.get("refresh_token"))
    assert _lifetime(row) == timedelta(hours=service.SHORT_SESSION_HOURS)
    assert service.is_remembered(row) is False


def test_remember_me_defaults_to_off(client: TestClient, db: Session) -> None:
    _register(client, db)

    response = client.post(LOGIN, json=LOGIN_BODY)
    assert response.status_code == 200, response.text
    _assert_session_cookie(response.headers.get("set-cookie", ""))


def test_login_with_remember_me_is_a_persistent_cookie(client: TestClient, db: Session) -> None:
    _register(client, db)

    login = _login(client, remember_me=True)
    _assert_persistent_cookie(login["set_cookie"])
    row = _row(db, client.cookies.get("refresh_token"))
    assert abs(_lifetime(row) - timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)) < timedelta(seconds=5)
    assert service.is_remembered(row) is True


def test_register_honours_remember_me(client: TestClient) -> None:
    response = client.post(REGISTER, json={**CREDENTIALS, "remember_me": True})
    assert response.status_code == 201, response.text
    _assert_persistent_cookie(response.headers.get("set-cookie", ""))


@pytest.mark.parametrize("remember_me", [True, False])
def test_select_role_honours_remember_me(client: TestClient, db: Session, remember_me: bool) -> None:
    _register(client, db, admin=True)
    challenge = client.post(LOGIN, json={**LOGIN_BODY, "remember_me": remember_me}).json()
    assert challenge["requires_role_selection"] is True

    response = client.post(
        SELECT, json={"selection_token": challenge["selection_token"], "role": "USER", "remember_me": remember_me}
    )
    assert response.status_code == 200, response.text
    set_cookie = response.headers.get("set-cookie", "")
    if remember_me:
        _assert_persistent_cookie(set_cookie)
    else:
        _assert_session_cookie(set_cookie)
    assert service.is_remembered(_row(db, client.cookies.get("refresh_token"))) is remember_me


# --------------------------------------------------------------------------- rotation


@pytest.mark.parametrize("remember_me", [True, False])
def test_refresh_preserves_the_remember_choice(client: TestClient, db: Session, remember_me: bool) -> None:
    _register(client, db)
    _login(client, remember_me=remember_me)

    for _ in range(2):  # survives more than one generation
        refreshed = client.post(REFRESH)
        assert refreshed.status_code == 200, refreshed.text
        set_cookie = refreshed.headers.get("set-cookie", "")
        if remember_me:
            _assert_persistent_cookie(set_cookie)
        else:
            _assert_session_cookie(set_cookie)
        assert service.is_remembered(_row(db, client.cookies.get("refresh_token"))) is remember_me


@pytest.mark.parametrize("remember_me", [True, False])
def test_switch_role_preserves_the_remember_choice(client: TestClient, db: Session, remember_me: bool) -> None:
    _register(client, db, admin=True)
    challenge = client.post(LOGIN, json=LOGIN_BODY).json()
    session = client.post(
        SELECT, json={"selection_token": challenge["selection_token"], "role": "USER", "remember_me": remember_me}
    ).json()

    switched = client.post(SWITCH, json={"role": "ADMIN"}, headers=_bearer(session["access_token"]))
    assert switched.status_code == 200, switched.text
    set_cookie = switched.headers.get("set-cookie", "")
    if remember_me:
        _assert_persistent_cookie(set_cookie)
    else:
        _assert_session_cookie(set_cookie)
    cookie = client.cookies.get("refresh_token")
    assert cookie.startswith("ADMIN.")
    assert service.is_remembered(_row(db, cookie)) is remember_me


def test_legacy_full_lifetime_rows_count_as_remembered(db: Session, client: TestClient) -> None:
    user = _register(client, db)
    raw = service.create_refresh_token(db, user, remember=True)
    db.commit()
    assert service.is_remembered(_row(db, raw)) is True


# --------------------------------------------------------------------------- reuse detection


def test_reusing_a_rotated_token_revokes_every_session_of_the_user(
    client: TestClient, db: Session, device
) -> None:
    user = _register(client, db)
    laptop = device(CHROME_WINDOWS)
    phone = device(SAFARI_IPHONE)
    _login(laptop, remember_me=True)
    _login(phone, remember_me=False)
    stolen = laptop.cookies.get("refresh_token")

    assert laptop.post(REFRESH).status_code == 200  # the laptop rotates; `stolen` is now retired

    replay = client.post(REFRESH, headers={"Cookie": f"refresh_token={stolen}"})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "refresh_token_reused"

    db.expire_all()
    assert all(t.revoked_at is not None for t in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)))
    assert "auth.refresh_reuse_detected" in _actions(db, user)
    # The whole family is gone: the laptop's fresh token and the phone's untouched one.
    assert laptop.post(REFRESH).status_code == 401
    assert phone.post(REFRESH).status_code == 401


def test_an_expired_short_session_does_not_trip_the_theft_response(
    client: TestClient, db: Session, device
) -> None:
    user = _register(client, db)
    laptop = device(CHROME_WINDOWS)
    phone = device(SAFARI_IPHONE)
    _login(laptop, remember_me=True)
    _login(phone, remember_me=False)

    row = _row(db, phone.cookies.get("refresh_token"))
    row.expires_at = row.created_at + timedelta(seconds=1) - timedelta(hours=1)
    db.commit()

    for _ in range(2):  # the browser retries its dead cookie, e.g. on the next app start
        response = phone.post(REFRESH)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "refresh_token_expired"

    assert "auth.refresh_reuse_detected" not in _actions(db, user)
    assert laptop.post(REFRESH).status_code == 200


# --------------------------------------------------------------------------- sessions list


def test_sessions_list_shows_every_device_and_marks_this_one(client: TestClient, db: Session, device) -> None:
    _register(client, db)
    laptop = device(CHROME_WINDOWS)
    phone = device(SAFARI_IPHONE)
    token = _login(laptop, remember_me=True)["body"]["access_token"]
    _login(phone, remember_me=False)

    response = laptop.get(SESSIONS, headers=_bearer(token))
    assert response.status_code == 200, response.text
    sessions = response.json()
    assert len(sessions) == 2
    by_label = {s["device_label"]: s for s in sessions}
    assert set(by_label) == {"Chrome on Windows", "Safari on iPhone"}
    assert by_label["Chrome on Windows"]["is_current"] is True
    assert by_label["Chrome on Windows"]["remembered"] is True
    assert by_label["Safari on iPhone"]["is_current"] is False
    assert by_label["Safari on iPhone"]["remembered"] is False
    assert by_label["Safari on iPhone"]["user_agent"] == SAFARI_IPHONE
    assert set(sessions[0]) == {"id", "created_at", "expires_at", "user_agent", "device_label", "is_current", "remembered"}

    # Without the cookie the same list comes back with nothing marked as current.
    laptop.cookies.clear()
    assert not any(s["is_current"] for s in laptop.get(SESSIONS, headers=_bearer(token)).json())


def test_sessions_list_hides_revoked_and_expired_tokens_and_other_users(
    client: TestClient, db: Session, device
) -> None:
    user = _register(client, db)
    laptop = device(CHROME_WINDOWS)
    token = _login(laptop, remember_me=True)["body"]["access_token"]
    laptop.post(REFRESH)  # leaves a revoked predecessor behind

    expired = service.create_refresh_token(db, user, remember=False)
    row = _row(db, expired)
    row.expires_at = row.created_at - timedelta(minutes=1)
    other = service.create_user(db, "someone.else@example.com", "StrongPass123", "Someone Else")
    service.create_refresh_token(db, other)
    db.commit()

    sessions = laptop.get(SESSIONS, headers=_bearer(token)).json()
    assert len(sessions) == 1 and sessions[0]["is_current"] is True


def test_sessions_list_requires_authentication(client: TestClient) -> None:
    assert client.get(SESSIONS).status_code == 401


# --------------------------------------------------------------------------- revoke one / others


def test_revoke_one_session_signs_that_device_out_and_nobody_else(
    client: TestClient, db: Session, device
) -> None:
    user = _register(client, db)
    laptop = device(CHROME_WINDOWS)
    phone = device(SAFARI_IPHONE)
    token = _login(laptop, remember_me=True)["body"]["access_token"]
    _login(phone, remember_me=True)

    phone_session = next(s for s in laptop.get(SESSIONS, headers=_bearer(token)).json() if not s["is_current"])
    response = laptop.delete(f"{SESSIONS}/{phone_session['id']}", headers=_bearer(token))
    assert response.status_code == 200, response.text
    assert response.json()["revoked"] == 1
    assert "set-cookie" not in response.headers  # not this device: our cookie stays

    # The phone wakes up and tries its old cookie: told it was signed out, and that does
    # *not* count as token theft, so the laptop keeps working.
    retry = phone.post(REFRESH)
    assert retry.status_code == 401
    assert retry.json()["error"]["code"] == "session_revoked"
    assert laptop.post(REFRESH).status_code == 200

    actions = _actions(db, user)
    assert "auth.session_revoked" in actions
    assert "auth.refresh_reuse_detected" not in actions
    assert len(laptop.get(SESSIONS, headers=_bearer(token)).json()) == 1


def test_revoking_the_current_session_clears_the_cookie(client: TestClient, db: Session) -> None:
    _register(client, db)
    token = _login(client, remember_me=True)["body"]["access_token"]
    current = client.get(SESSIONS, headers=_bearer(token)).json()[0]

    response = client.delete(f"{SESSIONS}/{current['id']}", headers=_bearer(token))
    assert response.status_code == 200, response.text
    assert 'refresh_token=""' in response.headers.get("set-cookie", "")
    assert client.post(REFRESH).status_code == 401


def test_revoke_session_is_404_for_someone_elses_or_unknown_session(client: TestClient, db: Session) -> None:
    _register(client, db)
    token = _login(client, remember_me=False)["body"]["access_token"]
    other = service.create_user(db, "someone.else@example.com", "StrongPass123", "Someone Else")
    foreign = service.create_refresh_token(db, other)
    db.commit()
    foreign_row = _row(db, foreign)

    for session_id in (foreign_row.id, uuid.uuid4()):
        response = client.delete(f"{SESSIONS}/{session_id}", headers=_bearer(token))
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "session_not_found"
    assert _row(db, foreign).revoked_at is None


def test_revoke_others_keeps_only_this_device(client: TestClient, db: Session, device) -> None:
    user = _register(client, db)
    laptop = device(CHROME_WINDOWS)
    phone = device(SAFARI_IPHONE)
    tablet = device(FIREFOX_LINUX)
    token = _login(laptop, remember_me=True)["body"]["access_token"]
    _login(phone, remember_me=True)
    _login(tablet, remember_me=False)

    response = laptop.post(REVOKE_OTHERS, headers=_bearer(token))
    assert response.status_code == 200, response.text
    assert response.json()["revoked"] == 2

    sessions = laptop.get(SESSIONS, headers=_bearer(token)).json()
    assert len(sessions) == 1 and sessions[0]["is_current"] is True
    assert phone.post(REFRESH).json()["error"]["code"] == "session_revoked"
    assert tablet.post(REFRESH).json()["error"]["code"] == "session_revoked"
    assert laptop.post(REFRESH).status_code == 200

    entry = db.scalars(
        select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "auth.sessions_revoked_others")
    ).one()
    assert entry.meta == {"sessions_revoked": 2, "current_session_kept": True}


# --------------------------------------------------------------------------- password change


def test_password_change_signs_out_other_devices_and_rotates_this_one(
    client: TestClient, db: Session, device
) -> None:
    user = _register(client, db)
    laptop = device(CHROME_WINDOWS)
    phone = device(SAFARI_IPHONE)
    token = _login(laptop, remember_me=True)["body"]["access_token"]
    _login(phone, remember_me=True)
    before = laptop.cookies.get("refresh_token")

    response = laptop.put(
        PASSWORD,
        json={"current_password": CREDENTIALS["password"], "new_password": "AnotherPass1"},
        headers=_bearer(token),
    )
    assert response.status_code == 200, response.text
    _assert_persistent_cookie(response.headers.get("set-cookie", ""))  # rotated, still remembered
    after = laptop.cookies.get("refresh_token")
    assert after and after != before
    assert _row(db, before).replaced_by_hash == hash_token(after)

    assert phone.post(REFRESH).json()["error"]["code"] == "session_revoked"
    assert laptop.post(REFRESH).status_code == 200
    entry = db.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "auth.password_changed")).one()
    assert entry.meta == {"sessions_revoked": 1, "current_session_kept": True}


# --------------------------------------------------------------------------- re-authentication


def test_reauth_fresh_token_passes(client: TestClient, db: Session, device) -> None:
    _register(client, db)
    laptop = device(CHROME_WINDOWS)
    token = _login(laptop, remember_me=False)["body"]["access_token"]
    assert laptop.post(REVOKE_OTHERS, headers=_bearer(token)).status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", REVOKE_OTHERS), ("delete", f"{SESSIONS}/{uuid.uuid4()}"), ("put", PASSWORD)],
)
def test_reauth_stale_token_without_password_is_refused(
    client: TestClient, db: Session, method: str, path: str
) -> None:
    user = _register(client, db)
    _login(client, remember_me=False)
    kwargs: dict = {"headers": _bearer(_stale_token(user))}
    if method == "put":
        kwargs["json"] = {"current_password": CREDENTIALS["password"], "new_password": "AnotherPass1"}

    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 401, response.text
    error = response.json()["error"]
    assert error["code"] == "reauth_required"
    assert error["details"] == {"reason": "stale_token"}
    # Listing is not sensitive and keeps working with the same token.
    assert client.get(SESSIONS, headers=_bearer(_stale_token(user))).status_code == 200


def test_reauth_stale_token_with_the_right_password_passes(client: TestClient, db: Session) -> None:
    user = _register(client, db)
    _login(client, remember_me=False)
    headers = _bearer(_stale_token(user), **{REAUTH_HEADER: CREDENTIALS["password"]})
    assert client.post(REVOKE_OTHERS, headers=headers).status_code == 200


def test_reauth_accepts_a_percent_encoded_non_ascii_password(client: TestClient, db: Session) -> None:
    password = "Pässwört 123"  # non-Latin-1-safe in a header, and has a space
    response = client.post(REGISTER, json={**CREDENTIALS, "password": password})
    assert response.status_code == 201, response.text
    user = _user(db)
    from urllib.parse import quote

    headers = _bearer(_stale_token(user), **{REAUTH_HEADER: quote(password, safe="")})
    assert client.post(REVOKE_OTHERS, headers=headers).status_code == 200


def test_reauth_wrong_password_fails_is_audited_and_rate_limited(client: TestClient, db: Session) -> None:
    user = _register(client, db)
    _login(client, remember_me=False)
    headers = _bearer(_stale_token(user), **{REAUTH_HEADER: "WrongPass999"})

    for _ in range(REAUTH_MAX_ATTEMPTS):
        response = client.post(REVOKE_OTHERS, headers=headers)
        assert response.status_code == 401, response.text
        assert response.json()["error"]["code"] == "reauth_required"
        assert response.json()["error"]["details"] == {"reason": "invalid_password"}

    limited = client.post(REVOKE_OTHERS, headers=headers)
    assert limited.status_code == 429
    # Locked even with the right password until the window passes: no free guesses.
    right = _bearer(_stale_token(user), **{REAUTH_HEADER: CREDENTIALS["password"]})
    assert client.post(REVOKE_OTHERS, headers=right).status_code == 429

    assert _actions(db, user).count("auth.reauth_failed") == REAUTH_MAX_ATTEMPTS
    # Nothing was revoked by the refused attempts.
    assert any(t.revoked_at is None for t in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)))


def test_an_access_token_without_iat_is_never_fresh(client: TestClient, db: Session) -> None:
    import jwt

    user = _register(client, db)
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(user.id), "role": "USER", "type": "access", "exp": now + 600, "jti": "no-iat"},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    response = client.post(REVOKE_OTHERS, headers=_bearer(token))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "reauth_required"


# --------------------------------------------------------------------------- no stored passwords


def test_no_password_or_derivative_reaches_the_client_or_the_token_table(client: TestClient, db: Session) -> None:
    _register(client, db)
    login = _login(client, remember_me=True)
    secret = CREDENTIALS["password"]
    assert secret not in login["set_cookie"]
    assert secret not in str(login["body"])
    columns = {column.name for column in RefreshToken.__table__.columns}
    assert not {"password", "hashed_password", "credential"} & columns


# --------------------------------------------------------------------------- device labels


@pytest.mark.parametrize(
    ("user_agent", "label"),
    [
        (CHROME_WINDOWS, "Chrome on Windows"),
        (SAFARI_IPHONE, "Safari on iPhone"),
        (FIREFOX_LINUX, "Firefox on Linux"),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
            "Edge on Windows",
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.5 Safari/605.1.15",
            "Safari on macOS",
        ),
        (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Mobile Safari/537.36",
            "Chrome on Android",
        ),
        ("python-httpx/0.27.0", "Unknown device"),
        ("testclient", "Unknown device"),
        (None, "Unknown device"),
        ("", "Unknown device"),
    ],
)
def test_device_label(user_agent: str | None, label: str) -> None:
    assert device_label(user_agent) == label


# --------------------------------------------------------------------------- remember this device later


REMEMBER_CURRENT = "/api/v1/auth/sessions/current/remember"


def test_token_responses_say_whether_the_session_is_remembered(client: TestClient, db: Session) -> None:
    _register(client, db)
    assert _login(client, remember_me=False)["body"]["remembered"] is False
    assert client.post(REFRESH).json()["remembered"] is False
    client.cookies.clear()
    assert _login(client, remember_me=True)["body"]["remembered"] is True
    assert client.post(REFRESH).json()["remembered"] is True


def test_turning_on_stay_signed_in_from_settings_rotates_into_a_remembered_session(
    client: TestClient, db: Session
) -> None:
    user = _register(client, db)
    token = _login(client, remember_me=False)["body"]["access_token"]
    before = client.cookies.get("refresh_token")

    response = client.post(REMEMBER_CURRENT, json={"remember": True}, headers=_bearer(token))
    assert response.status_code == 200, response.text
    _assert_persistent_cookie(response.headers.get("set-cookie", ""))
    body = response.json()
    assert body["remembered"] is True and body["is_current"] is True
    after = client.cookies.get("refresh_token")
    assert after != before and _row(db, before).replaced_by_hash == hash_token(after)
    assert service.is_remembered(_row(db, after)) is True

    # ...and it stays remembered across the next refresh; and can be turned off again.
    _assert_persistent_cookie(client.post(REFRESH).headers.get("set-cookie", ""))
    off = client.post(REMEMBER_CURRENT, json={"remember": False}, headers=_bearer(token))
    assert off.status_code == 200, off.text
    _assert_session_cookie(off.headers.get("set-cookie", ""))
    assert "auth.session_remember_changed" in _actions(db, user)


def test_remember_this_device_needs_recent_auth_and_a_cookie(client: TestClient, db: Session) -> None:
    user = _register(client, db)
    token = _login(client, remember_me=False)["body"]["access_token"]

    stale = client.post(REMEMBER_CURRENT, json={"remember": True}, headers=_bearer(_stale_token(user)))
    assert stale.status_code == 401 and stale.json()["error"]["code"] == "reauth_required"

    client.cookies.clear()
    missing = client.post(REMEMBER_CURRENT, json={"remember": True}, headers=_bearer(token))
    assert missing.status_code == 401 and missing.json()["error"]["code"] == "missing_refresh_token"
