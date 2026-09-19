"""Indeed mock adapter — deterministic catalogue, no network access."""
from __future__ import annotations

from app.models.enums import JobSourceType
from app.modules.adapters.mock.base_mock import BaseMockAdapter


class IndeedMockAdapter(BaseMockAdapter):
    """Indeed job source (mock).

    Applications are simulated as an easy-apply flow.
    """

    source = JobSourceType.INDEED
    display_name = "Indeed"
    supports_auto_apply = True
    requires_account = False
    rate_limit_per_minute = 30
    terms_note = (
        "Indeed exposes a publisher/Job Sync API for partners. Production code must use it with a valid "
        "publisher key, respect the documented rate limits and the Indeed Terms of Service."
    )
