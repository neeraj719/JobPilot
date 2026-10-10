"""Find a company's public job board from its name and/or website.

:func:`detect_board` tries four things in order and stops at the first hit:

1. **KNOWN** - the bundled list ``app/data/known_boards.json`` (well-known companies on the
   four supported vendors), matched by website domain, then by normalised name or alias.
2. **GUESS** - tokens derived from the domain and the name (``stripe``, ``stripe-inc``, ...)
   probed against the four public board APIs; a board with at least one posting is a hit.
3. **SCAN** - the website's home page, then its first careers / jobs link, searched for the
   vendors' hosted board URLs (``boards.greenhouse.io/<t>``, ``jobs.lever.co/<t>``,
   ``jobs.ashbyhq.com/<t>``, ``careers.smartrecruiters.com/<T>``) and for Workday
   (``<tenant>.wd1.myworkdayjobs.com``), which is recognised but cannot be read.
4. **NONE** - nothing found; :attr:`BoardDetection.tried` lists what was checked.

Every found board is verified with one fetch through the board adapters (the same call
``PUT /companies/{id}/board`` makes), which is where ``open_jobs`` comes from.

Politeness and safety, all enforced here:

* at most :data:`MAX_REQUESTS` HTTP requests per detection (board API probes, pages,
  redirects and robots.txt files all count), each with a :data:`TIMEOUT_SECONDS` timeout,
  and a descriptive ``User-Agent``; board API calls go through
  :mod:`app.modules.adapters.boards.http` and share its cache;
* only public pages: ``robots.txt`` is fetched for every host before a page on it, and a
  disallowed (or unreadable) robots.txt skips the scan; links and redirects that lead to a
  login are never followed; a page is only fetched when its host resolves to public
  addresses (no ``localhost``, private ranges or cloud metadata endpoints), on the default
  port, and at most one redirect is followed per page;
* nothing is ever posted, and no CAPTCHA or bot check is worked around - a page that
  answers 401/403 or redirects to a login is simply where the scan stops.

Tests replace the network with :func:`set_transport` (pages and robots.txt) plus
``adapters.boards.http.set_transport`` (board APIs), and DNS with :func:`set_resolver`.
"""
from __future__ import annotations

import html
import ipaddress
import json
import logging
import re
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.exceptions import RateLimitedError
from app.core.rate_limit import rate_limiter
from app.models.enums import JobSourceType
from app.modules.adapters.boards import http as board_http
from app.modules.adapters.boards.http import USER_AGENT, BoardFetchError
from app.modules.adapters.boards.urls import BOARD_VENDORS, TOKEN_RE, BoardUrlError, infer_ats_type, parse_board_url, public_board_url
from app.modules.companies.schemas import BoardDetection

logger = logging.getLogger(__name__)

#: Hard cap on HTTP requests per detection - every probe, page, redirect and robots.txt.
MAX_REQUESTS = 8
TIMEOUT_SECONDS = 10.0
#: Wall-clock budget for one detection; no new request starts after it.
DEADLINE_SECONDS = 45.0
#: Requests kept back from the token guess for the careers page scan when a website is
#: known: robots.txt, the home page, the careers page and the verification fetch.
SCAN_RESERVE = 4
#: Bytes of a page that are read; careers links and board URLs sit well inside this.
MAX_PAGE_BYTES = 1_500_000
#: How many board URLs found on a page are verified at most.
MAX_SCAN_CANDIDATES = 3
#: ``POST /companies/detect-board`` and friends hit third-party sites: per-user limit.
DETECT_RATE_LIMIT_PER_MINUTE = 10

KNOWN_BOARDS_FILE = Path(__file__).resolve().parents[2] / "data" / "known_boards.json"
#: Suggestion / board ordering by tag; anything else sorts after these.
TAG_ORDER: tuple[str, ...] = ("FAANG", "unicorn", "product", "startup")

WORKDAY = "WORKDAY"

_transport: httpx.BaseTransport | None = None
Resolver = Callable[[str], list[str]]


def _system_resolver(host: str) -> list[str]:
    try:
        return sorted({str(info[4][0]) for info in socket.getaddrinfo(host, None)})
    except (OSError, UnicodeError):
        return []


