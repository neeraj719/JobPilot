"""Shared pieces of the four public job board adapters.

:class:`BoardAdapter` is the discovery half: it walks every configured board of its
vendor (``SearchQuery.board_tokens``), maps each posting to a
:class:`~app.modules.adapters.base.DiscoveredJob`, and applies the query filters client
side with :func:`~app.modules.adapters.mock.base_mock.filter_catalogue` - the same
semantics as every other adapter. The apply half is inherited unchanged from
:class:`~app.modules.adapters.demo_ats.GenericAtsFormAdapter`: navigate, detect, map,
fill, pause for review. A CAPTCHA on a vendor's hosted form is reported by the detector
and pauses the application (``REQUIRES_USER`` / ``PauseReason.CAPTCHA``); nothing here
ever tries to solve one.

No Playwright import anywhere in this package (contract §8).
"""
from __future__ import annotations

import html
import logging
import re
from abc import abstractmethod
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from app.models.enums import ApplicationType, AutomationState, EmploymentType, WorkMode
from app.modules.adapters.base import ApplyContext, ApplyStepResult, BoardToken, DiscoveredJob, SearchQuery
from app.modules.adapters.boards.http import BoardFetchError, BoardPayloadError, fetch_json
from app.modules.adapters.boards.urls import TOKEN_RE
from app.modules.adapters.demo_ats import GenericAtsFormAdapter

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- HTML -> text

_BLOCK_TAGS = frozenset(
    {
        "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
        "section", "article", "header", "footer", "blockquote", "pre", "hr", "dd", "dt",
    }
)
_SKIP_TAGS = frozenset({"script", "style", "noscript", "template"})


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._bullet = False  # inside an <li> whose text has not started yet

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
            if tag == "li":
                self._bullet = True

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
            if tag == "li":
                self._bullet = False

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._bullet and data.strip():
            # The bullet goes on the item's first text, even when that sits in a nested <p>.
            self.parts.append("\n- ")
            data = data.lstrip()
            self._bullet = False
        self.parts.append(data)


def html_to_text(markup: str | None, *, unescape_first: bool = False) -> str:
    """Readable plain text from a vendor's HTML description.

    Block elements become line breaks, list items become ``- `` bullets, scripts and styles
    are dropped, runs of spaces collapse and at most one blank line separates paragraphs.
    ``unescape_first`` is for Greenhouse, whose API returns the HTML entity-escaped.
    """
    if not markup:
        return ""
    text = html.unescape(markup) if unescape_first else markup
    parser = _TextExtractor()
    try:
        parser.feed(text)
        parser.close()
    except Exception:  # pragma: no cover - HTMLParser is lenient; never lose a posting over it
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()
    raw = "".join(parser.parts).replace("\xa0", " ")
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in raw.split("\n")]
    compact: list[str] = []
    for line in lines:
        if line or (compact and compact[-1] != ""):
            compact.append(line)
    while compact and compact[-1] == "":
        compact.pop()
    # Paragraphs keep one blank line between them; consecutive list items stay together.
    out = [
        line
        for i, line in enumerate(compact)
        if line or not (compact[i - 1].startswith("- ") and i + 1 < len(compact) and compact[i + 1].startswith("- "))
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------- field helpers

_REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|anywhere|distributed|telecommute)\b", re.I)
_HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
_ONSITE_RE = re.compile(r"\b(on[- ]?site|in[- ]office)\b", re.I)


def detect_work_mode(*texts: str | None, flag: WorkMode | None = None) -> WorkMode | None:
    """The vendor's own flag when it has one, else the location (or title) text.

    ``None`` means "not stated" - the search filter keeps such postings rather than guess.
    """
    if flag is not None:
        return flag
    blob = " ".join(t for t in texts if t)
    if not blob:
        return None
    if _HYBRID_RE.search(blob):
        return WorkMode.HYBRID
    if _REMOTE_RE.search(blob):
        return WorkMode.REMOTE
    if _ONSITE_RE.search(blob):
        return WorkMode.ONSITE
    return None


def work_mode_from_vendor(value: Any) -> WorkMode | None:
    """``remote`` / ``Hybrid`` / ``OnSite`` / ``on-site`` style vendor values."""
    text = re.sub(r"[^a-z]", "", str(value or "").lower())
    if not text:
        return None
    if text == "remote":
        return WorkMode.REMOTE
    if text == "hybrid":
        return WorkMode.HYBRID
    if text in ("onsite", "inoffice", "office"):
        return WorkMode.ONSITE
    return None


def detect_employment_type(*texts: Any) -> EmploymentType | None:
    """Map a vendor's commitment / employment label (or a title) to :class:`EmploymentType`."""
    blob = " ".join(str(t) for t in texts if t).lower()
    if not blob:
        return None
    if re.search(r"\bintern(ship)?s?\b|\bco-?op\b", blob):
        return EmploymentType.INTERNSHIP
    if re.search(r"\bfreelanc", blob):
        return EmploymentType.FREELANCE
    if re.search(r"\bcontract(or)?\b|\btemporary\b|\btemp\b|\bshort[- ]term\b|\bfixed[- ]term\b", blob):
        return EmploymentType.CONTRACT
    if re.search(r"\bpart[- ]?time\b", blob):
        return EmploymentType.PART_TIME
    if re.search(r"\bfull[- ]?time\b|\bpermanent\b|\bregular\b", blob):
        return EmploymentType.FULL_TIME
    return None


