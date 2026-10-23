"""Read a job posting from the URL the user gave - and nothing else.

Known vendors first. A Greenhouse, Lever, Ashby or SmartRecruiters posting URL is answered from
the vendor's public board API through the existing board adapters (``adapters.boards``, the
same requests discovery makes, cached for 30 minutes): the posting is looked up by its id on
the company's board. That is the "reliable source": structured, current, and no HTML scraping.

Any other URL is fetched once, under these rules (plan §6):

* ``http``/``https`` only, default ports only, no credentials in the URL;
* the host must resolve to public addresses only - private, loopback, link-local, reserved and
  cloud-metadata ranges are refused - and that is checked again after **every** redirect
  (at most :data:`MAX_REDIRECTS`), because a public page may redirect inward;
* :data:`TIMEOUT_SECONDS` per request, the body is streamed and cut at :data:`MAX_BYTES`;
* a fresh client per request: no cookies are kept or sent, a fixed ``User-Agent``;
* HTML or plain text only.

From the page, a schema.org ``JobPosting`` in JSON-LD is preferred (title, company, location,
deadline, description); otherwise the main text with scripts, styles, navigation, headers,
footers and forms stripped. Nothing readable -> 422 ``jd_unreadable`` asking the user to paste
the text.

Known residual risk: the address check resolves the name, then httpx resolves it again to
connect (DNS rebinding between the two is not prevented). The fetch carries no credentials
and its body is only ever shown back to the same user.

Tests replace the network with :func:`set_transport` and DNS with :func:`set_resolver`.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from app.core.exceptions import ExternalServiceError, RateLimitedError, ValidationFailed
from app.core.rate_limit import rate_limiter
from app.models.enums import JdSource, JobSourceType, WorkMode
from app.modules.adapters.boards import http as board_http
from app.modules.adapters.boards.http import USER_AGENT
from app.modules.adapters.boards.urls import BOARD_VENDORS, TOKEN_RE, infer_ats_type

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_URL_CHARS = 2048
#: Outbound fetches (posting pages, board look-ups) per user per minute.
FETCH_RATE_LIMIT_PER_MINUTE = 10
#: Readable text below this is "nothing readable".
MIN_TEXT_CHARS = 200

_ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
_JOB_CUES = re.compile(r"\b(responsibilit|requirement|qualification|experience|skills|you will|what you)\w*", re.IGNORECASE)

Resolver = Callable[[str], list[str]]
_transport: httpx.BaseTransport | None = None


def _system_resolver(host: str) -> list[str]:
    try:
        return sorted({str(info[4][0]) for info in socket.getaddrinfo(host, None)})
    except (OSError, UnicodeError):
        return []


_resolver: Resolver = _system_resolver


def set_transport(transport: httpx.BaseTransport | None) -> None:
    """Route page requests through ``transport`` (tests); ``None`` restores the network."""
    global _transport
    _transport = transport


def set_resolver(resolver: Resolver | None) -> None:
    """Replace DNS resolution for the public-address check (tests); ``None`` restores it."""
    global _resolver
    _resolver = resolver or _system_resolver


def enforce_rate_limit(user_id: object, kind: str = "fetch") -> None:
    allowed, _ = rate_limiter.check(f"ats-{kind}:{user_id}", FETCH_RATE_LIMIT_PER_MINUTE, 60)
    if not allowed:
        raise RateLimitedError("Too many job-posting look-ups. Try again in a minute.")


@dataclass
class FetchedPosting:
    source: JdSource
    url: str
    text: str
    confidence: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    work_mode: WorkMode | None = None
    deadline: datetime | None = None
    vendor: str | None = None
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- URL guard


def _unreadable(message: str | None = None) -> ValidationFailed:
    return ValidationFailed(
        message or "No job description could be read from that page. Paste the job description text instead.",
        code="jd_unreadable",
    )


def _refused(reason: str) -> ValidationFailed:
    return ValidationFailed(
        f"That address cannot be fetched ({reason}). Use the public job posting link, or paste the job description.",
        code="url_not_allowed",
    )


def _is_public_host(host: str) -> bool:
    host = host.strip("[]").lower()
    if not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa")):
        return False
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        if "." not in host:
            return False
        addresses = _resolver(host)
    if not addresses:
        return False
    try:
        return all(ipaddress.ip_address(a).is_global for a in addresses)
    except ValueError:
        return False


def check_url(url: str) -> str:
    """The URL, normalised, or ``ValidationFailed`` (``invalid_url`` / ``url_not_allowed``)."""
    text = (url or "").strip()
    if not text or len(text) > MAX_URL_CHARS:
        raise ValidationFailed("Enter the job posting's full URL (https://...).", code="invalid_url")
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    if parsed.scheme.lower() not in ("http", "https"):
        raise _refused("only http and https links are supported")
    if parsed.username or parsed.password:
        raise _refused("links with credentials are not supported")
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        raise ValidationFailed("That URL has an invalid port.", code="invalid_url") from None
    if not host:
        raise ValidationFailed("Enter the job posting's full URL (https://...).", code="invalid_url")
    if port not in (None, 80, 443):
        raise _refused("non-standard ports are not fetched")
    if not _is_public_host(host):
        raise _refused("it does not point at a public website")
    return text


# --------------------------------------------------------------------------- vendors


def board_posting_from_url(url: str) -> tuple[JobSourceType, str, str] | None:
    """``(vendor, board token, posting id)`` for a vendor-hosted posting URL, else ``None``."""
    vendor = infer_ats_type(url)
    parsed = urlparse(url if "://" in url else f"https://{url}")
    segments = [s for s in parsed.path.split("/") if s]
    query = parse_qs(parsed.query)
    host = (parsed.hostname or "").lower()
    token: str | None = None
    posting: str | None = None
    if vendor is JobSourceType.GREENHOUSE:
        if "for" in query and "token" in query:
            token, posting = query["for"][0], query["token"][0]
        elif host.startswith(("boards-api.", "api.")) and "boards" in segments and "jobs" in segments:
            index = segments.index("boards")
            token = segments[index + 1] if index + 1 < len(segments) else None
            jobs_at = segments.index("jobs")
            posting = segments[jobs_at + 1] if jobs_at + 1 < len(segments) else None
        elif len(segments) >= 3 and segments[1] == "jobs":
            token, posting = segments[0], segments[2]
    elif vendor is JobSourceType.LEVER:
        if host.startswith("api.") and "postings" in segments:
            index = segments.index("postings")
            token = segments[index + 1] if index + 1 < len(segments) else None
            posting = segments[index + 2] if index + 2 < len(segments) else None
        elif len(segments) >= 2:
            token, posting = segments[0], segments[1]
    elif vendor is JobSourceType.ASHBY:
        if not host.startswith("api.") and len(segments) >= 2:
            token, posting = segments[0], segments[1]
    elif vendor is JobSourceType.SMARTRECRUITERS:
        if not host.startswith("api.") and len(segments) >= 2:
            token = segments[0]
            posting = segments[1].split("-", 1)[0]
    if vendor is None or not token or not posting:
        return None
    if not TOKEN_RE.match(token) or not re.match(r"^[A-Za-z0-9._-]{1,128}$", posting):
        return None
    return vendor, token, posting


def fetch_board_posting(vendor: JobSourceType | str, token: str, posting_id: str) -> FetchedPosting:
    """One posting from a public board API (through the board adapters and their cache)."""
    from app.modules.adapters.base import BoardToken
    from app.modules.adapters.boards.http import BoardFetchError, BoardNotFound
    from app.modules.adapters.registry import get_adapter

    source = vendor if isinstance(vendor, JobSourceType) else JobSourceType(str(vendor).upper())
    if source not in BOARD_VENDORS or not TOKEN_RE.match(token or ""):
        raise ValidationFailed("That board is not one JobPilot can read.", code="unsupported_board")
    wanted = str(posting_id).split(":")[-1]
    adapter = get_adapter(source)
    board = BoardToken(None, token, token, None, source)
    try:
        with board_http.request_timeout(TIMEOUT_SECONDS):
            postings = adapter.fetch_board(board)
            match = next(
                (p for p in postings if p.external_id.split(":", 1)[-1] == wanted or p.external_id == posting_id), None
            )
            if match is not None and not match.description:
                enriched = adapter.enrich([match], board)
                match = enriched[0] if enriched else match
    except BoardNotFound as exc:
        raise _unreadable(f"{token} has no public {source.value.title()} board. Paste the job description instead.") from exc
    except BoardFetchError as exc:
        raise ExternalServiceError(
            f"{source.value.title()} could not be reached right now. Try again, or paste the job description.",
            code="board_unreachable",
        ) from exc
    if match is None:
        raise _unreadable(
            "That posting is no longer on the company's board (it may have closed). Paste the job description instead."
        )
    text = (match.description or "").strip()
    if len(text) < MIN_TEXT_CHARS:
        raise _unreadable("The board lists this posting without a readable description. Paste the job description instead.")
    from app.modules.companies.board_detect import board_company_name

    # The board's own company name (Greenhouse / SmartRecruiters report it, from the cached answer);
    # the adapter's ``company_name`` is only the token here, so it is used when it is not just that.
    company = board_company_name(source, token) or (match.company_name if match.company_name and match.company_name != token else None)
    return FetchedPosting(
        source=JdSource.BOARD,
        url=match.url,
        text=text,
        confidence="high",
        title=match.title,
        company=company,
        location=match.location,
        work_mode=match.work_mode,
        vendor=source.value,
    )


# --------------------------------------------------------------------------- HTML


class _MainText(HTMLParser):
    """Readable text of a page, preferring ``<main>``/``<article>``; skips chrome and scripts."""

    SKIP = frozenset({"script", "style", "noscript", "template", "svg", "nav", "header", "footer", "form", "aside", "iframe", "button", "select"})
    BLOCK = frozenset(
        {"p", "div", "section", "article", "main", "li", "ul", "ol", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "dd", "dt"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.main_parts: list[str] = []
        self.skip_depth = 0
        self.main_depth = 0
        self.title: str | None = None
        self.h1: str | None = None
        self.og_title: str | None = None
        self.og_site: str | None = None
        self.ld_json: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._in_ld = False
        self._ld_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script" and "ld+json" in values.get("type", "").lower():
            self._in_ld = True
            self._ld_buffer = []
            return
        if tag == "meta":
            prop = (values.get("property") or values.get("name") or "").lower()
            if prop == "og:title":
                self.og_title = values.get("content") or None
            elif prop == "og:site_name":
                self.og_site = values.get("content") or None
            return
        if tag in self.SKIP:
            self.skip_depth += 1
            return
        if tag in ("main", "article"):
            self.main_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "h1":
            self._in_h1 = True
        if tag in self.BLOCK:
            self._emit("\n")
        if tag == "li":
            self._emit("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_ld:
            self._in_ld = False
            self.ld_json.append("".join(self._ld_buffer))
            return
        if tag in self.SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag in ("main", "article"):
            self.main_depth = max(0, self.main_depth - 1)
        if tag == "title":
            self._in_title = False
        if tag == "h1":
            self._in_h1 = False
        if tag in self.BLOCK:
            self._emit("\n")

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self._ld_buffer.append(data)
            return
        if self._in_title and not self.title:
            self.title = data.strip() or None
        if self.skip_depth:
            return
        if self._in_h1 and not self.h1 and data.strip():
            self.h1 = data.strip()
        self._emit(data)

    def _emit(self, text: str) -> None:
        self.parts.append(text)
        if self.main_depth:
            self.main_parts.append(text)


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _html_text(markup: str) -> str:
    from app.modules.adapters.boards.common import html_to_text

    return html_to_text(markup or "", unescape_first=True)


def _job_postings(blob: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(blob, list):
        for item in blob:
            found += _job_postings(item)
    elif isinstance(blob, dict):
        kind = blob.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(str(k).lower() == "jobposting" for k in kinds if k):
            found.append(blob)
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in blob:
                found += _job_postings(blob[key])
    return found


def _ld_location(posting: dict[str, Any]) -> str | None:
    places = posting.get("jobLocation")
    places = places if isinstance(places, list) else [places]
    for place in places:
        address = place.get("address") if isinstance(place, dict) else None
        if isinstance(address, dict):
            parts = [address.get(k) for k in ("addressLocality", "addressRegion", "addressCountry")]
            parts = [p.get("name") if isinstance(p, dict) else p for p in parts]
            text = ", ".join(str(p) for p in parts if p)
            if text:
                return text[:255]
    return None


def _parse_date(value: Any) -> datetime | None:
    from app.modules.adapters.boards.common import parse_datetime

    try:
        return parse_datetime(value)
    except Exception:  # noqa: BLE001
        return None


def parse_page(url: str, markup: str, content_type: str) -> FetchedPosting:
    """Pure: the posting inside a fetched page (JSON-LD first, then the main text)."""
    if content_type.startswith("text/plain"):
        text = _tidy(markup)
        if len(text) < MIN_TEXT_CHARS:
            raise _unreadable()
        return FetchedPosting(source=JdSource.URL, url=url, text=text, confidence="medium")

    parser = _MainText()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed HTML: use what was read
        pass
    for blob in parser.ld_json:
        try:
            data = json.loads(blob.strip())
        except ValueError:
            continue
        for posting in _job_postings(data):
            description = _tidy(_html_text(str(posting.get("description") or "")))
            if len(description) < MIN_TEXT_CHARS:
                continue
            org = posting.get("hiringOrganization")
            company = org.get("name") if isinstance(org, dict) else (org if isinstance(org, str) else None)
            location_type = str(posting.get("jobLocationType") or "").upper()
            return FetchedPosting(
                source=JdSource.URL,
                url=url,
                text=description,
                confidence="high",
                title=str(posting.get("title") or "").strip()[:255] or None,
                company=str(company or "").strip()[:255] or None,
                location=_ld_location(posting),
                work_mode=WorkMode.REMOTE if "TELECOMMUTE" in location_type else None,
                deadline=_parse_date(posting.get("validThrough")),
            )
    main = _tidy("".join(parser.main_parts))
    body = _tidy("".join(parser.parts))
    text = main if len(main) >= MIN_TEXT_CHARS else body
    if len(text) < MIN_TEXT_CHARS:
        raise _unreadable()
    confidence = "medium" if len(text) >= 600 and len(_JOB_CUES.findall(text)) >= 2 else "low"
    warnings = [] if confidence == "medium" else [
        "This page did not look like a job posting; check the text below and paste the description if it is wrong."
    ]
    title = parser.og_title or parser.h1 or parser.title
    return FetchedPosting(
        source=JdSource.URL,
        url=url,
        text=text,
        confidence=confidence,
        title=(title or "").strip()[:255] or None,
        company=(parser.og_site or "").strip()[:255] or None,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- fetch


@dataclass
class _Page:
    status_code: int
    headers: httpx.Headers
    content: bytes
    encoding: str | None

    @property
    def is_redirect(self) -> bool:
        return self.status_code in (301, 302, 303, 307, 308) and "location" in self.headers


def _get_once(url: str) -> _Page:
    """One GET, no redirects followed, body capped; a fresh client so no cookie survives."""
    with httpx.Client(
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.8"},
        follow_redirects=False,
        transport=_transport,
    ) as client:
        with client.stream("GET", url) as response:
            body = bytearray()
            page = _Page(response.status_code, response.headers, b"", response.encoding)
            if not page.is_redirect:
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ValidationFailed(
                            "That page is larger than 2 MB. Paste the job description text instead.", code="jd_too_large"
                        )
            page.content = bytes(body)
            return page


def fetch_page(url: str) -> tuple[str, str, str]:
    """``(final_url, text, content_type)`` of a public page, following at most 3 checked redirects."""
    current = check_url(url)
    for _hop in range(MAX_REDIRECTS + 1):
        try:
            response = _get_once(current)
        except ValidationFailed:
            raise
        except httpx.TimeoutException as exc:
            raise ExternalServiceError("The page took too long to answer. Paste the job description instead.", code="fetch_timeout") from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                f"The page could not be fetched ({type(exc).__name__}). Paste the job description instead.",
                code="fetch_failed",
            ) from exc
        if response.is_redirect:
            location = response.headers.get("location") or ""
            current = check_url(urljoin(current, location))
            continue
        if response.status_code in (401, 403):
            raise _unreadable("That page needs a login or blocks automated reading. Paste the job description instead.")
        if response.status_code == 404:
            raise _unreadable("That page was not found (the posting may have closed). Paste the job description instead.")
        if response.status_code >= 400:
            raise _unreadable(f"The site answered HTTP {response.status_code}. Paste the job description instead.")
        content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type and not content_type.startswith(_ALLOWED_TYPES):
            raise _unreadable("That link is not a web page. Paste the job description instead.")
        encoding = response.encoding or "utf-8"
        try:
            text = response.content.decode(encoding, errors="replace")
        except LookupError:
            text = response.content.decode("utf-8", errors="replace")
        return current, text, content_type or "text/html"
    raise _refused(f"more than {MAX_REDIRECTS} redirects")


def fetch_posting(url: str) -> FetchedPosting:
    """The job posting behind ``url``: a known vendor's API first, else the guarded page fetch."""
    checked = check_url(url)
    vendor = board_posting_from_url(checked)
    if vendor is not None:
        return fetch_board_posting(*vendor)
    final_url, markup, content_type = fetch_page(checked)
    posting = parse_page(final_url, markup, content_type)
    # A company careers page that embeds a vendor board ("?gh_jid=123" style) still says so.
    return posting


__all__ = [
    "FETCH_RATE_LIMIT_PER_MINUTE",
    "MAX_BYTES",
    "MAX_REDIRECTS",
    "FetchedPosting",
    "board_posting_from_url",
    "check_url",
    "enforce_rate_limit",
    "fetch_board_posting",
    "fetch_page",
    "fetch_posting",
    "parse_page",
    "set_resolver",
    "set_transport",
]