_resolver: Resolver = _system_resolver


def set_transport(transport: httpx.BaseTransport | None) -> None:
    """Route page and robots.txt requests through ``transport`` (tests); ``None`` restores the network."""
    global _transport
    _transport = transport


def set_resolver(resolver: Resolver | None) -> None:
    """Replace DNS resolution for the public-address check (tests); ``None`` restores it."""
    global _resolver
    _resolver = resolver or _system_resolver


def enforce_rate_limit(user_id: object) -> None:
    """At most :data:`DETECT_RATE_LIMIT_PER_MINUTE` detections per user per minute."""
    allowed, _ = rate_limiter.check(f"board-detect:{user_id}", DETECT_RATE_LIMIT_PER_MINUTE, 60)
    if not allowed:
        raise RateLimitedError("Too many career board look-ups. Try again in a minute.")


# --------------------------------------------------------------------------- the known list


@dataclass(frozen=True)
class KnownBoard:
    name: str
    domain: str | None
    ats_type: JobSourceType
    token: str
    tags: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()

    @property
    def board_url(self) -> str:
        return public_board_url(self.ats_type, self.token)


@lru_cache(maxsize=1)
def known_boards() -> tuple[KnownBoard, ...]:
    """The bundled known-board list. Read once; malformed entries are skipped with a warning."""
    try:
        data = json.loads(KNOWN_BOARDS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Known board list %s unreadable: %s", KNOWN_BOARDS_FILE, exc)
        return ()
    boards: list[KnownBoard] = []
    for row in data.get("boards") or []:
        try:
            vendor = JobSourceType(str(row["ats_type"]).strip().upper())
            token = str(row["token"]).strip()
            name = str(row["name"]).strip()
        except (KeyError, ValueError, TypeError):
            logger.warning("Known board entry skipped (malformed): %r", row)
            continue
        if vendor not in BOARD_VENDORS or not TOKEN_RE.match(token) or not name:
            logger.warning("Known board entry skipped (unsupported vendor or bad token): %r", row)
            continue
        domain = str(row.get("domain") or "").strip().lower() or None
        boards.append(
            KnownBoard(
                name=name,
                domain=domain,
                ats_type=vendor,
                token=token,
                tags=tuple(str(t) for t in row.get("tags") or []),
                aliases=tuple(str(a) for a in row.get("aliases") or []),
            )
        )
    return tuple(boards)


def tag_rank(tags: object) -> int:
    """Position of the best-ranked tag in :data:`TAG_ORDER` (``len(TAG_ORDER)`` when none)."""
    ranks = [TAG_ORDER.index(t) for t in (tags or []) if isinstance(t, str) and t in TAG_ORDER]  # type: ignore[union-attr]
    return min(ranks) if ranks else len(TAG_ORDER)


def known_name_keys(board: KnownBoard) -> set[str]:
    """Normalised name and aliases of ``board`` (the keys it is matched by)."""
    from app.modules.companies.service import normalize_company_name

    return {key for key in (normalize_company_name(n) for n in (board.name, *board.aliases)) if key}


@lru_cache(maxsize=1)
def _known_index() -> tuple[dict[str, KnownBoard], dict[str, KnownBoard]]:
    by_name: dict[str, KnownBoard] = {}
    by_domain: dict[str, KnownBoard] = {}
    for board in known_boards():
        for key in known_name_keys(board):
            by_name.setdefault(key, board)
        if board.domain:
            by_domain.setdefault(board.domain, board)
    return by_name, by_domain


def website_host(website: str | None) -> str | None:
    """Lower-case host of a website the user typed (``Stripe.com/jobs`` -> ``stripe.com``), no ``www.``."""
    text = (website or "").strip()
    if not text:
        return None
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or "").strip(".").lower()
    if not host or "." not in host:
        return None
    return host[4:] if host.startswith("www.") else host


def _parent_domains(host: str) -> list[str]:
    labels = host.split(".")
    return [".".join(labels[i:]) for i in range(len(labels) - 1)]


