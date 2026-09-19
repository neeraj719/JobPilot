"""Audit log schemas (contract §5)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Actor, AuditLevel


class AuditLogRead(BaseModel):
    # ``AuditLog.meta`` maps to the DB column "metadata"; the API exposes "metadata".
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    actor: Actor
    level: AuditLevel
    action: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="meta")
    application_id: uuid.UUID | None = None
    automation_run_id: uuid.UUID | None = None
    created_at: datetime
