"""Lever - the public Postings API.

``GET https://api.lever.co/v0/postings/{token}?mode=json`` returns every published
posting of one company, unauthenticated (https://github.com/lever/postings-api). A
posting's description is spread over ``description`` (the intro), ``lists`` (titled
sections such as "What you'll do") and ``additional`` (the closing text); they are joined
in that order. ``salaryRange`` is used when the company publishes a yearly range.

Applying goes through the hosted form at the posting's ``applyUrl``
(``jobs.lever.co/{token}/{id}/apply``). Lever renders an hCaptcha on that form; the
detector reports it and the application pauses for the user (never solved).
"""
from __future__ import annotations

import html
import logging
from typing import Any
from urllib.parse import quote

from app.models.enums import JobSourceType
from app.modules.adapters.base import BoardToken, DiscoveredJob
from app.modules.adapters.boards.common import (
    BoardAdapter,
    detect_employment_type,
    detect_work_mode,
    html_to_text,
    parse_datetime,
    require_list,
    to_int,
    work_mode_from_vendor,
)

logger = logging.getLogger(__name__)

API_URL = "https://api.lever.co/v0/postings/{token}?mode=json"


def _salary(row: dict[str, Any]) -> tuple[int | None, int | None, str | None]:
    """``salaryRange`` when it is a yearly salary; hourly / monthly ranges are not comparable."""
    salary = row.get("salaryRange")
    if not isinstance(salary, dict):
        return None, None, None
    interval = str(salary.get("interval") or "").lower()
    if interval and "year" not in interval and "annual" not in interval:
        return None, None, None
    low, high = to_int(salary.get("min")), to_int(salary.get("max"))
    if low is None and high is None:
        return None, None, None
    return low, high, (str(salary.get("currency")).upper() if salary.get("currency") else None)


def _description_html(row: dict[str, Any]) -> str:
    parts: list[str] = []
    if row.get("description"):
        parts.append(str(row["description"]))
    for section in row.get("lists") or []:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("text") or "").strip()
        if heading:
            parts.append(f"<h3>{html.escape(heading)}</h3>")
        if section.get("content"):
            parts.append(f"<ul>{section['content']}</ul>")
    if row.get("additional"):
        parts.append(str(row["additional"]))
    return "\n".join(parts)


class LeverAdapter(BoardAdapter):
    source = JobSourceType.LEVER
    display_name = "Lever"
    rate_limit_per_minute = 30
    # Observed on jobs.lever.co: the visible button is #btn-submit (type=button); a hidden
    # #hcaptchaSubmitBtn is the captcha widget's own trigger and must never be clicked.
    submit_selectors = ("#btn-submit", "button.template-btn-submit", "button[type=submit]")
    confirmation_text = "Thank you for applying"
    terms_note = (
        "Reads Lever's free, public Postings API (api.lever.co/v0/postings/<company>) for the "
        "companies you configured - no login, no scraping. Requests carry a descriptive User-Agent "
        "and are cached for 30 minutes. Lever's hosted form shows an hCaptcha, so applications pause "
        "for you to finish them; the CAPTCHA is never solved automatically."
    )

    def api_url(self, token: str) -> str:
        return API_URL.format(token=quote(token, safe=""))

    def map_board(self, payload: Any, board: BoardToken) -> list[DiscoveredJob]:
        rows = require_list(payload, None, f"Lever board {board.token!r}")
        jobs: list[DiscoveredJob] = []
        for row in rows:
            posting_id = row.get("id")
            title = str(row.get("text") or "").strip()
            hosted = row.get("hostedUrl")
            if not posting_id or not title or not hosted:
                continue
            categories = row.get("categories") if isinstance(row.get("categories"), dict) else {}
            location = str(categories.get("location") or "").strip() or None
            description_html = _description_html(row)
            salary_min, salary_max, currency = _salary(row)
            jobs.append(
                self.make_job(
                    board,
                    external_id=f"{board.token}:{posting_id}",
                    url=str(hosted),
                    title=title,
                    location=location,
                    work_mode=detect_work_mode(location, title, flag=work_mode_from_vendor(row.get("workplaceType"))),
                    employment_type=detect_employment_type(categories.get("commitment"), title),
                    description=html_to_text(description_html),
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_currency=currency,
                    posted_at=parse_datetime(row.get("createdAt")),
                    apply_url=str(row.get("applyUrl") or f"{hosted}/apply"),
                    raw={
                        "vendor": "lever",
                        "board_token": board.token,
                        "posting_id": posting_id,
                        "categories": categories,
                        "country": row.get("country"),
                        "workplace_type": row.get("workplaceType"),
                        "salary_range": row.get("salaryRange"),
                        "description_html": description_html,
                    },
                )
            )
        return jobs
