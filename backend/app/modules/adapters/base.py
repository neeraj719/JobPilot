"""Job source adapter contract (see ``docs/CONTRACTS.md`` §8).

Every platform JobPilot can discover jobs from — mock platforms, the local demo ATS
and the Greenhouse/Lever style ATS stubs — implements :class:`JobSourceAdapter`.

Design notes
------------
* The dataclasses below are the *only* shape the rest of the backend sees. Adapters
  normalise whatever their upstream returns into :class:`DiscoveredJob`.
* Nothing in this module imports Playwright. Browser usage lives behind lazy imports
  inside the concrete adapters so ``import app.modules.adapters`` stays cheap and
  works in environments without a browser.
* Adapters never bypass CAPTCHA / OTP / 2FA / anti-bot systems. When they detect one
  they return ``AutomationState.REQUIRES_USER`` with the matching
  :class:`~app.models.enums.PauseReason` so a human can take over.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.enums import (
    ApplicationStatus,
    ApplicationType,
    AutomationState,
    EmploymentType,
    JobSourceType,
    PauseReason,
    WorkMode,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- data shapes


@dataclass
class DiscoveredJob:
    """Normalised output of :meth:`JobSourceAdapter.search_jobs`."""

    source: JobSourceType
    external_id: str
    url: str
    title: str
    company_name: str
    location: str | None = None
    work_mode: WorkMode | None = None
    employment_type: EmploymentType | None = None
    description: str = ""
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    experience_min: float | None = None
    experience_max: float | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    posted_at: datetime | None = None
    apply_url: str | None = None
    application_type: ApplicationType = ApplicationType.UNKNOWN
    company_domain: str | None = None
    company_logo_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchQuery:
    """What the user is looking for, built from their :class:`JobPreference`."""

    titles: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    posted_within_hours: int | None = None
    limit: int = 50
    work_modes: list[WorkMode] = field(default_factory=list)


@dataclass
class ApplyContext:
    """Everything an adapter needs to drive one application step.

    ``page`` is a Playwright ``Page`` for browser based adapters and ``None`` for mock
    adapters. Typed as ``Any`` so importing this module never needs Playwright.
    """

    application: Any = None
    job: Any = None
    candidate: Any = None
    answers: list[Any] = field(default_factory=list)
    page: Any = None
    db: Any = None
    settings: Any = None


@dataclass
class ApplyStepResult:
    """Outcome of one automation step (start / fill / submit)."""

    state: AutomationState
    message: str = ""
    pause_reason: PauseReason | None = None
    form_snapshot: dict[str, Any] | None = None
    external_application_id: str | None = None
    confirmation_message: str | None = None
    screenshot_path: str | None = None

    @property
    def ok(self) -> bool:
        return self.state == AutomationState.SUCCESS


@dataclass
class AuthResult:
    """Result of (re)establishing a session with a platform.

    Mock adapters always return ``ok=True, is_mock=True`` and never read credentials.
    """

    ok: bool
    message: str = ""
    is_mock: bool = False
    requires_user: bool = False
    pause_reason: PauseReason | None = None


@dataclass
class AdapterInfo:
    """Public description of an adapter (surfaced by ``GET /jobs/sources``)."""

    source: JobSourceType
    display_name: str
    is_mock: bool
    supports_auto_apply: bool
    requires_account: bool
    terms_note: str
    rate_limit_per_minute: int = 60
    uses_browser: bool = False


# --------------------------------------------------------------------------- helpers

#: Platforms that host the application inside their own product ("easy apply").
PLATFORM_INTERNAL_SOURCES: frozenset[JobSourceType] = frozenset(
    {
        JobSourceType.LINKEDIN,
        JobSourceType.NAUKRI,
        JobSourceType.INDEED,
        JobSourceType.HIRIST,
        JobSourceType.WELLFOUND,
        JobSourceType.INTERNSHALA,
        JobSourceType.GLASSDOOR,
        JobSourceType.FOUNDIT,
    }
)

#: Sources that are always an ATS style hosted form.
ATS_SOURCES: frozenset[JobSourceType] = frozenset(
    {JobSourceType.GREENHOUSE, JobSourceType.LEVER, JobSourceType.WORKDAY, JobSourceType.DEMO_ATS}
)

#: Fragments in an apply URL that identify a hosted ATS form.
ATS_URL_MARKERS: tuple[str, ...] = (
    "greenhouse.io",
    "boards.greenhouse",
    "lever.co",
    "jobs.lever",
    "myworkdayjobs.com",
    "workday.com",
    "/demo-ats/",
    "smartrecruiters.com",
    "ashbyhq.com",
)


def detect_application_type(
    apply_url: str | None,
    source: JobSourceType,
    *,
    url: str | None = None,
) -> ApplicationType:
    """Best-effort classification of how an application has to be submitted.

    * Greenhouse / Lever / Workday / demo ATS (by source **or** URL) → ``ATS_FORM``
    * Platform internal apply URL on an "easy apply" platform → ``EASY_APPLY``
    * Anything else → ``EXTERNAL_FORM``
    """
    target = (apply_url or url or "").lower()
    if source in ATS_SOURCES:
        return ApplicationType.ATS_FORM
    if any(marker in target for marker in ATS_URL_MARKERS):
        return ApplicationType.ATS_FORM
    if source in PLATFORM_INTERNAL_SOURCES:
        host_marker = _PLATFORM_HOST_MARKERS.get(source)
        if not target or (host_marker and host_marker in target):
            return ApplicationType.EASY_APPLY
        return ApplicationType.EXTERNAL_FORM
    return ApplicationType.EXTERNAL_FORM


_PLATFORM_HOST_MARKERS: dict[JobSourceType, str] = {
    JobSourceType.LINKEDIN: "linkedin.com",
    JobSourceType.NAUKRI: "naukri.com",
    JobSourceType.INDEED: "indeed.com",
    JobSourceType.HIRIST: "hirist.",
    JobSourceType.WELLFOUND: "wellfound.com",
    JobSourceType.INTERNSHALA: "internshala.com",
    JobSourceType.GLASSDOOR: "glassdoor.",
    JobSourceType.FOUNDIT: "foundit.in",
}


# --------------------------------------------------------------------------- the ABC


class JobSourceAdapter(ABC):
    """Base class for every job source.

    Subclasses set the class attributes and implement :meth:`search_jobs`. The
    application steps have safe defaults so read-only adapters stay tiny.
    """

    source: JobSourceType = JobSourceType.OTHER
    display_name: str = "Unknown"
    is_mock: bool = True
    supports_auto_apply: bool = False
    requires_account: bool = False
    rate_limit_per_minute: int = 60
    uses_browser: bool = False
    terms_note: str = (
        "A production implementation must use the platform's official API, honour its Terms of "
        "Service and robots.txt, stay inside documented rate limits, act only inside a session the "
        "user owns and never attempt to bypass CAPTCHA, OTP or bot detection."
    )

    # -- discovery ---------------------------------------------------------

    @abstractmethod
    def search_jobs(self, query: SearchQuery) -> list[DiscoveredJob]:
        """Return jobs matching ``query``. Must never raise for an empty result."""

    def get_job_details(self, external_id: str) -> DiscoveredJob | None:
        """Fetch one posting by its platform id. Defaults to a catalogue scan."""
        for job in self.search_jobs(SearchQuery(limit=500)):
            if job.external_id == external_id:
                return job
        return None

    # -- session -----------------------------------------------------------

    def authenticate(self, session: Any | None = None, credentials: dict[str, Any] | None = None) -> AuthResult:
        """Establish/verify a platform session.

        The base implementation is a no-op that deliberately ignores ``credentials``.
        """
        return AuthResult(ok=True, message=f"{self.display_name} needs no authentication", is_mock=self.is_mock)

    # -- classification ----------------------------------------------------

    def detect_application_type(self, job: DiscoveredJob) -> ApplicationType:
        return detect_application_type(job.apply_url, job.source or self.source, url=job.url)

    # -- application steps -------------------------------------------------

    def start_application(self, ctx: ApplyContext) -> ApplyStepResult:
        return ApplyStepResult(
            state=AutomationState.FAILED,
            message=f"{self.display_name} does not support automated applications",
        )

    def fill_application(self, ctx: ApplyContext) -> ApplyStepResult:
        return ApplyStepResult(
            state=AutomationState.FAILED,
            message=f"{self.display_name} does not support automated applications",
        )

    def submit_application(self, ctx: ApplyContext) -> ApplyStepResult:
        return ApplyStepResult(
            state=AutomationState.FAILED,
            message=f"{self.display_name} does not support automated applications",
        )

    def get_application_status(self, external_application_id: str) -> ApplicationStatus | None:
        """Platforms rarely expose this; ``None`` means "unknown, track via email"."""
        return None

    # -- metadata ----------------------------------------------------------

    def info(self) -> AdapterInfo:
        return AdapterInfo(
            source=self.source,
            display_name=self.display_name,
            is_mock=self.is_mock,
            supports_auto_apply=self.supports_auto_apply,
            requires_account=self.requires_account,
            terms_note=self.terms_note,
            rate_limit_per_minute=self.rate_limit_per_minute,
            uses_browser=self.uses_browser,
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<{type(self).__name__} source={self.source.value}>"
