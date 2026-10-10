"""Job source adapters (``docs/CONTRACTS.md`` §8).

Public surface::

    from app.modules.adapters.base import DiscoveredJob, SearchQuery, ApplyContext, ApplyStepResult
    from app.modules.adapters.registry import get_adapter, list_adapters, get_enabled_adapters
"""
from __future__ import annotations

from app.modules.adapters.base import (
    AdapterInfo,
    ApplyContext,
    ApplyStepResult,
    AuthResult,
    DiscoveredJob,
    JobSourceAdapter,
    SearchQuery,
)

__all__ = [
    "AdapterInfo",
    "ApplyContext",
    "ApplyStepResult",
    "AuthResult",
    "DiscoveredJob",
    "JobSourceAdapter",
    "SearchQuery",
]
