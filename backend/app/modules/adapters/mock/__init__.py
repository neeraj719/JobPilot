"""Mock job platform adapters.

Each adapter serves a deterministic, seeded catalogue of realistic Indian + remote
software postings. No third-party site is contacted and no credential is ever read —
see :mod:`app.modules.adapters.mock.base_mock` for the generator and the terms notes.
"""
from __future__ import annotations

from app.modules.adapters.mock.base_mock import (
    CROSS_POST_SOURCES,
    MOCK_TERMS_NOTE,
    SHARED_POSTINGS,
    BaseMockAdapter,
    build_catalogue,
)
from app.modules.adapters.mock.company_careers import CompanyCareersMockAdapter
from app.modules.adapters.mock.foundit import FounditMockAdapter
from app.modules.adapters.mock.glassdoor import GlassdoorMockAdapter
from app.modules.adapters.mock.hirist import HiristMockAdapter
from app.modules.adapters.mock.indeed import IndeedMockAdapter
from app.modules.adapters.mock.internshala import InternshalaMockAdapter
from app.modules.adapters.mock.linkedin import LinkedInMockAdapter
from app.modules.adapters.mock.naukri import NaukriMockAdapter
from app.modules.adapters.mock.wellfound import WellfoundMockAdapter

MOCK_ADAPTER_CLASSES: tuple[type[BaseMockAdapter], ...] = (
    NaukriMockAdapter,
    LinkedInMockAdapter,
    IndeedMockAdapter,
    HiristMockAdapter,
    WellfoundMockAdapter,
    InternshalaMockAdapter,
    GlassdoorMockAdapter,
    FounditMockAdapter,
    CompanyCareersMockAdapter,
)

__all__ = [
    "BaseMockAdapter",
    "MOCK_ADAPTER_CLASSES",
    "MOCK_TERMS_NOTE",
    "SHARED_POSTINGS",
    "CROSS_POST_SOURCES",
    "build_catalogue",
    "NaukriMockAdapter",
    "LinkedInMockAdapter",
    "IndeedMockAdapter",
    "HiristMockAdapter",
    "WellfoundMockAdapter",
    "InternshalaMockAdapter",
    "GlassdoorMockAdapter",
    "FounditMockAdapter",
    "CompanyCareersMockAdapter",
]
