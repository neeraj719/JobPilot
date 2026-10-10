"""Turn whatever the user pasted - a board URL, a job URL, an API URL or a bare token -
into the board token each vendor's public API is keyed by.

=================  ==================================================================
Vendor             Accepted forms (``{t}`` is the token)
=================  ==================================================================
Greenhouse         ``boards.greenhouse.io/{t}``, ``job-boards.greenhouse.io/{t}[/jobs/..]``,
                   ``boards.greenhouse.io/embed/job_board?for={t}``,
                   ``boards-api.greenhouse.io/v1/boards/{t}/jobs``
Lever              ``jobs.lever.co/{t}[/<posting>]``, ``api.lever.co/v0/postings/{t}``
Ashby              ``jobs.ashbyhq.com/{t}[/<posting>]``,
                   ``api.ashbyhq.com/posting-api/job-board/{t}``
SmartRecruiters    ``jobs.smartrecruiters.com/{t}[/<posting>]``, ``careers.smartrecruiters.com/{t}``,
                   ``jobs.smartrecruiters.com/oneclick-ui/company/{t}/..``,
                   ``api.smartrecruiters.com/v1/companies/{t}/postings``
=================  ==================================================================

A bare token (``stripe``) is accepted for every vendor. The token is the only thing the
adapters ever put into a request URL, and it is restricted to :data:`TOKEN_RE`, so a
pasted URL can never steer a request to another host.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, quote, urlparse

from app.models.enums import JobSourceType

#: Letters, digits, dot, dash and underscore - every real board token fits.
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

BOARD_VENDORS: tuple[JobSourceType, ...] = (
    JobSourceType.GREENHOUSE,
    JobSourceType.LEVER,
    JobSourceType.ASHBY,
    JobSourceType.SMARTRECRUITERS,
)

#: Host suffix -> vendor.
_HOSTS: dict[JobSourceType, tuple[str, ...]] = {
    JobSourceType.GREENHOUSE: ("greenhouse.io",),
    JobSourceType.LEVER: ("lever.co",),
    JobSourceType.ASHBY: ("ashbyhq.com",),
    JobSourceType.SMARTRECRUITERS: ("smartrecruiters.com",),
}

_DISPLAY = {
    JobSourceType.GREENHOUSE: "Greenhouse",
    JobSourceType.LEVER: "Lever",
    JobSourceType.ASHBY: "Ashby",
    JobSourceType.SMARTRECRUITERS: "SmartRecruiters",
}


class BoardUrlError(ValueError):
    """The value is neither a board URL of the expected vendor nor a usable token."""


def _vendor(ats_type: JobSourceType | str) -> JobSourceType:
    try:
        vendor = ats_type if isinstance(ats_type, JobSourceType) else JobSourceType(str(ats_type).strip().upper())
    except ValueError as exc:
        raise BoardUrlError(f"Unknown ATS type {ats_type!r}") from exc
    if vendor not in BOARD_VENDORS:
        raise BoardUrlError(f"{vendor.value} has no public job board API JobPilot can read")
    return vendor


def _host_matches(host: str, suffixes: tuple[str, ...]) -> bool:
    return any(host == suffix or host.endswith("." + suffix) for suffix in suffixes)


def _looks_like_url(value: str) -> bool:
    return "/" in value or value.lower().startswith(("http:", "https:")) or any(
        suffix in value.lower() for suffixes in _HOSTS.values() for suffix in suffixes
    )


def infer_ats_type(value: str | None) -> JobSourceType | None:
    """The vendor whose host ``value`` points at, or ``None`` (bare tokens, other hosts)."""
    text = (value or "").strip()
    if not text or not _looks_like_url(text):
        return None
    host = (urlparse(text if "://" in text else f"https://{text}").hostname or "").lower()
    for vendor, suffixes in _HOSTS.items():
        if _host_matches(host, suffixes):
            return vendor
    return None


def _segments(path: str) -> list[str]:
    return [segment for segment in path.split("/") if segment]


def _token_from_url(vendor: JobSourceType, host: str, segments: list[str], query: dict[str, list[str]]) -> str | None:
    if vendor is JobSourceType.GREENHOUSE:
        if "for" in query:  # embed/job_board?for=<token>, embed/job_app?for=<token>&token=<job>
            return query["for"][0]
        if host.startswith("boards-api.") or host.startswith("api."):
            # /v1/boards/<token>/jobs
            if "boards" in segments:
                index = segments.index("boards")
                return segments[index + 1] if index + 1 < len(segments) else None
            return None
        return segments[0] if segments and segments[0] != "embed" else None
    if vendor is JobSourceType.LEVER:
        if host.startswith("api."):
            # /v0/postings/<token>
            if "postings" in segments:
                index = segments.index("postings")
                return segments[index + 1] if index + 1 < len(segments) else None
            return None
        return segments[0] if segments else None
    if vendor is JobSourceType.ASHBY:
        if host.startswith("api."):
            # /posting-api/job-board/<token>
            if "job-board" in segments:
                index = segments.index("job-board")
                return segments[index + 1] if index + 1 < len(segments) else None
            return None
        return segments[0] if segments else None
    # SmartRecruiters
    if host.startswith("api."):
        # /v1/companies/<token>/postings
        if "companies" in segments:
            index = segments.index("companies")
            return segments[index + 1] if index + 1 < len(segments) else None
        return None
    if len(segments) >= 3 and segments[0] == "oneclick-ui" and segments[1] == "company":
        return segments[2]
    return segments[0] if segments else None


def parse_board_url(ats_type: JobSourceType | str, value: str | None) -> str:
    """Return the board token for ``value`` on ``ats_type``.

    Raises :class:`BoardUrlError` when ``value`` is empty, points at another vendor, or
    does not contain a token.
    """
    vendor = _vendor(ats_type)
    text = (value or "").strip()
    if not text:
        raise BoardUrlError("A board URL or token is required")

    if not _looks_like_url(text):
        if TOKEN_RE.match(text):
            return text
        raise BoardUrlError(f"{text!r} is not a valid {_DISPLAY[vendor]} board token")

    parsed = urlparse(text if "://" in text else f"https://{text}")
    if parsed.scheme.lower() not in ("http", "https"):
        raise BoardUrlError("Board URLs must be http(s) addresses")
    host = (parsed.hostname or "").lower()
    if not _host_matches(host, _HOSTS[vendor]):
        raise BoardUrlError(f"{text!r} is not a {_DISPLAY[vendor]} board URL")
    token = _token_from_url(vendor, host, _segments(parsed.path), parse_qs(parsed.query))
    if not token or not TOKEN_RE.match(token):
        raise BoardUrlError(f"Could not find a {_DISPLAY[vendor]} board token in {text!r}")
    return token


def public_board_url(ats_type: JobSourceType | str, token: str) -> str:
    """The human-facing board page for ``token`` (stored for display when only a token was given)."""
    vendor = _vendor(ats_type)
    safe = quote(token, safe="")
    return {
        JobSourceType.GREENHOUSE: f"https://job-boards.greenhouse.io/{safe}",
        JobSourceType.LEVER: f"https://jobs.lever.co/{safe}",
        JobSourceType.ASHBY: f"https://jobs.ashbyhq.com/{safe}",
        JobSourceType.SMARTRECRUITERS: f"https://jobs.smartrecruiters.com/{safe}",
    }[vendor]
