"""Lever ATS adapter (stub).

Discovery is intentionally not implemented in the MVP: a production version would read
the **public Lever postings API**
(``https://api.lever.co/v0/postings/<company>?mode=json``) for the companies on the
user's priority list — a documented, public endpoint that needs no scraping.

The *application* side reuses the shared hosted-form flow in
:class:`~app.modules.adapters.demo_ats.GenericAtsFormAdapter` (detect → map → fill →
human review → submit) via the browser module.
"""
from __future__ import annotations

import logging

from app.models.enums import JobSourceType
from app.modules.adapters.base import DiscoveredJob, SearchQuery
from app.modules.adapters.demo_ats import GenericAtsFormAdapter

logger = logging.getLogger(__name__)


class LeverAdapter(GenericAtsFormAdapter):
    source = JobSourceType.LEVER
    display_name = "Lever"
    is_mock = False
    supports_auto_apply = True
    requires_account = False
    uses_browser = True
    rate_limit_per_minute = 30
    submit_selectors = ("button[type=submit]", ".template-btn-submit", "input[type=submit]")
    confirmation_text = "Thank you for applying"
    terms_note = (
        "Lever exposes a public postings API per company. A production implementation must use that "
        "API instead of scraping, honour Lever's Terms of Service and rate limits, and submit only "
        "applications the user has explicitly approved."
    )

    def search_jobs(self, query: SearchQuery) -> list[DiscoveredJob]:
        """Not implemented in the MVP — see the module docstring for the production plan."""
        logger.info("Lever discovery is not enabled in the MVP; returning no jobs")
        return []
