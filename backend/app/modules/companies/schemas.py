"""Company + company-preference schemas (contract §4)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CompanyPriority

#: The ATS vendors with a public job board API JobPilot can read.
BoardAtsType = Literal["GREENHOUSE", "LEVER", "ASHBY", "SMARTRECRUITERS"]
#: How a board was found: the bundled known list, a token guess, a careers page scan, or not at all.
DetectionMethod = Literal["KNOWN", "GUESS", "SCAN", "NONE"]


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
    ats_board_token: str | None = None
    ats_board_url: str | None = None
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


class CompanyBoardUpdate(BaseModel):
    """Body of ``PUT /companies/{id}/board``.

    ``board_url`` is the company's public board URL on that ATS (or just its token, e.g.
    ``"stripe"``). The board is fetched once to verify it before anything is saved.
    """

    ats_type: BoardAtsType
    board_url: str = Field(min_length=1, max_length=500)


class CompanyBoardResult(BaseModel):
    """The saved company plus how many open postings its board had when it was verified."""

    company: CompanyRead
    board_job_count: int


class CompanyCreate(BaseModel):
    """Body of ``POST /companies``: add a company the registry does not know yet.

    ``board_url`` is optional; when given, ``ats_type`` may be omitted if the URL's host
    names the vendor (``jobs.lever.co/...`` → ``LEVER``). A bare token needs ``ats_type``.
    """

    name: str = Field(min_length=1, max_length=255)
    website: str | None = Field(default=None, max_length=500)
    board_url: str | None = Field(default=None, max_length=500)
    ats_type: BoardAtsType | None = None
    #: Without a ``board_url``, look the board up (known list, token guess, careers page scan)
    #: and store it when one is found. Skipped when the company already has a board.
    auto_detect: bool = True


class BoardDetectRequest(BaseModel):
    """Body of ``POST /companies/detect-board``: at least one of the two is required."""

    name: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=500)


class BoardDetection(BaseModel):
    """What board auto-detection found for a company (``companies.board_detect``).

    ``ats_type`` is one of the four readable vendors, ``WORKDAY`` (recognised on a careers
    page but not readable - ``supported`` is false and nothing is stored as a board), or
    ``None`` with ``method="NONE"`` when nothing was found; ``tried`` then lists every
    lookup, guess and page that was checked, so the UI can offer the manual board URL field.
    """

    ats_type: str | None = None
    token: str | None = None
    board_url: str | None = None
    method: DetectionMethod = "NONE"
    #: Open postings counted by the verification fetch (``None`` when not verified).
    open_jobs: int | None = None
    tried: list[str] = Field(default_factory=list)
    #: The company name the vendor's board itself shows (Greenhouse and SmartRecruiters
    #: report it), so a guessed board that belongs to a namesake is easy to spot.
    board_company: str | None = None
    #: The company's careers page, when the scan saw one.
    careers_url: str | None = None
    #: Whether JobPilot can read this board (false for Workday and for no result).
    supported: bool = False
    #: HTTP requests the detection made (never more than 8).
    requests: int = 0


class CompanyDetectResult(CompanyRead):
    """``POST /companies`` and ``POST /companies/{id}/detect-board``: the company plus the detection.

    ``detection`` is ``None`` when none ran (a ``board_url`` was given, ``auto_detect`` was
    off, or the company already had a board). ``detection_saved`` says whether the result
    was written to the company.
    """

    detection: BoardDetection | None = None
    detection_saved: bool = False


class CompanySuggestion(BaseModel):
    """One company of the bundled known-board list, offered by the Companies "Quick start" panel."""

    name: str
    domain: str | None = None
    ats_type: BoardAtsType
    token: str
    board_url: str
    tags: list[str] = Field(default_factory=list)
    #: The registry row with this name, when there is one.
    company_id: uuid.UUID | None = None
    #: Whether that row already has a board configured (adding it then needs no network).
    board_configured: bool = False


class CompanySuggestions(BaseModel):
    """``GET /companies/suggestions``."""

    items: list[CompanySuggestion] = Field(default_factory=list)
    #: Companies on the user's list (any priority but AVOID) whose board is configured.
    board_companies: int = 0
    #: True while ``board_companies`` is below the quick-start threshold (3).
    show_quick_start: bool = True
