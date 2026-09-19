"""Greenhouse ATS adapter (stub).

Discovery is intentionally not implemented in the MVP: a production version would read
the **public Greenhouse job board JSON API**
(``https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs?content=true``) for the
boards of the companies on the user's priority list — a documented, public endpoint that
needs no scraping.

The *application* side is fully functional: Greenhouse forms are ordinary hosted HTML
forms, so this adapter reuses :class:`~app.modules.adapters.demo_ats.GenericAtsFormAdapter`
(detect → map → fill → human review → submit) via the browser module.
"""
from __future__ import annotations

import logging

from app.models.enums import JobSourceType
from app.modules.adapters.base import DiscoveredJob, SearchQuery
from app.modules.adapters.demo_ats import GenericAtsFormAdapter

logger = logging.getLogger(__name__)


class GreenhouseAdapter(GenericAtsFormAdapter):
    source = JobSourceType.GREENHOUSE
    display_name = "Greenhouse"
    is_mock = False
    supports_auto_apply = True
    requires_account = False
    uses_browser = True
    rate_limit_per_minute = 30
    submit_selectors = ("#submit_app", "button[type=submit]", "input[type=submit]")
    terms_note = (
        "Greenhouse publishes a free, public job board API per company board token. A production "
        "implementation must use that API rather than scraping, identify itself with a descriptive "
        "User-Agent, cache aggressively to stay polite, and submit only forms the user has reviewed."
    )

    def search_jobs(self, query: SearchQuery) -> list[DiscoveredJob]:
        """Not implemented in the MVP — see the module docstring for the production plan."""
        logger.info("Greenhouse discovery is not enabled in the MVP; returning no jobs")
        return []
