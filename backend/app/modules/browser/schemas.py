"""Pydantic schemas for the browser automation module (spec / CONTRACTS.md §12).

These shapes are shared with the applications module (``ApplicationRunner``) and are
serialised verbatim into ``Application.form_snapshot``, so keep them stable.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict

from app.models.enums import BrowserSessionStatus, FieldType, JobSourceType, PauseReason

# --------------------------------------------------------------------------- detection


class FieldOption(BaseModel):
    """One choice of a select element or radio group."""

    value: str
    label: str
    selector: str | None = None  # concrete element selector (radio options)


class DetectedField(BaseModel):
    """A single form control discovered on a page."""

    selector: str
    label: str | None = None
    name: str | None = None
    id: str | None = None
    placeholder: str | None = None
    field_type: FieldType = FieldType.TEXT
    required: bool = False
    options: list[FieldOption] = Field(default_factory=list)
    autocomplete: str | None = None
    section: str | None = None

    @property
    def option_labels(self) -> list[str]:
        return [o.label for o in self.options]

    @property
    def option_values(self) -> list[str]:
        return [o.value for o in self.options]

    def text_blob(self) -> str:
        """Everything a human/rule would read to understand this field."""
        return " ".join(p for p in (self.label, self.name, self.id, self.placeholder, self.section) if p)


class Blocker(BaseModel):
    """Something that makes unattended automation impossible: we pause, never bypass."""

    kind: PauseReason
    selector: str | None = None
    message: str


class DetectedForm(BaseModel):
    url: str = ""
    fields: list[DetectedField] = Field(default_factory=list)
    submit_selector: str | None = None
    blockers: list[Blocker] = Field(default_factory=list)

    def field_by_selector(self, selector: str) -> DetectedField | None:
        return next((f for f in self.fields if f.selector == selector), None)

    @property
    def has_blockers(self) -> bool:
        return bool(self.blockers)


# --------------------------------------------------------------------------- mapping


class Mapping(BaseModel):
    """Result of mapping one detected field onto a canonical profile key (§11)."""

    canonical_key: str | None = None
    confidence: float = 0.0
    reason: str = ""
    is_sensitive: bool = False


class MappedField(BaseModel):
    field: DetectedField
    mapping: Mapping


# --------------------------------------------------------------------------- filling


# Plain ``TypedDict`` rows (not models): a FillResult is copied verbatim into
# ``Application.form_snapshot``, a JSON column, so every row must survive json.dumps.
class FilledField(TypedDict):
    selector: str
    key: str | None
    value_preview: str
    field_type: str


class SkippedField(TypedDict):
    selector: str
    key: str | None
    label: str | None
    required: bool
    reason: str


class FillResult(BaseModel):
    filled: list[FilledField] = Field(default_factory=list)
    skipped: list[SkippedField] = Field(default_factory=list)
    needs_user: list[SkippedField] = Field(default_factory=list)
    screenshot_path: str | None = None

    @property
    def ok(self) -> bool:
        return not self.needs_user

    def snapshot(self) -> dict[str, Any]:
        """JSON-safe summary for ``Application.form_snapshot``."""
        return self.model_dump(mode="json")


# --------------------------------------------------------------------------- API


class BrowserSessionRead(BaseModel):
    """A stored browser context. The encrypted storage state is never exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: JobSourceType
    status: BrowserSessionStatus
    user_agent: str | None = None
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    has_stored_state: bool = False


class BrowserStatus(BaseModel):
    available: bool
    headless: bool
