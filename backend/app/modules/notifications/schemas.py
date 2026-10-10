"""Notification schemas (contract §5)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import NotificationType


class NotificationRead(BaseModel):
    # ``Notification.meta`` maps to the DB column "metadata"; the API exposes "metadata".
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    type: NotificationType
    title: str
    body: str | None = None
    link: str | None = None
    is_read: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="meta")
    created_at: datetime


class MarkAllReadResponse(BaseModel):
    ok: bool = True
    updated: int = 0
