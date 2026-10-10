"""Foundit mock adapter — deterministic catalogue, no network access."""
from __future__ import annotations

from app.models.enums import JobSourceType
from app.modules.adapters.mock.base_mock import BaseMockAdapter


class FounditMockAdapter(BaseMockAdapter):
    """Foundit job source (mock).

    Applications are simulated as an easy-apply flow.
    """

    source = JobSourceType.FOUNDIT
    display_name = "Foundit"
    supports_auto_apply = True
    requires_account = True
    rate_limit_per_minute = 30
    terms_note = (
        "Foundit (formerly Monster India) provides an employer/partner API. Production integration must be "
        "contractual, rate limited and used only with the candidate's consent."
    )