def find_known_board(name: str | None, website: str | None) -> KnownBoard | None:
    """The known-list entry for this website's domain (or a parent domain), else for the name."""
    from app.modules.companies.service import normalize_company_name

    by_name, by_domain = _known_index()
    host = website_host(website)
    if host:
        for domain in _parent_domains(host):
            if domain in by_domain:
                return by_domain[domain]
    key = normalize_company_name(name)
    return by_name.get(key) if key else None


# --------------------------------------------------------------------------- token guessing

_SECOND_LEVEL = frozenset({"co", "com", "org", "net", "ac", "gov", "edu", "ltd", "plc"})


def domain_label(host: str) -> str | None:
    """The registrable label of a host: ``careers.stripe.com`` -> ``stripe``, ``acme.co.in`` -> ``acme``."""
    labels = [label for label in host.split(".") if label]
    if len(labels) < 2:
        return None
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2:
        return labels[-3]
    return labels[-2]


def candidate_tokens(name: str | None, website: str | None) -> list[str]:
    """Board tokens worth guessing, best first.

    The domain label, then the normalised name (legal suffixes dropped) without spaces and
    hyphenated, then the full name the same two ways: ``"Stripe Inc", "stripe.com"`` ->
    ``["stripe", "stripeinc", "stripe-inc"]``.
    """
    from app.modules.companies.service import normalize_company_name

    tokens: list[str] = []
    host = website_host(website)
    if host:
        label = domain_label(host)
        if label:
            tokens.append(label)
    raw = re.sub(r"[^a-z0-9\s-]+", "", (name or "").lower().replace("&", " and ")).replace("-", " ").split()
    for words in (normalize_company_name(name).split(), raw):
        if words:
            tokens.extend(("".join(words), "-".join(words)))
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        if len(token) >= 2 and TOKEN_RE.match(token) and token not in seen:
            seen.add(token)
            out.append(token)
    return out


# --------------------------------------------------------------------------- page scanning

#: Hosted board URLs of the four vendors, with or without a scheme (also inside JSON / JS).
_BOARD_URL_RE = re.compile(
    r"(?<![A-Za-z0-9.-])(?:https?:)?(?://)?"
    r"(?:(?:boards|job-boards|boards-api)\.greenhouse\.io"
    r"|(?:jobs|api)\.lever\.co"
    r"|(?:jobs|api)\.ashbyhq\.com"
    r"|(?:careers|jobs|api)\.smartrecruiters\.com)"
    r"/[^\s\"'<>()\\]+",
    re.IGNORECASE,
)
_WORKDAY_RE = re.compile(
    r"(?<![A-Za-z0-9.-])(?:https?://)?([a-z0-9][a-z0-9-]{0,62})\.(wd\d{1,3})\.myworkdayjobs\.com"
    r"(/(?:[a-z]{2}-[A-Z]{2}/)?[A-Za-z0-9_-]+)?",
    re.IGNORECASE,
)
#: Path segments that are never a board token.
_NOT_TOKENS = frozenset({"embed", "js", "css", "static", "assets", "api", "v0", "v1", "widget", "oneclick-ui", "posting-api", "job-board", "jobs"})
_CAREERS_WORDS = ("careers", "career", "jobs", "job openings", "open positions", "open roles")
_JOIN_WORDS = ("join us", "join our team", "join the team", "work with us", "work-with-us", "workwithus", "join-us", "/join")
_LOGIN_RE = re.compile(r"(log[-_ ]?in|sign[-_ ]?in|sign[-_ ]?up|signup|register|/auth\b|/oauth|/sso\b|/account|/session)", re.IGNORECASE)


def _clean_html(text: str) -> str:
    return html.unescape(text.replace("\\/", "/"))


def find_board_urls(text: str) -> list[tuple[JobSourceType, str]]:
    """``(vendor, token)`` for every hosted board URL in ``text``, most frequent first."""
    counts: dict[tuple[JobSourceType, str], list[int]] = {}
    for position, match in enumerate(_BOARD_URL_RE.finditer(_clean_html(text or ""))):
        url = match.group(0).rstrip(".,;:!?")
        url = "https://" + re.sub(r"^(?:https?:)?(?://)?", "", url, flags=re.IGNORECASE)
        vendor = infer_ats_type(url)
        if vendor is None:
            continue
        try:
            token = parse_board_url(vendor, url)
        except BoardUrlError:
            continue
        if token.lower() in _NOT_TOKENS:
            continue
        key = (vendor, token)
        counts.setdefault(key, [0, position])[0] += 1
    return [key for key, _ in sorted(counts.items(), key=lambda item: (-item[1][0], item[1][1]))]


