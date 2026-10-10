"""Company Careers mock adapter — deterministic catalogue, no network access."""
from __future__ import annotations

from app.models.enums import JobSourceType
from app.modules.adapters.mock.base_mock import BaseMockAdapter


class CompanyCareersMockAdapter(BaseMockAdapter):
    """Company Careers job source (mock).

    Listings redirect to the employer's own form, so auto-apply is not supported here.
    """

    source = JobSourceType.COMPANY_CAREERS
    display_name = "Company Careers"
    supports_auto_apply = False
    requires_account = False
    rate_limit_per_minute = 30
    terms_note = (
        "Company career sites are the canonical source for a posting. Production code should read the "
        "company's public jobs feed (Greenhouse/Lever/Workday JSON or an RSS/JSON careers feed), honour "
        "robots.txt and the site's Terms of Use, and hand the application form to the browser module."
    )
