"""Glassdoor mock adapter — deterministic catalogue, no network access."""
from __future__ import annotations

from app.models.enums import JobSourceType
from app.modules.adapters.mock.base_mock import BaseMockAdapter


class GlassdoorMockAdapter(BaseMockAdapter):
    """Glassdoor job source (mock).

    Listings redirect to the employer's own form, so auto-apply is not supported here.
    """

    source = JobSourceType.GLASSDOOR
    display_name = "Glassdoor"
    supports_auto_apply = False
    requires_account = False
    rate_limit_per_minute = 30
    terms_note = (
        "Glassdoor job listings are available through their partner API. Production code must use it, "
        "attribute Glassdoor as required and stay inside the documented rate limits; applications usually "
        "redirect to the employer's own site."
    )
