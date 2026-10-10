"""Internshala mock adapter — deterministic catalogue, no network access."""
from __future__ import annotations

from app.models.enums import JobSourceType
from app.modules.adapters.mock.base_mock import BaseMockAdapter


class InternshalaMockAdapter(BaseMockAdapter):
    """Internshala job source (mock).

    Applications are simulated as an easy-apply flow.
    """

    source = JobSourceType.INTERNSHALA
    display_name = "Internshala"
    supports_auto_apply = True
    requires_account = True
    rate_limit_per_minute = 30
    terms_note = (
        "Internshala lists internships and fresher roles. Production integration must use their official "
        "partner feed or the candidate's own session, and honour internshala.com Terms of Use."
    )
