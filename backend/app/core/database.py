"""SQLAlchemy engine/session management.

Sync SQLAlchemy 2.0 is used throughout. FastAPI runs sync endpoints in a
threadpool, and the Playwright automation uses the sync API in worker threads,
so a single blocking session model keeps the codebase simple and predictable.
"""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.base import SQLITE_SCHEMA_TRANSLATE_MAP


def make_engine(url: str, *, echo: bool | None = None) -> Engine:
    """Build an engine for ``url``, teaching SQLite to ignore the named schemas.

    The models name five PostgreSQL schemas (``master``, ``unified``, ``transaction``,
    ``media``, ``audit``). SQLite has no such concept, so a SQLite engine carries a
    ``schema_translate_map`` that rewrites every one of them to "no schema" at
    statement-compile time. All 25 table names are unique, so they coexist happily in
    SQLite's single namespace and no model or query has to branch on the backend.
    PostgreSQL gets no map at all — the schema names in the SQL are the real ones.
    """
    kwargs: dict = {"echo": settings.DB_ECHO if echo is None else echo, "pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        kwargs.update(connect_args={"check_same_thread": False}, execution_options={"schema_translate_map": SQLITE_SCHEMA_TRANSLATE_MAP})
        if ":memory:" in url:
            kwargs.update(poolclass=StaticPool)
    else:
        kwargs.update(pool_size=10, max_overflow=20)
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        file_backed = ":memory:" not in url

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            if file_backed:
                # A file-backed SQLite database (the local demo DB) is written concurrently by
                # the API, the automation threads and the bundled demo ATS. WAL lets readers and
                # one writer coexist, and the busy timeout absorbs the rest, instead of failing
                # outright with "database is locked".
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=10000")
                cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return eng


#: Backwards-compatible private alias (the factory used to be private).
_make_engine = make_engine

engine: Engine = make_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for background jobs / scripts."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
