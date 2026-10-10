"""SmartRecruiters - the public Posting API.

``GET https://api.smartrecruiters.com/v1/companies/{token}/postings`` lists one company's
public postings, 100 per page (``offset``/``limit``), without descriptions;
``GET .../postings/{id}`` returns one posting with its job ad sections
(https://developers.smartrecruiters.com/docs/posting-api). No authentication.

Because a description costs one request per posting, the list is filtered first (title,
location, age, work mode - everything the summary carries) and details are fetched only
for the postings that survived, which is at most the query limit. A keyword-only match
therefore has to hit the title. Large boards are read up to :data:`MAX_PAGES` pages.

The API answers ``200`` with ``totalFound: 0`` for a company identifier that does not
exist, so an empty board is treated as "not found" when a board is verified.

Applying goes through the posting's ``applyUrl`` on jobs.smartrecruiters.com. That form
sits behind bot protection that answers automated browsers with a CAPTCHA interstitial;
the detector reports it and the application pauses for the user (never solved).
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
    extract_skills,
    html_to_text,
    parse_datetime,
    require_list,
)
from app.modules.adapters.boards.http import BoardFetchError, BoardPayloadError, fetch_json

logger = logging.getLogger(__name__)

API_BASE = "https://api.smartrecruiters.com/v1/companies/{token}/postings"
PAGE_SIZE = 100
#: 1,000 postings per board. Enough for every company except the very largest, whose
#: newest postings come first anyway.
MAX_PAGES = 10
#: The job ad sections, in reading order.
_SECTIONS = ("companyDescription", "jobDescription", "qualifications", "additionalInformation")


def _location_text(location: dict[str, Any]) -> str | None:
    full = str(location.get("fullLocation") or "").strip()
    if full:
        return full
    parts = [str(location.get(k) or "").strip() for k in ("city", "region", "country")]
    text = ", ".join(p for p in parts if p)
    return text or None


def _work_mode_flag(location: dict[str, Any]) -> WorkMode | None:
    if location.get("remote") is True:
        return WorkMode.REMOTE
    if location.get("hybrid") is True:
        return WorkMode.HYBRID
    return None


class SmartRecruitersAdapter(BoardAdapter):
    source = JobSourceType.SMARTRECRUITERS
    display_name = "SmartRecruiters"
    rate_limit_per_minute = 30
    form_ready_selector = "form, oc-oneclick-form, button[type=submit]"
    # Not observed live: jobs.smartrecruiters.com answered the automated browser with a
    # CAPTCHA interstitial before the form. These are the one-click form's documented
    # footer submit button and the generic fallback.
    submit_selectors = ("button[data-test='footer-submit']", "button[type=submit]")
    terms_note = (
        "Reads SmartRecruiters' free, public Posting API (api.smartrecruiters.com/v1/companies/<company>/postings) "
        "for the companies you configured - no login, no scraping. Requests carry a descriptive User-Agent and are "
        "cached for 30 minutes. The hosted application form is protected by a bot check; when it shows a CAPTCHA the "
        "application pauses for you - it is never solved automatically."
    )

    def api_url(self, token: str, offset: int = 0) -> str:
        base = API_BASE.format(token=quote(token, safe=""))
        return f"{base}?limit={PAGE_SIZE}&offset={int(offset)}"

    def detail_url(self, token: str, posting_id: str) -> str:
        return f"{API_BASE.format(token=quote(token, safe=''))}/{quote(str(posting_id), safe='')}"

    # -- discovery ----------------------------------------------------------

    def fetch_board(self, board: BoardToken) -> list[DiscoveredJob]:
        rows: list[dict[str, Any]] = []
        total: int | None = None
        for page in range(MAX_PAGES):
            payload = fetch_json(self.api_url(board.token, page * PAGE_SIZE))
            content = require_list(payload, "content", f"SmartRecruiters board {board.token!r}")
            if isinstance(payload, dict) and isinstance(payload.get("totalFound"), int):
                total = payload["totalFound"]
            rows.extend(content)
            if len(content) < PAGE_SIZE or (total is not None and len(rows) >= total):
                break
        else:
            logger.info("SmartRecruiters board %r: read the first %d of %s postings", board.token, len(rows), total)
        return self.map_board(rows, board)

    def count_board_jobs(self, token: str) -> int:
        """``totalFound`` from the first page - verifying a board never walks all of it."""
        payload = fetch_json(self.api_url(token, 0))
        require_list(payload, "content", f"SmartRecruiters board {token!r}")
        total = payload.get("totalFound") if isinstance(payload, dict) else None
        if not isinstance(total, int):
            raise BoardPayloadError(f"SmartRecruiters board {token!r}: no totalFound in the answer")
        return total

    def map_board(self, payload: Any, board: BoardToken) -> list[DiscoveredJob]:
        rows = require_list(payload, "content", f"SmartRecruiters board {board.token!r}")
        jobs: list[DiscoveredJob] = []
        for row in rows:
            posting_id = row.get("id")
            title = str(row.get("name") or "").strip()
            if not posting_id or not title:
                continue
            location = row.get("location") if isinstance(row.get("location"), dict) else {}
            location_text = _location_text(location)
            employment = (row.get("typeOfEmployment") or {}).get("label") if isinstance(row.get("typeOfEmployment"), dict) else None
            public_url = f"https://jobs.smartrecruiters.com/{quote(board.token, safe='')}/{quote(str(posting_id), safe='')}"
            jobs.append(
                self.make_job(
                    board,
                    external_id=f"{board.token}:{posting_id}",
                    url=public_url,
                    title=title,
                    location=location_text,
                    work_mode=detect_work_mode(location_text, title, flag=_work_mode_flag(location)),
                    employment_type=detect_employment_type(employment, title),
                    description="",
                    required_skills=[],
                    posted_at=parse_datetime(row.get("releasedDate")),
                    apply_url=f"{public_url}?oga=true",
                    raw={
                        "vendor": "smartrecruiters",
                        "board_token": board.token,
                        "posting_id": posting_id,
                        "uuid": row.get("uuid"),
                        "ref_number": row.get("refNumber"),
                        "department": (row.get("department") or {}).get("label") if isinstance(row.get("department"), dict) else None,
                        "experience_level": (row.get("experienceLevel") or {}).get("label")
                        if isinstance(row.get("experienceLevel"), dict)
                        else None,
                    },
                )
            )
        return jobs

    def enrich(self, jobs: list[DiscoveredJob], board: BoardToken) -> list[DiscoveredJob]:
        """Fetch the job ad (description, real posting / apply URLs) for each kept posting."""
        for job in jobs:
            posting_id = job.raw.get("posting_id")
            if not posting_id:
                continue
            try:
                detail = fetch_json(self.detail_url(board.token, str(posting_id)))
            except BoardFetchError as exc:
                logger.warning("SmartRecruiters posting %s/%s: no details (%s)", board.token, posting_id, exc)
                continue
            if not isinstance(detail, dict):
                continue
            self.apply_detail(job, detail)
        return jobs

    @staticmethod
    def apply_detail(job: DiscoveredJob, detail: dict[str, Any]) -> None:
        sections = ((detail.get("jobAd") or {}).get("sections") or {}) if isinstance(detail.get("jobAd"), dict) else {}
        parts: list[str] = []
        for key in _SECTIONS:
            section = sections.get(key) if isinstance(sections, dict) else None
            if not isinstance(section, dict) or not section.get("text"):
                continue
            title = str(section.get("title") or "").strip()
            parts.append((f"<h3>{title}</h3>" if title else "") + str(section["text"]))
        description_html = "\n".join(parts)
        if description_html:
            job.description = html_to_text(description_html)
            job.required_skills = extract_skills(job.description)
            job.raw["description_html"] = description_html
        if detail.get("postingUrl"):
            job.url = str(detail["postingUrl"])
        if detail.get("applyUrl"):
            job.apply_url = str(detail["applyUrl"])
