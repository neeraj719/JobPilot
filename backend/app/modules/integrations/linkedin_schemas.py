"""LinkedIn connection schemas. Nothing here ever carries a token (encrypted or not)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LinkedInStatusValue = Literal["not_connected", "pending", "connected", "expired", "revoked", "error"]
DiffAction = Literal["add", "replace", "same"]


class LinkedInHistoryCounts(BaseModel):
    positions: int = 0
    education: int = 0
    skills: int = 0
    certifications: int = 0
    languages: int = 0


class LinkedInDiffSummary(BaseModel):
    """What the last sync found (``last_sync_diff``), without the values themselves."""

    synced_at: datetime | None = None
    source: str | None = None
    adds: int = 0
    replaces: int = 0
    same: int = 0
    changes: int = 0
    trigger: str | None = None  # "manual" | "scheduled" | "export"


class LinkedInStatus(BaseModel):
    """State of the user's LinkedIn connection (safe to expose: no tokens, no state)."""

    configured: bool = False
    dma_enabled: bool = False
    status: LinkedInStatusValue = "not_connected"
    connected: bool = False
    name: str | None = None
    email: str | None = None
    picture_url: str | None = None
    locale: str | None = None
    scopes: list[str] = Field(default_factory=list)
    dma_granted: bool = False
    #: Why the full history is missing when DMA was requested but did not answer.
    dma_error: str | None = None
    connected_at: datetime | None = None
    token_expires_at: datetime | None = None
    last_synced_at: datetime | None = None
    auto_sync: bool = True
    auto_sync_hours: int = 24
    snapshot_source: str | None = None
    #: ``dma`` / ``export`` when positions, education… are available; ``None`` = basics only.
    history_source: str | None = None
    history_counts: LinkedInHistoryCounts = Field(default_factory=LinkedInHistoryCounts)
    export_imported_at: datetime | None = None
    export_stale: bool = False
    export_stale_days: int = 90
    last_error: str | None = None
    pending_changes: int = 0
    last_sync_diff: LinkedInDiffSummary | None = None


class LinkedInDiffRow(BaseModel):
    """One proposed change to the master profile."""

    id: str
    field: str
    label: str
    group: str  # "basics" | "experience" | "education" | "skills" | "certifications" | "languages"
    key: str | None = None
    current: Any = None
    incoming: Any = None
    action: DiffAction
    #: Ticked by default in the review dialog (additions yes, conflicts no).
    default_selected: bool = False


class LinkedInDiff(BaseModel):
    source: str | None = None
    history_source: str | None = None
    rows: list[LinkedInDiffRow] = Field(default_factory=list)
    adds: int = 0
    replaces: int = 0
    same: int = 0
    changes: int = 0


class LinkedInSyncResult(BaseModel):
    status: LinkedInStatus
    diff: LinkedInDiff
    #: Plain-language notes for the card ("Only your basics were shared…", "export is 120 days old").
    notes: list[str] = Field(default_factory=list)


class LinkedInApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_ids: list[str] = Field(default_factory=list, max_length=2000)


class LinkedInApplyResult(BaseModel):
    applied: int = 0
    fields: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    status: LinkedInStatus
    diff: LinkedInDiff


class LinkedInUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_sync: bool


class LinkedInResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    target_role: str | None = Field(default=None, max_length=255)
    template: str | None = Field(default=None, max_length=40)
    set_default: bool = False
