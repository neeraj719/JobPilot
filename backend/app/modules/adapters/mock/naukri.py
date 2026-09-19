"""Naukri mock adapter — deterministic catalogue, no network access."""
from __future__ import annotations

from app.models.enums import JobSourceType
from app.modules.adapters.mock.base_mock import BaseMockAdapter


class NaukriMockAdapter(BaseMockAdapter):
    """Naukri job source (mock).

    Applications are simulated as an easy-apply flow.
    """

    source = JobSourceType.NAUKRI
    display_name = "Naukri"
    supports_auto_apply = True
    requires_account = True
    rate_limit_per_minute = 20
    terms_note = (
        "India's largest job board. Production integration must use the Naukri recruiter/partner API or the "
        "candidate's own authenticated session with explicit consent, honour naukri.com Terms of Use and "
        "robots.txt, and never automate around their bot protection."
    )
