"""Shared pytest fixtures.

The suite runs against a **real PostgreSQL** database (``jobpilot_test``), not SQLite:
the 27 tables live in five named schemas (``master``, ``unified``, ``transaction``,
``media``, ``audit``) and only PostgreSQL has schemas, so testing anywhere else would
test a translated layout rather than the one that ships.

The database is created on demand from the ``postgres`` maintenance database and is
separate from the ``jobpilot`` demo database, so running the suite never touches demo
data. Point ``TEST_DATABASE_URL`` somewhere else to override.

Everything else stays local: ``LLM_PROVIDER=mock`` and an in-process rate limiter mean
no other service is required.
"""
from __future__ import annotations

import os
import tempfile

#: Host-side port of the Postgres container, read from the same variable
#: ``docker-compose.yml`` uses so the two can never drift. Set POSTGRES_HOST_PORT when
#: something else on the machine already owns 5432 — a natively installed PostgreSQL is
#: the usual culprit, and it answers with "password authentication failed" rather than
#: a connection error, which looks like a credentials problem but is not one.
POSTGRES_HOST_PORT = os.getenv("POSTGRES_HOST_PORT", "5432")
POSTGRES_USER = os.getenv("POSTGRES_USER", "jobpilot")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "jobpilot")

#: Deliberately *not* SQLite, and deliberately not the ``jobpilot`` demo database.
#: Override with TEST_DATABASE_URL, not DATABASE_URL, so a shell that exports
#: DATABASE_URL for the dev server cannot silently redirect the suite onto demo data.
DEFAULT_TEST_DATABASE_URL = (
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@localhost:{POSTGRES_HOST_PORT}/jobpilot_test"
)
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)

os.environ.setdefault("ENV", "test")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("LLM_PROVIDER", "mock")
#: Local embeddings (Ollama) stay off unless a test mocks them; the deterministic path is the default.
os.environ.setdefault("EMBEDDINGS_ENABLED", "false")
os.environ.setdefault("SEED_DEMO_DATA", "false")
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="jobpilot-test-uploads-"))
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-0123456789")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.db_triggers import create_updated_at_triggers, drop_updated_at_triggers, metadata_tables  # noqa: E402
from app.models import DEFAULT_ROLES, SCHEMAS, Base  # noqa: E402

_SAFE_URL = make_url(TEST_DATABASE_URL).render_as_string(hide_password=True)
UNREACHABLE = (
    f"Cannot reach PostgreSQL at {_SAFE_URL} (host port {POSTGRES_HOST_PORT}).\n"
    "The test suite requires it: the models live in five named schemas, which SQLite does not have.\n"
    "Start it with:  docker compose up -d postgres\n"
    "\n"
    "If the failure is 'password authentication failed for user jobpilot', something else is\n"
    f"listening on port {POSTGRES_HOST_PORT} \u2014 most often a natively installed PostgreSQL Windows\n"
    "service. Stop it, or publish the container on a free port instead. Check with\n"
    f"  docker compose port postgres 5432\n"
    "and set POSTGRES_HOST_PORT (or TEST_DATABASE_URL) to match."
)

#: Every table, schema-qualified and quoted — ``transaction`` is a reserved word.
_ALL_TABLES = ", ".join(f'"{table.schema}"."{table.name}"' for table in Base.metadata.sorted_tables)


def _seed_roles(conn) -> None:
    """Re-create the ``master.roles`` reference rows.

    In production the Alembic migration inserts them, so they simply exist. The suite
    builds its schema from ``Base.metadata`` and wipes every table between tests, so the
    two rows have to be put back each time or the first ``create_user`` after a truncate
    would have no ``USER`` role to map to.

    The timestamps are left out of the INSERT deliberately: ``created_at``/``updated_at``
    are the database's to fill (``DEFAULT now()``), and naming them here would quietly
    stop exercising that.
    """
    for name, description in DEFAULT_ROLES:
        conn.execute(
            text(
                'INSERT INTO "master"."roles" (id, name, description, is_active) '
                "VALUES (gen_random_uuid(), :name, :description, true)"
            ),
            {"name": name, "description": description},
        )


def _ensure_database() -> None:
    """``CREATE DATABASE`` the test database if it is not there yet."""
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with admin.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError as exc:  # pragma: no cover - depends on local infra
        raise pytest.UsageError(f"{UNREACHABLE}\n\n{exc}") from exc
    finally:
        admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    if engine.dialect.name != "postgresql":  # pragma: no cover - misconfiguration guard
        raise pytest.UsageError(UNREACHABLE)
    _ensure_database()
    with engine.begin() as conn:
        for schema in SCHEMAS:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        # ``updated_at`` is maintained by a trigger, and triggers are not part of
        # SQLAlchemy metadata — ``create_all`` does not know about them. Without this the
        # convention would hold in production and not here, and the test that proves a
        # raw UPDATE bumps the timestamp would be proving nothing. Same helper the
        # migration calls, so the two cannot drift.
        create_updated_at_triggers(conn, metadata_tables(Base.metadata))
        _seed_roles(conn)
    yield
    with engine.begin() as conn:
        drop_updated_at_triggers(conn, metadata_tables(Base.metadata))
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        for schema in SCHEMAS:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate every table between tests to keep them independent.

    One ``TRUNCATE`` over all 27 tables is a single statement and ignores foreign-key
    ordering (``CASCADE``), which is both faster and less fragile than 27 DELETEs.
    ``master.roles`` is reference data, so it is put straight back afterwards.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {_ALL_TABLES} RESTART IDENTITY CASCADE"))
        _seed_roles(conn)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The in-memory rate limiter is process-wide; reset it so a large suite never trips 429."""
    from app.core.rate_limit import _MemoryBackend, rate_limiter

    rate_limiter._backend = _MemoryBackend()
    rate_limiter._tried_redis = True  # never try to reach Redis from tests
    yield


#: What every host resolves to while the network guard is on: a public documentation
#: address (TEST-NET-3 is not "global", so example.com's address is used), so the board
#: detector's public-address check passes and the refusing transport decides.
TEST_PUBLIC_IP = "93.184.215.14"


@pytest.fixture(autouse=True)
def _no_job_board_network():
    """The default suite never calls the real public job boards or company websites.

    Every board request goes through ``app.modules.adapters.boards.http``, and every page
    and robots.txt the board detector reads goes through ``companies.board_detect``; both
    are routed to a transport that refuses, and the detector's DNS lookups to a stub, so a
    test that forgets to mock the network fails loudly instead of quietly depending on
    Greenhouse (or a company website) being up. Tests that need answers install their own
    ``httpx.MockTransport``; the opt-in live tests restore the network.
    """
    import httpx

    from app.modules.adapters.boards import http as board_http
    from app.modules.companies import board_detect

    def _refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"network access to {request.url.host} is disabled in tests", request=request)

    board_http.clear_cache()
    board_http.set_transport(httpx.MockTransport(_refuse))
    board_detect.set_transport(httpx.MockTransport(_refuse))
    board_detect.set_resolver(lambda host: [TEST_PUBLIC_IP])
    yield
    board_http.set_transport(None)
    board_detect.set_transport(None)
    board_detect.set_resolver(None)
    board_http.clear_cache()


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
