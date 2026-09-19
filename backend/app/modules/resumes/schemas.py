"""Resume API schemas (CONTRACTS.md §7).

``ParsedResume`` (and its nested entries) is owned by the AI module and re-exported
here so the frontend sees one shape for parsed resume data everywhere.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ResumeParseStatus
from app.modules.ai.schemas import (
    CertificationEntry,
    EducationEntry,
    ExperienceEntry,
    Links,
    ParsedResume,
    ProjectEntry,
)


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    target_role: str | None = None
    is_default: bool = False
    original_filename: str
    mime_type: str
    size_bytes: int
    parse_status: ResumeParseStatus
    parse_error: str | None = None
    parsed_at: datetime | None = None
    # ``ParsedResume``-shaped; ``{}`` until the resume has been parsed.
    parsed_data: dict[str, Any] = Field(default_factory=dict)
    current_version: int = 1
    created_at: datetime
    updated_at: datetime

    @field_validator("parsed_data", mode="before")
    @classmethod
    def _default_parsed(cls, v: Any) -> dict[str, Any]:
        return v or {}


class ResumeUpdate(BaseModel):
    """PATCH body — every field optional."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    target_role: str | None = Field(default=None, max_length=255)
    is_default: bool | None = None


class ResumeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_id: uuid.UUID
    version_number: int
    parsed_data: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None
    created_at: datetime

    @field_validator("parsed_data", mode="before")
    @classmethod
    def _default_parsed(cls, v: Any) -> dict[str, Any]:
        return v or {}


__all__ = [
    "CertificationEntry",
    "EducationEntry",
    "ExperienceEntry",
    "Links",
    "ParsedResume",
    "ProjectEntry",
    "ResumeRead",
    "ResumeUpdate",
    "ResumeVersionRead",
]
