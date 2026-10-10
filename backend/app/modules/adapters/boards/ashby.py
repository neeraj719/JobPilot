"""Ashby - the public Job Postings API.

``GET https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true``
returns one company's published postings with descriptions and, when the company shows
it, the compensation breakdown (https://developers.ashbyhq.com/docs/public-job-posting-api).
Unlisted postings (``isListed: false``) are skipped. Salary comes from the yearly
``Salary`` component of the compensation summary.

Applying goes through the hosted form at the posting's ``applyUrl``
(``jobs.ashbyhq.com/{token}/{id}/application``), a single-page app with no ``<form>``
element - so the readiness check waits for the submit button instead. The form carries a
reCAPTCHA; the detector reports it and the application pauses for the user.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from app.models.enums import JobSourceType, WorkMode
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

API_URL = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"

#: Ashby's ``employmentType`` values.
_EMPLOYMENT = {"fulltime": "full time", "parttime": "part time", "intern": "intern", "contract": "contract", "temporary": "temporary"}


def _yearly_salary(compensation: Any) -> tuple[int | None, int | None, str | None]:
    if not isinstance(compensation, dict):
        return None, None, None
    components: list[dict[str, Any]] = [c for c in compensation.get("summaryComponents") or [] if isinstance(c, dict)]
    for tier in compensation.get("compensationTiers") or []:
        if isinstance(tier, dict):
            components.extend(c for c in tier.get("components") or [] if isinstance(c, dict))
    for component in components:
        if str(component.get("compensationType") or "").lower() != "salary":
            continue
        interval = str(component.get("interval") or "").upper()
        if interval and "YEAR" not in interval:
            continue
        low, high = to_int(component.get("minValue")), to_int(component.get("maxValue"))
        if low is None and high is None:
            continue
        currency = component.get("currencyCode")
        return low, high, (str(currency).upper() if currency else None)
    return None, None, None


class AshbyAdapter(BoardAdapter):
    source = JobSourceType.ASHBY
    display_name = "Ashby"
    rate_limit_per_minute = 30
    form_ready_selector = "button.ashby-application-form-submit-button, form, input[type=email]"
    # Observed on jobs.ashbyhq.com: <button type="submit" class="... ashby-application-form-submit-button">.
    submit_selectors = ("button.ashby-application-form-submit-button", "button[type=submit]")
    terms_note = (
        "Reads Ashby's free, public Job Postings API (api.ashbyhq.com/posting-api/job-board/<board>) for "
        "the companies you configured - no login, no scraping. Requests carry a descriptive User-Agent and "
        "are cached for 30 minutes. Ashby's hosted form carries a reCAPTCHA, so applications pause for you "
        "to finish them; the CAPTCHA is never solved automatically."
    )

    def api_url(self, token: str) -> str:
        return API_URL.format(token=quote(token, safe=""))

    def map_board(self, payload: Any, board: BoardToken) -> list[DiscoveredJob]:
        rows = require_list(payload, "jobs", f"Ashby board {board.token!r}")
        jobs: list[DiscoveredJob] = []
        for row in rows:
            if row.get("isListed") is False:
                continue
            posting_id = row.get("id")
            title = str(row.get("title") or "").strip()
            job_url = row.get("jobUrl")
            if not posting_id or not title or not job_url:
                continue
            location = str(row.get("location") or "").strip() or None
            flag = work_mode_from_vendor(row.get("workplaceType"))
            if flag is None and row.get("isRemote") is True:
                flag = WorkMode.REMOTE
            employment_raw = str(row.get("employmentType") or "")
            salary_min, salary_max, currency = _yearly_salary(row.get("compensation"))
            description_html = str(row.get("descriptionHtml") or "")
            description = html_to_text(description_html) or str(row.get("descriptionPlain") or "")
            jobs.append(
                self.make_job(
                    board,
                    external_id=f"{board.token}:{posting_id}",
                    url=str(job_url),
                    title=title,
                    location=location,
                    work_mode=detect_work_mode(location, title, flag=flag),
                    employment_type=detect_employment_type(_EMPLOYMENT.get(employment_raw.lower(), employment_raw), title),
                    description=description,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_currency=currency,
                    posted_at=parse_datetime(row.get("publishedAt")),
                    apply_url=str(row.get("applyUrl") or f"{job_url}/application"),
                    raw={
                        "vendor": "ashby",
                        "board_token": board.token,
                        "posting_id": posting_id,
                        "department": row.get("department"),
                        "team": row.get("team"),
                        "workplace_type": row.get("workplaceType"),
                        "is_remote": row.get("isRemote"),
                        "secondary_locations": [
                            s.get("location") for s in row.get("secondaryLocations") or [] if isinstance(s, dict)
                        ],
                        "compensation_summary": (row.get("compensation") or {}).get("compensationTierSummary")
                        if isinstance(row.get("compensation"), dict)
                        else None,
                        "description_html": description_html,
                    },
                )
            )
        return jobs
