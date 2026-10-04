"""Declarative base, schema constants and shared mixins.

Types are chosen to be portable between PostgreSQL (production and the test suite)
and SQLite (the no-Docker local run): ``Uuid``, generic ``JSON`` and
``DateTime(timezone=True)``.

Storage layout
--------------
The 25 tables live in five named PostgreSQL schemas rather than in ``public``:

==============  ===========================================================
``master``      slowly-changing reference/ownership data (11 tables)
``unified``     the de-duplicated job graph shared by every user (3 tables)
``transaction`` high-churn per-application event data (7 tables)
``media``       uploaded and generated documents (3 tables)
``audit``       the append-only audit trail (1 table)
==============  ===========================================================

Models name their schema *symbolically* via these constants. SQLite has no
schemas, so ``app.core.database`` puts a ``schema_translate_map`` mapping all five
to ``None`` on a SQLite engine; every table name is unique, so they coexist in the
single SQLite namespace. Nothing outside this module and ``database.py`` needs to
know which backend is in use.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


#: Named PostgreSQL schemas. Referenced symbolically by every model so that the
#: SQLite ``schema_translate_map`` can collapse them to ``None``.
SCHEMA_MASTER = "master"
SCHEMA_UNIFIED = "unified"
SCHEMA_TRANSACTION = "transaction"
SCHEMA_MEDIA = "media"
SCHEMA_AUDIT = "audit"

#: Every schema JobPilot owns, in creation order. Iterated by the engine factory,
#: Alembic and the test fixtures — never hardcode the list again.
SCHEMAS: tuple[str, ...] = (SCHEMA_MASTER, SCHEMA_UNIFIED, SCHEMA_TRANSACTION, SCHEMA_MEDIA, SCHEMA_AUDIT)

#: Maps every JobPilot schema onto "no schema at all", for backends without them.
SQLITE_SCHEMA_TRANSLATE_MAP: dict[str, None] = {schema: None for schema in SCHEMAS}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """``DateTime(timezone=True)`` that is *always* timezone-aware UTC in Python.

    PostgreSQL round-trips ``timestamptz`` faithfully, but SQLite (the dev/demo and
    test database) has no time-zone type: it stores the rendered timestamp and hands
    the value back **naive**. Pydantic then serialises it without an offset, which
    breaks contract §0 ("datetimes are timezone-aware UTC, ISO-8601 in JSON") and makes
    every client read UTC instants as local time — a 5h30m shift in Asia/Kolkata.

    So: normalise to UTC on the way in (an aware non-UTC value is converted rather than
    truncated, a naive one is assumed to already be UTC) and re-attach ``timezone.utc``
    on the way out when the driver lost it. The column type is unchanged at the DDL
    level (``impl`` is the same ``DateTime(timezone=True)``), so there is no migration.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value


#: SQLAlchemy's default name for an ``index=True`` column is ``ix_%(column_0_label)s``,
#: and the label picks up the table's schema — so simply moving a table would rename
#: every one of its implicit indexes (``ix_users_email`` -> ``ix_master_users_email``).
#: Pinning the convention to "table + column" keeps the physical names the initial
#: migration created, so the schema move stays a pure ``ALTER TABLE ... SET SCHEMA``
#: and ``--autogenerate`` has nothing to drop and recreate. Index names are per-schema
#: in PostgreSQL and all 25 table names are unique, so nothing can collide.
NAMING_CONVENTION = {"ix": "ix_%(table_name)s_%(column_0_N_name)s"}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}

    def to_dict(self) -> dict[str, Any]:
        return {c.key: getattr(self, c.key) for c in self.__table__.columns}  # type: ignore[attr-defined]


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )
