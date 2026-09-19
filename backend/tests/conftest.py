"""Shared pytest fixtures.

Tests run against an in-memory SQLite database (models use portable types) with the
mock LLM provider, so the suite needs no external services.
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("SEED_DEMO_DATA", "false")
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="jobpilot-test-uploads-"))
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-0123456789")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate every table between tests to keep them independent."""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The in-memory rate limiter is process-wide; reset it so a large suite never trips 429."""
    from app.core.rate_limit import _MemoryBackend, rate_limiter

    rate_limiter._backend = _MemoryBackend()
    rate_limiter._tried_redis = True  # never try to reach Redis from tests
    yield


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def user_payload() -> dict:
    return {"email": "tester@example.com", "password": "StrongPass123!", "full_name": "Test User"}


@pytest.fixture
def auth_client(client: TestClient, user_payload: dict) -> TestClient:
    """A TestClient that is already registered + logged in (Authorization header set)."""
    r = client.post("/api/v1/auth/register", json=user_payload)
    assert r.status_code in (200, 201), r.text
    token = r.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
