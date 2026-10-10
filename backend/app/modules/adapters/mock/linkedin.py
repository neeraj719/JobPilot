"""LinkedIn mock adapter — deterministic catalogue, no network access."""
from __future__ import annotations

from app.models.enums import JobSourceType
from app.modules.adapters.mock.base_mock import BaseMockAdapter


class LinkedInMockAdapter(BaseMockAdapter):
    """LinkedIn job source (mock).

    Applications are simulated as an easy-apply flow.
    """

    source = JobSourceType.LINKEDIN
    display_name = "LinkedIn"
    supports_auto_apply = True
    requires_account = True
    rate_limit_per_minute = 20
    terms_note = (
        "LinkedIn forbids scraping. A production integration must use the official LinkedIn Talent/Jobs APIs "
        "under an approved partnership, or let the user apply manually; no session scraping, no CAPTCHA or "
        "checkpoint bypass."
    )
