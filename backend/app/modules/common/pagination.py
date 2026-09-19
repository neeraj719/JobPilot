"""Pagination dependency + helper shared by every list endpoint (contract §0).

Usage::

    @router.get("/", response_model=PageResponse[CompanyRead])
    def list_companies(pagination: Pagination = Depends(), db: Session = Depends(get_db)):
        return paginate(db, select(Company).order_by(Company.name), pagination)
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.common.schemas import PageResponse

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class Pagination:
    """FastAPI dependency carrying ``page`` (1-based) and ``page_size`` (1..100)."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-based page number"),
        page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page (max 100)"),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Pagination(page={self.page}, page_size={self.page_size})"


def count_stmt(stmt: Select[Any]) -> Select[Any]:
    """Build a ``SELECT count(*)`` for an arbitrary select statement."""
    return select(func.count()).select_from(stmt.order_by(None).limit(None).offset(None).subquery())


def _selects_whole_entities(stmt: Select[Any]) -> bool:
    """True for ``select(Model)`` (needs ``.unique()`` when joined eager loads are used)
    but False for ``select(Model.column)``, where de-duplicating would drop real rows."""
    try:
        descriptions = stmt.column_descriptions
    except Exception:  # pragma: no cover - defensive
        return False
    if not descriptions:
        return False
    first = descriptions[0]
    return first.get("entity") is not None and first.get("expr") is first.get("entity")


def paginate(
    db: Session,
    stmt: Select[Any],
    pagination: Pagination,
    *,
    transform: Callable[[Any], Any] | None = None,
) -> PageResponse[Any]:
    """Run ``stmt`` for one page and return a :class:`PageResponse`.

    ``transform`` optionally maps every ORM row to a read schema.
    """
    total = int(db.scalar(count_stmt(stmt)) or 0)
    result = db.scalars(stmt.offset(pagination.offset).limit(pagination.limit))
    if _selects_whole_entities(stmt):
        result = result.unique()
    rows: Sequence[Any] = result.all()
    items = [transform(row) for row in rows] if transform else list(rows)
    return PageResponse(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


def paginate_sequence(items: Sequence[Any], pagination: Pagination) -> PageResponse[Any]:
    """Paginate an already-materialised list (used when ranking happens in Python)."""
    total = len(items)
    start = pagination.offset
    window = list(items[start : start + pagination.page_size])
    return PageResponse(items=window, total=total, page=pagination.page, page_size=pagination.page_size)
