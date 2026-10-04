"""Declarative base, schema constants and shared mixins.

Types are chosen to be portable between PostgreSQL (production and the test suite)
and SQLite (the no-Docker local run): ``Uuid``, generic ``JSON`` and
``DateTime(timezone=True)``.

Storage layout
--------------
The 27 tables live in five named PostgreSQL schemas rather than in ``public``:

==============  ===========================================================
``master``      slowly-changing reference/ownership data (13 tables)
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

Every one of them also carries the same seven standard columns, from the single
:class:`StandardColumnsMixin`: a uuid ``id`` primary key, the database-owned
``created_at``/``updated_at`` pair, the ``created_by``/``updated_by`` audit pair and the
``is_active``/``deleted_at`` lifecycle pair. Every link between tables is a uuid foreign
key.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, FetchedValue, ForeignKey, MetaData, Uuid, func, text, true
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
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
#: in PostgreSQL and all 27 table names are unique, so nothing can collide.
NAMING_CONVENTION = {"ix": "ix_%(table_name)s_%(column_0_N_name)s"}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}

    def to_dict(self) -> dict[str, Any]:
        return {c.key: getattr(self, c.key) for c in self.__table__.columns}  # type: ignore[attr-defined]


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """``created_at`` / ``updated_at``, owned by the **database** and nothing else.

    There is deliberately no Python-side ``default=``/``onupdate=`` here. One mechanism
    keeps the two timestamps honest, and it is the one that also sees the writes the ORM
    never hears about: a hand-written ``UPDATE``, a psql session, a migration, a bulk
    ``update()`` statement. ``created_at`` comes from ``DEFAULT now()`` on INSERT and
    ``updated_at`` is bumped by the ``trg_<table>_updated_at`` trigger
    (:mod:`app.core.db_triggers`) on every UPDATE that actually changes the row.

    ``server_onupdate=FetchedValue()`` carries no DDL — it is the ORM being told that the
    value changes server-side, so the attribute is expired after a flush and re-read on
    next access instead of going stale in the identity map.

    Consequence worth knowing: ``obj.created_at`` is ``None`` between ``Session.add()``
    and the flush, because the value does not exist until the INSERT runs. Read it after
    ``db.flush()``. Supplying a value explicitly still wins — a server default only
    applies when the INSERT names no value — which is what lets ``app/seed.py`` fabricate
    history on past dates.
    """

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), server_onupdate=FetchedValue(), nullable=False
    )


class AuditUserMixin:
    """Who created and who last changed the row.

    Both are nullable uuids pointing at ``master.users.id`` ``ON DELETE SET NULL``: the
    audit trail must not keep a deleted account alive, and ``NULL`` is a meaningful value
    — it means *no user did this*, i.e. a system/automation/migration write. They are
    stamped from the acting user by the flush listeners in :mod:`app.core.actor`, never
    by hand, and they are **not** API fields: this is a database-level trail, not a
    feature. No index: audit columns are not query paths.

    ``declared_attr`` rather than plain columns because a ``ForeignKey`` object belongs to
    exactly one table, so each mapped class needs its own.
    """

    @declared_attr
    def created_by(cls) -> Mapped[uuid.UUID | None]:  # noqa: N805
        return mapped_column(Uuid, ForeignKey("master.users.id", ondelete="SET NULL"), nullable=True)

    @declared_attr
    def updated_by(cls) -> Mapped[uuid.UUID | None]:  # noqa: N805
        return mapped_column(Uuid, ForeignKey("master.users.id", ondelete="SET NULL"), nullable=True)


class LifecycleMixin:
    """The two lifecycle columns every JobPilot table carries.

    ``is_active`` — a **business** switch, not a delete. A user who has been disabled, a
    job posting that is no longer open, an integration the user paused: the row is still
    real, still referenced and still returned when asked for; it is simply not currently
    in play. It is a normal queryable column and endpoints filter on it explicitly.

    ``deleted_at`` — the **soft-delete tombstone**. ``NULL`` means the row exists; a
    timestamp means it has been deleted and must behave as if it were gone. Nothing
    filters on it by hand: ``app.core.soft_delete`` registers one global ORM filter that
    appends ``deleted_at IS NULL`` to every ORM SELECT (including ``Session.get`` and
    relationship loads) unless the statement opts out with
    ``execution_options(include_deleted=True)``.

    Deleting therefore means :func:`app.core.soft_delete.soft_delete`, which sets *both*:
    ``deleted_at = now()`` **and** ``is_active = False`` — a deleted row is never also
    "active". The pair is not redundant: ``is_active=False, deleted_at=NULL`` is the
    common "paused / closed / disabled but still here" state.

    Append-only tables (``audit_logs``, ``application_events``, ``resume_versions``,
    ``automation_runs``) carry the columns too, purely so that every table has the same
    shape and the global filter needs no exceptions. Nothing ever deletes from them —
    their ``deleted_at`` stays ``NULL`` for the life of the row.

    Soft delete and UNIQUE keys do not mix: a tombstoned row still occupies its unique
    key, so re-creating the thing the user just deleted would fail. Every key a user can
    delete and legitimately re-create is therefore a **partial** unique index
    (``... WHERE deleted_at IS NULL``) rather than a UNIQUE constraint — see
    ``docs/DATABASE.md``.
    """

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class StandardColumnsMixin(UUIDMixin, TimestampMixin, AuditUserMixin, LifecycleMixin):
    """The seven standard columns, in one place, on all 27 tables.

    ===============  =========================================================
    ``id``           uuid primary key (:class:`UUIDMixin`)
    ``created_at``   ``timestamptz NOT NULL DEFAULT now()`` (:class:`TimestampMixin`)
    ``updated_at``   ``timestamptz NOT NULL DEFAULT now()``, bumped by a trigger
    ``created_by``   ``uuid NULL`` -> ``master.users.id`` (:class:`AuditUserMixin`)
    ``updated_by``   ``uuid NULL`` -> ``master.users.id``
    ``is_active``    the business switch (:class:`LifecycleMixin`)
    ``deleted_at``   the soft-delete tombstone
    ===============  =========================================================

    Every model inherits this one mixin rather than picking from the four, so "which
    columns does this table have" has a single answer and a new table cannot quietly
    ship without the audit trail. The four pieces stay separate classes because other
    code targets them by type: ``with_loader_criteria(LifecycleMixin, ...)`` in
    :mod:`app.core.soft_delete` and the stamping listeners on :class:`AuditUserMixin`.
    """


def soft_delete_where(column: str = "deleted_at") -> dict[str, Any]:
    """Keyword arguments making an ``Index`` partial on "not deleted", on both backends.

    PostgreSQL and SQLite both support partial indexes but spell the predicate through
    different dialect keywords, and SQLAlchemy keeps them separate. Passing both from one
    helper means the two can never drift apart::

        Index("uq_roles_name_active", "name", unique=True, **soft_delete_where())
    """
    predicate = text(f"{column} IS NULL")
    return {"postgresql_where": predicate, "sqlite_where": predicate}
