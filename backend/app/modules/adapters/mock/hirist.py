"""Hirist mock adapter — deterministic catalogue, no network access."""
from __future__ import annotations

from app.models.enums import JobSourceType
from app.modules.adapters.mock.base_mock import BaseMockAdapter


class HiristMockAdapter(BaseMockAdapter):
    """Hirist job source (mock).

    Applications are simulated as an easy-apply flow.
    """

    source = JobSourceType.HIRIST
    display_name = "Hirist"
    supports_auto_apply = True
    requires_account = True
    rate_limit_per_minute = 30
    terms_note = (
        "Hirist is an India-focused tech job board. Production integration requires their employer/partner "
        "feed or the candidate's own session, used within hirist.tech Terms of Service."
    )