def parse_datetime(value: Any) -> datetime | None:
    """ISO-8601 strings (``Z`` or offset) and epoch milliseconds, always returned in UTC."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            seconds = float(value) / 1000.0 if float(value) > 10_000_000_000 else float(value)
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_int(value: Any) -> int | None:
    try:
        if value is None or value == "" or isinstance(value, bool):
            return None
        return int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return None


def extract_skills(text: str) -> list[str]:
    """Canonical skills from the description, via the shared taxonomy in ``ai.skills``."""
    from app.modules.ai.skills import extract_skills as _extract

    try:
        return _extract(text or "")
    except Exception as exc:  # pragma: no cover - the taxonomy is pure Python; defensive
        logger.debug("Skill extraction failed: %s", exc)
        return []


def coerce_board_tokens(tokens: list[Any] | None) -> list[BoardToken]:
    """Accept :class:`BoardToken`s and plain ``(company_id, token)`` tuples alike."""
    out: list[BoardToken] = []
    for item in tokens or []:
        if isinstance(item, BoardToken):
            out.append(item)
            continue
        try:
            values = tuple(item)
        except TypeError:
            continue
        if len(values) < 2 or not values[1]:
            continue
        out.append(BoardToken(*values[:5]))
    return out


def require_list(payload: Any, key: str | None, what: str) -> list[dict[str, Any]]:
    """``payload[key]`` (or ``payload`` itself) as a list of dicts, else :class:`BoardPayloadError`."""
    value = payload.get(key) if (key and isinstance(payload, dict)) else payload
    if not isinstance(value, list):
        raise BoardPayloadError(f"{what}: expected a list of postings, got {type(value).__name__}")
    return [row for row in value if isinstance(row, dict)]


# --------------------------------------------------------------------------- the adapter


class BoardAdapter(GenericAtsFormAdapter):
    """Discovery from one vendor's public job board API; applying via the hosted form.

    Subclasses provide :meth:`api_url` and :meth:`map_board` (payload -> postings) and the
    vendor's submit selectors. Everything else - which boards to read, isolation of a
    failing board, filtering, the result limit - happens here once.
    """

    is_mock = False
    supports_auto_apply = True
    requires_account = False
    uses_browser = True
    rate_limit_per_minute = 30
    snapshot_fields_on_blocker = True
    #: Upper bound on waiting for the hosted form to finish loading its scripts (see :meth:`_settle`).
    settle_timeout_ms = 8000
    extra_confirmation_texts: tuple[str, ...] = (
        "Thank you for applying",
        "Thanks for applying",
        "Application submitted",
    )

    # -- vendor specifics ---------------------------------------------------

    @abstractmethod
    def api_url(self, token: str) -> str:
        """The public API URL that lists ``token``'s postings."""

    @abstractmethod
    def map_board(self, payload: Any, board: BoardToken) -> list[DiscoveredJob]:
        """Map a board payload to postings; raise :class:`BoardPayloadError` on a foreign shape."""

    def fetch_board(self, board: BoardToken) -> list[DiscoveredJob]:
        """Every posting on ``board`` (one request by default; SmartRecruiters paginates)."""
        return self.map_board(fetch_json(self.api_url(board.token)), board)

    def enrich(self, jobs: list[DiscoveredJob], board: BoardToken) -> list[DiscoveredJob]:
        """Hook for vendors whose list endpoint has no description (SmartRecruiters)."""
        return jobs

    def count_board_jobs(self, token: str) -> int:
        """Open postings on ``token``'s board - used to verify a board before saving it.

        Raises :class:`~app.modules.adapters.boards.http.BoardNotFound`,
        :class:`BoardPayloadError` or :class:`BoardFetchError`.
        """
        if not TOKEN_RE.match(token or ""):
            raise BoardPayloadError(f"{token!r} is not a valid board token")
        return len(self.fetch_board(BoardToken(None, token, token, None, self.source)))

    # -- discovery ----------------------------------------------------------

    def boards_for(self, query: SearchQuery) -> list[BoardToken]:
        """This vendor's boards from ``query.board_tokens``, validated and de-duplicated."""
        boards: list[BoardToken] = []
        seen: set[str] = set()
        for board in coerce_board_tokens(query.board_tokens):
            if board.source not in (None, self.source):
                continue
            if not TOKEN_RE.match(board.token or ""):
                logger.warning("%s: ignoring malformed board token %r", self.display_name, board.token)
                continue
            if board.token.lower() in seen:
                continue
            seen.add(board.token.lower())
            boards.append(board)
        return boards

    def search_jobs(self, query: SearchQuery) -> list[DiscoveredJob]:
        from app.modules.adapters.mock.base_mock import filter_catalogue

        boards = self.boards_for(query)
        if not boards:
            logger.info("%s: no company has a %s board configured; nothing to search", self.display_name, self.display_name)
            return []

        now = datetime.now(timezone.utc)
        per_board: list[list[DiscoveredJob]] = []
        for board in boards:
            try:
                postings = self.fetch_board(board)
            except Exception as exc:  # noqa: BLE001 - one bad board never sinks the others
                logger.warning("%s board %r failed: %s", self.display_name, board.token, exc)
                continue
            matched = filter_catalogue(postings, query, now) if postings else []
            if matched:
                try:
                    matched = self.enrich(matched, board)
                except Exception as exc:  # noqa: BLE001 - keep the postings without the extras
                    logger.warning("%s board %r: could not load posting details: %s", self.display_name, board.token, exc)
            logger.info("%s board %r: %d/%d postings match", self.display_name, board.token, len(matched), len(postings))
            per_board.append(matched)

        # Round-robin across companies so one huge board cannot use up the whole limit.
        limit = max(1, int(query.limit or 50))
        results: list[DiscoveredJob] = []
        index = 0
        while len(results) < limit and any(index < len(jobs) for jobs in per_board):
            for jobs in per_board:
                if index < len(jobs) and len(results) < limit:
                    results.append(jobs[index])
            index += 1
        return results

    def get_job_details(self, external_id: str) -> DiscoveredJob | None:
        """Postings are only reachable through a configured board; there is no global lookup."""
        return None

    # -- mapping helpers ----------------------------------------------------

    def make_job(self, board: BoardToken, **fields: Any) -> DiscoveredJob:
        """A :class:`DiscoveredJob` labelled with the configured company (not the vendor's name for it)."""
        description = fields.pop("description", "") or ""
        fields.setdefault("required_skills", extract_skills(description))
        return DiscoveredJob(
            source=self.source,
            company_name=board.company_name or board.token,
            company_domain=board.company_domain,
            application_type=ApplicationType.ATS_FORM,
            description=description,
            **fields,
        )

    # -- apply side ---------------------------------------------------------

    def start_application(self, ctx: ApplyContext) -> ApplyStepResult:
        """Open the hosted form; a page that never shows a form is handed to the detector.

        Vendors put bot protection (a CAPTCHA interstitial) in front of the form, and the
        form selector then never appears. Failing here would report "could not open" for
        what really is "a human must take over", so a page that did load is passed on and
        :meth:`fill_application` lets the blocker detector decide.
        """
        result = super().start_application(ctx)
        if ctx.page is None:
            return result
        if result.state == AutomationState.SUCCESS:
            self._settle(ctx.page)
            return result
        page_url = str(getattr(ctx.page, "url", "") or "")
        if not page_url.startswith(("http://", "https://")):
            return result
        logger.info("%s: form selector did not appear (%s); checking the page for blockers", self.display_name, result.message)
        self._settle(ctx.page)
        return ApplyStepResult(
            state=AutomationState.SUCCESS,
            message=f"Opened the {self.display_name} page (form not confirmed yet)",
            form_snapshot={"url": page_url},
        )

    def _settle(self, page: Any) -> None:
        """Give late widgets a moment to load before the detector looks at the page.

        The vendors' CAPTCHA widgets (Greenhouse's invisible reCAPTCHA in particular) are
        injected by script after the form itself renders. Detecting the instant the form
        appears misses them, and the run would then fill a form whose submission a CAPTCHA
        will block. Waiting for the network to go quiet - bounded, never fatal - lets the
        detector see the widget and pause the application for the user instead.
        """
        wait = getattr(page, "wait_for_load_state", None)
        if not callable(wait):
            return
        try:
            wait("networkidle", timeout=self.settle_timeout_ms)
        except Exception as exc:  # noqa: BLE001 - a page that never goes idle is still usable
            logger.debug("%s: page did not go idle within %d ms (%s)", self.display_name, self.settle_timeout_ms, exc)

    def fill_application(self, ctx: ApplyContext) -> ApplyStepResult:
        result = super().fill_application(ctx)
        if result.state == AutomationState.SUCCESS and not (result.form_snapshot or {}).get("fields"):
            return ApplyStepResult(
                state=AutomationState.FAILED,
                message=f"No application form was found on the {self.display_name} page",
                form_snapshot=result.form_snapshot,
                screenshot_path=result.screenshot_path,
            )
        return result

    def _submit_selector(self, ctx: ApplyContext) -> str:
        """The vendor's own submit button when it is on the page, else the detected one."""
        query = getattr(ctx.page, "query_selector", None)
        if callable(query):
            for selector in self.submit_selectors:
                try:
                    if query(selector) is not None:
                        return selector
                except Exception:  # noqa: BLE001 - selector unsupported here; try the next one
                    continue
        return super()._submit_selector(ctx)


__all__ = [
    "BoardAdapter",
    "BoardFetchError",
    "BoardPayloadError",
    "coerce_board_tokens",
    "detect_employment_type",
    "detect_work_mode",
    "extract_skills",
    "html_to_text",
    "parse_datetime",
    "require_list",
    "to_int",
    "work_mode_from_vendor",
]