def find_workday(text: str) -> tuple[str, str] | None:
    """``(tenant, board_url)`` of the first Workday careers site in ``text``."""
    match = _WORKDAY_RE.search(_clean_html(text or ""))
    if not match:
        return None
    tenant, pod, path = match.group(1).lower(), match.group(2).lower(), match.group(3) or ""
    return tenant, f"https://{tenant}.{pod}.myworkdayjobs.com{path}"


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._close()
            self._href = dict(attrs).get("href") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._close()

    def _close(self) -> None:
        if self._href is not None:
            self.links.append((self._href.strip(), " ".join("".join(self._text).split())))
        self._href = None
        self._text = []

    def close(self) -> None:
        super().close()
        self._close()


def _is_login(url_or_text: str) -> bool:
    return bool(_LOGIN_RE.search(url_or_text or ""))


def find_careers_link(text: str, base_url: str) -> str | None:
    """The first careers / jobs link on the page (then the first "join us" / "work with us" one).

    Links to a login or sign-up and non-http(s) links are skipped.
    """
    parser = _LinkParser()
    try:
        parser.feed(text or "")
        parser.close()
    except Exception:  # pragma: no cover - HTMLParser is lenient
        return None
    candidates: list[str] = []
    fallbacks: list[str] = []
    for href, label in parser.links:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base_url, href)
        if urlparse(url).scheme not in ("http", "https"):
            continue
        haystack = f"{label} {href}".lower()
        if _is_login(href) or _is_login(label):
            continue
        if any(word in haystack for word in _CAREERS_WORDS):
            candidates.append(url)
        elif any(word in haystack for word in _JOIN_WORDS) or haystack.strip().startswith("join"):
            fallbacks.append(url)
    for url in candidates + fallbacks:
        if url.rstrip("/") != base_url.rstrip("/"):
            return url
    return None


def normalize_website(website: str | None) -> str | None:
    """``acme.com`` -> ``https://acme.com/``; ``None`` for anything that is not an http(s) URL."""
    text = (website or "").strip()
    if not text:
        return None
    parsed = urlparse(text if "://" in text else f"https://{text}")
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        return None
    return parsed.geturl() if parsed.path else parsed._replace(path="/").geturl()


# --------------------------------------------------------------------------- the detector


@dataclass
class _Probe:
    status: str  # "hit" | "empty" | "not_found" | "unreachable" | "skipped"
    count: int | None = None


@dataclass
class _Response:
    status_code: int
    headers: httpx.Headers
    text: str

    @property
    def is_redirect(self) -> bool:
        return self.status_code in (301, 302, 303, 307, 308) and "location" in self.headers


@dataclass
class _Fetched:
    url: str
    text: str
    board: tuple[JobSourceType, str] | None = None


