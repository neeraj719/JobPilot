"""Declarative base and shared mixins.

Types are chosen to be portable between PostgreSQL (production) and SQLite (unit
tests): ``Uuid``, generic ``JSON`` and ``DateTime(timezone=True)``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


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


class Base(DeclarativeBase):
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
