"""Adapter registry — the single place that maps a :class:`JobSourceType` to its adapter."""
from __future__ import annotations

import logging
from functools import lru_cache

from app.core.exceptions import NotFoundError
from app.models.enums import JobSourceType
from app.modules.adapters.base import AdapterInfo, JobSourceAdapter
from app.modules.adapters.boards import BOARD_SOURCES, AshbyAdapter, SmartRecruitersAdapter
from app.modules.adapters.demo_ats import DemoAtsAdapter
from app.modules.adapters.greenhouse import GreenhouseAdapter
from app.modules.adapters.lever import LeverAdapter
from app.modules.adapters.mock import (
    CompanyCareersMockAdapter,
    FounditMockAdapter,
    GlassdoorMockAdapter,
    HiristMockAdapter,
    IndeedMockAdapter,
    InternshalaMockAdapter,
    LinkedInMockAdapter,
    NaukriMockAdapter,
    WellfoundMockAdapter,
)

logger = logging.getLogger(__name__)

#: Every adapter JobPilot knows about, in the order they should be presented.
ADAPTERS: dict[JobSourceType, type[JobSourceAdapter]] = {
    JobSourceType.LINKEDIN: LinkedInMockAdapter,
    JobSourceType.NAUKRI: NaukriMockAdapter,
    JobSourceType.INDEED: IndeedMockAdapter,
    JobSourceType.HIRIST: HiristMockAdapter,
    JobSourceType.WELLFOUND: WellfoundMockAdapter,
    JobSourceType.INTERNSHALA: InternshalaMockAdapter,
    JobSourceType.GLASSDOOR: GlassdoorMockAdapter,
    JobSourceType.FOUNDIT: FounditMockAdapter,
    JobSourceType.COMPANY_CAREERS: CompanyCareersMockAdapter,
    JobSourceType.DEMO_ATS: DemoAtsAdapter,
    JobSourceType.GREENHOUSE: GreenhouseAdapter,
    JobSourceType.LEVER: LeverAdapter,
    JobSourceType.ASHBY: AshbyAdapter,
    JobSourceType.SMARTRECRUITERS: SmartRecruitersAdapter,
}

#: Sources backed by a deterministic mock catalogue (no network access).
MOCK_SOURCES: tuple[JobSourceType, ...] = tuple(source for source, cls in ADAPTERS.items() if cls.is_mock)

#: Real public job boards (Greenhouse, Lever, Ashby, SmartRecruiters). They read the boards of
#: the companies configured in ``companies.ats_board_token`` and return ``[]`` without one.
BOARD_SOURCES: tuple[JobSourceType, ...] = tuple(source for source in BOARD_SOURCES if source in ADAPTERS)

#: Sources that can actually discover jobs.
DISCOVERY_SOURCES: tuple[JobSourceType, ...] = MOCK_SOURCES + (JobSourceType.DEMO_ATS,) + BOARD_SOURCES


def _coerce(source: JobSourceType | str) -> JobSourceType:
    if isinstance(source, JobSourceType):
        return source
    try:
        return JobSourceType(str(source).upper())
    except ValueError as exc:
        raise NotFoundError(f"Unknown job source '{source}'", code="unknown_source") from exc


@lru_cache(maxsize=None)
def _adapter_instance(source: JobSourceType) -> JobSourceAdapter:
    cls = ADAPTERS[source]
    return cls()


def get_adapter(source: JobSourceType | str) -> JobSourceAdapter:
    """Return the (cached, stateless) adapter for ``source``."""
    resolved = _coerce(source)
    if resolved not in ADAPTERS:
        raise NotFoundError(f"No adapter registered for '{resolved.value}'", code="unknown_source")
    return _adapter_instance(resolved)


def list_adapters() -> list[AdapterInfo]:
    """Public metadata for every registered adapter."""
    return [_adapter_instance(source).info() for source in ADAPTERS]


def get_enabled_adapters(sources: list[JobSourceType] | list[str] | None = None) -> list[JobSourceAdapter]:
    """Resolve the adapters for ``sources``.

    ``None`` (or an empty list) means "everything that can discover jobs". Unknown or
    unregistered sources are skipped with a warning rather than failing the whole run.
    """
    if not sources:
        return [_adapter_instance(source) for source in DISCOVERY_SOURCES]
    adapters: list[JobSourceAdapter] = []
    seen: set[JobSourceType] = set()
    for source in sources:
        try:
            resolved = _coerce(source)
        except NotFoundError:
            logger.warning("Ignoring unknown job source %r", source)
            continue
        if resolved in seen:
            continue
        if resolved not in ADAPTERS:
            logger.warning("No adapter registered for source %s; skipping", resolved.value)
            continue
        seen.add(resolved)
        adapters.append(_adapter_instance(resolved))
    return adapters