class _Detector:
    def __init__(self, name: str | None, website: str | None) -> None:
        self.name = (name or "").strip() or None
        self.website = (website or "").strip() or None
        self.requests = 0
        self.tried: list[str] = []
        self.careers_url: str | None = None
        self._capped = False
        self._started = time.monotonic()
        self._robots: dict[str, RobotFileParser] = {}
        self._robots_unreadable: set[str] = set()
        self._public: dict[str, bool] = {}
        self._client: httpx.Client | None = None

    # -- bookkeeping ---------------------------------------------------------

    def _spend(self) -> bool:
        if self.requests >= MAX_REQUESTS or time.monotonic() - self._started > DEADLINE_SECONDS:
            if not self._capped:
                self._capped = True
                reason = f"request cap of {MAX_REQUESTS}" if self.requests >= MAX_REQUESTS else "time budget"
                self.tried.append(f"stopped: {reason} reached")
            return False
        self.requests += 1
        return True

    def _result(self, method: str, **fields: object) -> BoardDetection:
        return BoardDetection(method=method, tried=self.tried, careers_url=self.careers_url, requests=self.requests, **fields)

    def _hit(self, method: str, vendor: JobSourceType, token: str, count: int | None) -> BoardDetection:
        return self._result(
            method,
            ats_type=vendor.value,
            token=token,
            board_url=public_board_url(vendor, token),
            open_jobs=count,
            supported=True,
            board_company=board_company_name(vendor, token),
        )

    # -- board APIs ----------------------------------------------------------

    def _probe(self, vendor: JobSourceType, token: str, step: str) -> _Probe:
        """One verification fetch of ``token``'s board on ``vendor`` (via the board adapter)."""
        from app.modules.adapters.registry import get_adapter

        label = f"{step}: {vendor.value}/{token}"
        if not self._spend():
            return _Probe("skipped")
        try:
            with board_http.request_timeout(TIMEOUT_SECONDS):
                count = int(get_adapter(vendor).count_board_jobs(token))
        except board_http.BoardNotFound:
            self.tried.append(f"{label} - no board")
            return _Probe("not_found")
        except board_http.BoardPayloadError:
            self.tried.append(f"{label} - not a job board")
            return _Probe("not_found")
        except BoardFetchError as exc:
            logger.info("Board detection: %s unreachable: %s", label, exc)
            self.tried.append(f"{label} - could not be reached")
            return _Probe("unreachable")
        if count <= 0:
            self.tried.append(f"{label} - no open jobs")
            return _Probe("empty", 0)
        owner = board_company_name(vendor, token)
        self.tried.append(f"{label} - {count} open jobs" + (f" (board of '{owner}')" if owner else ""))
        return _Probe("hit", count)

    # -- pages ---------------------------------------------------------------

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"},
                follow_redirects=False,
                transport=_transport,
            )
        return self._client

    def _is_public(self, host: str) -> bool:
        if host not in self._public:
            if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
                addresses: list[str] = []
            else:
                try:
                    addresses = [str(ipaddress.ip_address(host))]
                except ValueError:
                    addresses = _resolver(host)
            try:
                self._public[host] = bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)
            except ValueError:
                self._public[host] = False
        return self._public[host]

    def _check_url(self, url: str, what: str) -> bool:
        """Scheme, port and public-address checks for a page URL; records why it is refused."""
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        try:
            port = parsed.port
        except ValueError:
            port = -1
        if parsed.scheme not in ("http", "https") or not host or port not in (None, 80, 443):
            self.tried.append(f"scan: {what} {url} is not a plain http(s) address - skipped")
            return False
        if not self._is_public(host):
            self.tried.append(f"scan: {what} {url} does not resolve to a public address - skipped")
            return False
        return True

    def _get(self, url: str) -> _Response | None:
        """One GET (no redirects followed), body capped at :data:`MAX_PAGE_BYTES`."""
        if not self._spend():
            return None
        try:
            with self._http().stream("GET", url) as response:
                body = bytearray()
                if not response.is_redirect:
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) >= MAX_PAGE_BYTES:
                            break
                text = bytes(body[:MAX_PAGE_BYTES]).decode(response.encoding or "utf-8", errors="replace")
                return _Response(response.status_code, response.headers, text)
        except (httpx.HTTPError, LookupError) as exc:
            self.tried.append(f"scan: could not fetch {url} ({type(exc).__name__})")
            return None

    def _robots_allows(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._robots.get(origin)
        if parser is None:
            parser = RobotFileParser()
            robots_url = f"{origin}/robots.txt"
            response = self._get(robots_url)
            target_origin: str | None = None
            if response is not None and response.is_redirect:
                target = urljoin(robots_url, response.headers.get("location", ""))
                target_parsed = urlparse(target)
                target_origin = f"{target_parsed.scheme}://{target_parsed.netloc}"
                response = self._get(target) if self._check_url(target, "robots.txt") else None
            if response is None:
                parser.disallow_all = True  # unknown rules: do not scan
                self._robots_unreadable.add(origin)
            elif response.status_code in (401, 403):
                parser.disallow_all = True
            elif 400 <= response.status_code < 500:
                parser.allow_all = True  # no robots.txt: everything is allowed
            elif response.status_code >= 300:
                parser.disallow_all = True  # 5xx or a second redirect: treat as "do not crawl"
                self._robots_unreadable.add(origin)
            else:
                parser.parse(response.text.splitlines())
            self._robots[origin] = parser
            if target_origin and target_origin != origin:
                # ``http://acme.com/robots.txt`` -> ``https://www.acme.com/robots.txt``: the file
                # just read is that origin's own, so the home page redirect costs no second fetch.
                self._robots.setdefault(target_origin, parser)
                if origin in self._robots_unreadable:
                    self._robots_unreadable.add(target_origin)
        return parser.can_fetch(USER_AGENT, url)

    def _fetch_page(self, url: str, what: str) -> _Fetched | None:
        """Fetch a public page, following at most one redirect; never a login page."""
        for hop in range(2):
            parsed = urlparse(url)
            if _is_login(f"{parsed.hostname or ''}{parsed.path}"):
                self.tried.append(f"scan: {what} {url} leads to a login - not followed")
                return None
            if not self._check_url(url, what):
                return None
            if not self._robots_allows(url):
                origin = f"{parsed.scheme}://{parsed.netloc}"
                if self._capped:
                    pass
                elif origin in self._robots_unreadable:
                    self.tried.append(f"scan: {origin}/robots.txt could not be read - scan skipped")
                else:
                    self.tried.append(f"scan: robots.txt disallows {url} - skipped")
                return None
            response = self._get(url)
            if response is None:
                return None
            if response.is_redirect:
                target = urljoin(url, response.headers.get("location", ""))
                board = _board_in_url(target)
                if board is not None:  # the careers link redirects straight to a hosted board
                    return _Fetched(url=target, text="", board=board)
                if find_workday(target):
                    return _Fetched(url=target, text=target)
                if hop == 1:
                    self.tried.append(f"scan: {what} {url} redirects more than once - stopped")
                    return None
                url = target
                continue
            if response.status_code in (401, 403):
                # A login wall or a bot check: either way a human's page, never worked around.
                self.tried.append(f"scan: {what} {url} refused access (HTTP {response.status_code}) - stopped")
                return None
            if response.status_code >= 400:
                self.tried.append(f"scan: {what} {url} answered HTTP {response.status_code}")
                return None
            content_type = response.headers.get("content-type", "").lower()
            if content_type and "html" not in content_type and "text/plain" not in content_type:
                self.tried.append(f"scan: {what} {url} is not a web page ({content_type.split(';')[0]})")
                return None
            return _Fetched(url=url, text=response.text)
        return None  # pragma: no cover - the loop always returns

    # -- the steps -----------------------------------------------------------

    def _scan(self) -> BoardDetection | None:
        start = normalize_website(self.website)
        if start is None:
            self.tried.append(f"scan: {self.website!r} is not a website address - skipped")
            return None
        home = self._fetch_page(start, "website")
        if home is None:
            return None
        self.tried.append(f"scan: read {home.url}")

        boards: list[tuple[JobSourceType, str]] = [home.board] if home.board else find_board_urls(home.text)
        workday = find_workday(home.text)
        if not boards:
            link = find_careers_link(home.text, home.url)
            if link is None:
                self.tried.append(f"scan: no careers link on {home.url}")
            else:
                self.careers_url = link[:500]
                direct = _board_in_url(link)
                if direct is not None:
                    boards = [direct]
                elif find_workday(link):
                    workday = find_workday(link)
                else:
                    page = self._fetch_page(link, "careers page")
                    if page is not None:
                        self.careers_url = page.url[:500]
                        self.tried.append(f"scan: read {page.url}")
                        boards = [page.board] if page.board else find_board_urls(page.text)
                        workday = find_workday(page.text) or workday
        if not boards and not workday and not self._capped:
            self.tried.append("scan: no job board link found")

        for vendor, token in boards[:MAX_SCAN_CANDIDATES]:
            probe = self._probe(vendor, token, "scan")
            if probe.status == "hit":
                return self._hit("SCAN", vendor, token, probe.count)
            if probe.status == "skipped":
                break
        if workday is not None:
            tenant, url = workday
            self.tried.append(f"scan: Workday careers site {url} - recognised, but JobPilot cannot read Workday boards")
            return self._result("SCAN", ats_type=WORKDAY, token=tenant, board_url=url[:500], supported=False)
        return None

    def run(self) -> BoardDetection:
        if not self.name and not self.website:
            self.tried.append("nothing to look up: give a company name or a website")
            return self._result("NONE")
        try:
            return self._run()
        finally:
            if self._client is not None:
                self._client.close()

    def _run(self) -> BoardDetection:
        # 1. the known list
        known = find_known_board(self.name, self.website)
        if known is not None:
            probe = self._probe(known.ats_type, known.token, "known")
            if probe.status == "hit":
                return self._hit("KNOWN", known.ats_type, known.token, probe.count)
            if probe.status == "unreachable":
                # The list was verified when it was written; a vendor outage is not a reason
                # to forget the mapping. Not counted, so ``open_jobs`` stays unknown.
                return self._hit("KNOWN", known.ats_type, known.token, None)
        else:
            self.tried.append("known: not on the known-board list")

        # 2. token guesses, keeping enough requests back for the careers page scan
        reserve = SCAN_RESERVE if self.website else 0
        budget = max(0, MAX_REQUESTS - self.requests - reserve)
        skip = {(known.ats_type, known.token.lower())} if known else set()
        tokens = candidate_tokens(self.name, self.website)
        spent = 0
        for token in tokens:
            for vendor in BOARD_VENDORS:
                if (vendor, token.lower()) in skip:
                    continue
                if spent >= budget:
                    break
                spent += 1
                probe = self._probe(vendor, token, "guess")
                if probe.status == "hit":
                    return self._hit("GUESS", vendor, token, probe.count)
            if spent >= budget:
                break
        if not tokens:
            self.tried.append("guess: no usable token in the name or website")

        # 3. the careers page scan
        if self.website:
            found = self._scan()
            if found is not None:
                return found
        else:
            self.tried.append("scan: no website given")

        # 4. nothing
        return self._result("NONE")


def board_company_name(vendor: JobSourceType, token: str) -> str | None:
    """The company name on a board just verified, from the cached answer (no request).

    Greenhouse puts ``company_name`` on every job and SmartRecruiters ``company.name`` on
    every posting; Lever and Ashby do not say.
    """
    from app.modules.adapters.registry import get_adapter

    try:
        adapter = get_adapter(vendor)
        if vendor is JobSourceType.GREENHOUSE:
            payload = board_http.cached_json(adapter.api_url(token))
            rows = payload.get("jobs") if isinstance(payload, dict) else None
            value = rows[0].get("company_name") if rows and isinstance(rows[0], dict) else None
        elif vendor is JobSourceType.SMARTRECRUITERS:
            payload = board_http.cached_json(adapter.api_url(token, 0))
            rows = payload.get("content") if isinstance(payload, dict) else None
            company = rows[0].get("company") if rows and isinstance(rows[0], dict) else None
            value = company.get("name") if isinstance(company, dict) else None
        else:
            return None
    except Exception:  # noqa: BLE001 - purely informational
        return None
    text = " ".join(str(value or "").split())
    return text[:255] or None


def _board_in_url(url: str) -> tuple[JobSourceType, str] | None:
    found = find_board_urls(url)
    return found[0] if found else None


def detect_board(name: str | None, website: str | None) -> BoardDetection:
    """Find the public job board of the company called ``name`` with website ``website``.

    Never raises for network problems: anything that fails is recorded in ``tried`` and the
    detection moves on. See the module docstring for the steps and the limits.
    """
    detection = _Detector(name, website).run()
    logger.info(
        "Board detection for name=%r website=%r: %s %s/%s (%d requests)",
        name,
        website,
        detection.method,
        detection.ats_type,
        detection.token,
        detection.requests,
    )
    return detection


__all__ = [
    "DETECT_RATE_LIMIT_PER_MINUTE",
    "KnownBoard",
    "MAX_REQUESTS",
    "candidate_tokens",
    "detect_board",
    "enforce_rate_limit",
    "find_board_urls",
    "find_careers_link",
    "find_known_board",
    "find_workday",
    "known_boards",
    "set_resolver",
    "set_transport",
    "tag_rank",
]
