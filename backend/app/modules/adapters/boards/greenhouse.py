"""Greenhouse - the public Job Board API.

``GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`` lists every
published posting of one company's board, description included, with no authentication
(https://developers.greenhouse.io/job-board.html). Greenhouse returns the description as
*entity-escaped* HTML, so it is unescaped before the tags are stripped.

Applying goes through Greenhouse's hosted application form. The adapter points the
browser at ``job-boards.greenhouse.io/embed/job_app?for={token}&token={job_id}`` rather
than the posting's ``absolute_url``: companies with their own careers site (Stripe,
for one) set ``absolute_url`` to a page on their domain that embeds the form in an
iframe, while the embed URL serves the same form directly for every board.
"""
from __future__ import annotations

import html
import logging
from typing import Any
from urllib.parse import quote, urlencode

from app.models.enums import JobSourceType
from app.modules.adapters.base import BoardToken, DiscoveredJob
from app.modules.adapters.boards.common import (
    BoardAdapter,
    detect_employment_type,
    detect_work_mode,
    html_to_text,
    parse_datetime,
    require_list,
)

logger = logging.getLogger(__name__)

API_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
APPLY_URL = "https://job-boards.greenhouse.io/embed/job_app"


def _metadata_value(job: dict[str, Any], *needles: str) -> Any:
    """The value of the first custom metadata field whose name mentions one of ``needles``."""
    for entry in job.get("metadata") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").lower()
        if any(needle in name for needle in needles):
            value = entry.get("value")
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value if v)
            if value:
                return value
    return None


class GreenhouseAdapter(BoardAdapter):
    source = JobSourceType.GREENHOUSE
    display_name = "Greenhouse"
    rate_limit_per_minute = 30
    # Legacy boards.greenhouse.io forms use #submit_app; the current job-boards forms a
    # plain submit button labelled "Submit application".
    submit_selectors = (
        "#submit_app",
        "button[type=submit]:has-text('Submit application')",
        "button[type=submit]",
        "input[type=submit]",
    )
    terms_note = (
        "Reads Greenhouse's free, public Job Board API (boards-api.greenhouse.io/v1/boards/<token>/jobs) "
        "for the companies you configured - no login, no scraping. Requests carry a descriptive "
        "User-Agent and are cached for 30 minutes. Applications are filled on Greenhouse's hosted form "
        "and paused for your review; a reCAPTCHA on the form pauses the application for you, it is never solved."
    )

    def api_url(self, token: str) -> str:
        return API_URL.format(token=quote(token, safe=""))

    @staticmethod
    def apply_url(token: str, job_id: Any) -> str:
        return f"{APPLY_URL}?{urlencode({'for': token, 'token': str(job_id)})}"

    def map_board(self, payload: Any, board: BoardToken) -> list[DiscoveredJob]:
        rows = require_list(payload, "jobs", f"Greenhouse board {board.token!r}")
        jobs: list[DiscoveredJob] = []
        for row in rows:
            job_id = row.get("id")
            title = str(row.get("title") or "").strip()
            if job_id is None or not title:
                continue
            location = (row.get("location") or {}).get("name") if isinstance(row.get("location"), dict) else None
            location = str(location).strip() if location else None
            # Greenhouse entity-escapes the description; keep the real HTML in ``raw``.
            content_html = html.unescape(str(row.get("content") or ""))
            description = html_to_text(content_html)
            workplace = _metadata_value(row, "workplace", "remote", "location type")
            employment = _metadata_value(row, "employment", "time type", "job type", "commitment")
            apply_url = self.apply_url(board.token, job_id)
            jobs.append(
                self.make_job(
                    board,
                    external_id=f"{board.token}:{job_id}",
                    url=str(row.get("absolute_url") or apply_url),
                    title=title,
                    location=location,
                    work_mode=detect_work_mode(str(workplace) if workplace else None, location, title),
                    employment_type=detect_employment_type(employment, title),
                    description=description,
                    posted_at=parse_datetime(row.get("first_published")) or parse_datetime(row.get("updated_at")),
                    apply_url=apply_url,
                    raw={
                        "vendor": "greenhouse",
                        "board_token": board.token,
                        "job_id": job_id,
                        "absolute_url": row.get("absolute_url"),
                        "updated_at": row.get("updated_at"),
                        "departments": [d.get("name") for d in row.get("departments") or [] if isinstance(d, dict)],
                        "offices": [o.get("name") for o in row.get("offices") or [] if isinstance(o, dict)],
                        "content_html": content_html,
                    },
                )
            )
        return jobs
