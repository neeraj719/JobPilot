"""Wellfound mock adapter — deterministic catalogue, no network access."""
from __future__ import annotations

from app.models.enums import JobSourceType
from app.modules.adapters.mock.base_mock import BaseMockAdapter


class WellfoundMockAdapter(BaseMockAdapter):
    """Wellfound job source (mock).

    Applications are simulated as an easy-apply flow.
    """

    source = JobSourceType.WELLFOUND
    display_name = "Wellfound"
    supports_auto_apply = True
    requires_account = True
    rate_limit_per_minute = 30
    terms_note = (
        "Wellfound (AngelList Talent) offers a partner API for startups. Production integration must be "
        "authorised, respect their Terms of Service and apply only on behalf of the signed-in user."
    )
