"""Browser API endpoints (CONTRACTS.md section 12): own sessions, own screenshots only."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.application import Application
from app.models.automation import BrowserSession
from app.models.company import Company
from app.models.enums import JobSourceType
from app.models.job import Job
from app.models.user import User

PREFIX = "/api/v1/browser"


@pytest.fixture(autouse=True)
def _reset_auth_rate_limit():
    """Every test here registers a fresh user; the in-memory limiter is process wide."""
    from app.core.rate_limit import rate_limiter

    hits = getattr(getattr(rate_limiter, "_backend", None), "_hits", None)
    if hits is not None:
        hits.clear()
    yield


def current_user(client: TestClient, db: Session) -> User:
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    return db.get(User, uuid.UUID(me.json()["id"]))


def make_application(db: Session, user: User) -> Application:
    company = Company(name="Northwind Labs", normalized_name=f"northwind{uuid.uuid4().hex[:8]}", domain="northwindlabs.dev")
    db.add(company)
    db.flush()
    job = Job(
        company_id=company.id,
        title="Full Stack Engineer",
        normalized_title="full stack engineer",
        description="demo",
        dedupe_hash=uuid.uuid4().hex,
    )
    db.add(job)
    db.flush()
    application = Application(user_id=user.id, job_id=job.id)
    db.add(application)
    db.commit()
    return application


def write_screenshot(application_id: uuid.UUID, name: str = "after_fill") -> Path:
    folder = Path(settings.UPLOAD_DIR) / "screenshots" / str(application_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n fake")
    return path


# --------------------------------------------------------------------------- status / auth


def test_endpoints_require_authentication(client: TestClient) -> None:
    for path in (f"{PREFIX}/sessions", f"{PREFIX}/status"):
        assert client.get(path).status_code == 401


def test_status_reports_availability(auth_client: TestClient) -> None:
    response = auth_client.get(f"{PREFIX}/status")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"available", "headless"}
    assert isinstance(body["available"], bool)
    assert body["headless"] is settings.PLAYWRIGHT_HEADLESS


# --------------------------------------------------------------------------- sessions


def test_sessions_are_listed_without_the_stored_state(auth_client: TestClient, db: Session) -> None:
    user = current_user(auth_client, db)
    db.add(
        BrowserSession(
            user_id=user.id,
            source=JobSourceType.DEMO_ATS,
            encrypted_storage_state="gAAAAA-not-real",
            user_agent="JobPilotAI/0.1",
        )
    )
    db.commit()

    response = auth_client.get(f"{PREFIX}/sessions")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["source"] == "DEMO_ATS"
    assert items[0]["has_stored_state"] is True
    assert "encrypted_storage_state" not in items[0]
    assert "storage_state" not in items[0]


def test_other_users_sessions_are_invisible(auth_client: TestClient, db: Session) -> None:
    stranger = User(email="stranger@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Stranger")
    db.add(stranger)
    db.flush()
    db.add(BrowserSession(user_id=stranger.id, source=JobSourceType.LINKEDIN))
    db.commit()

    assert auth_client.get(f"{PREFIX}/sessions").json() == []
    session_id = db.scalars(select(BrowserSession.id)).first()
    assert auth_client.delete(f"{PREFIX}/sessions/{session_id}").status_code == 404
    assert db.get(BrowserSession, session_id) is not None


def test_delete_own_session(auth_client: TestClient, db: Session) -> None:
    user = current_user(auth_client, db)
    row = BrowserSession(user_id=user.id, source=JobSourceType.DEMO_ATS)
    db.add(row)
    db.commit()
    session_id = row.id

    assert auth_client.delete(f"{PREFIX}/sessions/{session_id}").status_code == 204
    # Deletes are soft. Drop the identity map first: the global filter rewrites queries,
    # it cannot make an instance this session is already holding disappear.
    db.expunge_all()
    assert db.get(BrowserSession, session_id) is None
    tombstoned = db.get(BrowserSession, session_id, execution_options={"include_deleted": True})
    assert tombstoned is not None
    assert tombstoned.deleted_at is not None
    assert tombstoned.is_active is False


# --------------------------------------------------------------------------- screenshots


def test_screenshot_of_own_application_is_served(auth_client: TestClient, db: Session) -> None:
    user = current_user(auth_client, db)
    application = make_application(db, user)
    write_screenshot(application.id)

    response = auth_client.get(f"{PREFIX}/screenshots/{application.id}/after_fill")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
    assert auth_client.get(f"{PREFIX}/screenshots/{application.id}/after_fill.png").status_code == 200


def test_screenshot_of_another_users_application_is_404(auth_client: TestClient, db: Session) -> None:
    stranger = User(email="stranger2@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Stranger")
    db.add(stranger)
    db.flush()
    application = make_application(db, stranger)
    write_screenshot(application.id)

    assert auth_client.get(f"{PREFIX}/screenshots/{application.id}/after_fill").status_code == 404


def test_missing_screenshot_is_404(auth_client: TestClient, db: Session) -> None:
    user = current_user(auth_client, db)
    application = make_application(db, user)
    assert auth_client.get(f"{PREFIX}/screenshots/{application.id}/nope").status_code == 404


@pytest.mark.parametrize("name", ["..%2F..%2Fsecret", "..", "a/b", "sub%2Ffile"])
def test_path_traversal_is_rejected(auth_client: TestClient, db: Session, name: str) -> None:
    user = current_user(auth_client, db)
    application = make_application(db, user)
    response = auth_client.get(f"{PREFIX}/screenshots/{application.id}/{name}")
    assert response.status_code in (404, 422), response.text
    assert "secret" not in response.text or response.status_code == 422
