"""Shared response schemas used by every module (contract §0).

``PageResponse[T]`` is the canonical envelope for every paginated list endpoint::

    @router.get("/", response_model=PageResponse[CompanyRead])
    def list_companies(...): ...
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    """Envelope returned by every paginated list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20

    @property
    def pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size


class OkResponse(BaseModel):
    """Generic acknowledgement body for endpoints with nothing better to return."""

    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    message: str | None = None


class CountResponse(BaseModel):
    """``{"count": n}`` — used by unread-count style endpoints."""

    count: int = 0


class ErrorBody(BaseModel):
    """Documents the error envelope produced by ``app.core.exceptions``."""

    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
