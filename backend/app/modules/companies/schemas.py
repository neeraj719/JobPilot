"""Company + company-preference schemas (contract §4)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CompanyPriority


class CompanyRead(BaseModel):
    """A company plus the current user's view of it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    normalized_name: str
    domain: str | None = None
    email_domains: list[Any] = Field(default_factory=list)
    website: str | None = None
    careers_url: str | None = None
    logo_url: str | None = None
    industry: str | None = None
    size: str | None = None
    headquarters: str | None = None
    description: str | None = None
    ats_type: str | None = None
    tags: list[Any] = Field(default_factory=list)
    created_at: datetime | None = None

    # per-user enrichment
    priority: CompanyPriority | None = None
    open_jobs: int = 0
    applications: int = 0


class CompanyPreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None = None
    company_name: str
    normalized_name: str
    priority: CompanyPriority
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CompanyPreferenceItem(BaseModel):
    """One row of the user's priority list.

    Blank-after-normalisation names are rejected by the service (``ValidationFailed``)
    rather than by a pydantic validator - see the note in ``auth/schemas.py``.
    """

    company_name: str = Field(min_length=1, max_length=255)
    priority: CompanyPriority
    notes: str | None = Field(default=None, max_length=2000)


class CompanyPreferencesReplace(BaseModel):
    items: list[CompanyPreferenceItem] = Field(default_factory=list, max_length=500)
