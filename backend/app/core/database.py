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


def _make_engine(url: str) -> Engine:
    kwargs: dict = {"echo": settings.DB_ECHO, "pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        kwargs.update(connect_args={"check_same_thread": False})
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


engine: Engine = _make_engine(settings.DATABASE_URL)
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
