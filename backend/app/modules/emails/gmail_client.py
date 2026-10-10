"""Thin, read-only Gmail API wrapper (contract §13).

Scope discipline: this client only ever *reads* (``gmail.readonly``). It never sends,
modifies or deletes mail, and it never stores the raw message — only the normalised
:class:`IncomingEmail` the pipeline needs.

The search query is deliberately narrow (recruiting subjects + known ATS senders) so
JobPilot pulls as little of the user's mailbox as possible.
"""
from __future__ import annotations

import base64
import binascii
import html
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from app.core.exceptions import ExternalServiceError
from app.modules.emails.schemas import IncomingEmail

logger = logging.getLogger(__name__)

#: Subject keywords and sender fragments used to keep the sync narrow (contract §13).
QUERY_SUBJECT_TERMS = ("application", "interview", "offer", "assessment", "recruiter", "position", "role")
QUERY_FROM_TERMS = ("greenhouse", "lever", "workday", "naukri", "linkedin", "indeed")

DEFAULT_MAX_RESULTS = 50
DEFAULT_NEWER_THAN_DAYS = 30
MAX_BODY_CHARS = 100_000

_SCRIPT_RE = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_BREAK_RE = re.compile(r"(?i)<(br\s*/?|/p|/div|/tr|/li|/h[1-6])>")
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


# --------------------------------------------------------------------------- pure helpers


def build_query(newer_than_days: int = DEFAULT_NEWER_THAN_DAYS) -> str:
    """The Gmail search query used by :meth:`GmailClient.list_job_related_messages`."""
    days = max(1, int(newer_than_days or DEFAULT_NEWER_THAN_DAYS))
    subjects = " OR ".join(QUERY_SUBJECT_TERMS)
    senders = " OR ".join(QUERY_FROM_TERMS)
    return f"newer_than:{days}d (subject:({subjects}) OR from:({senders}))"


def decode_body_data(data: str | None) -> str:
    """Decode a base64url-encoded Gmail body part (tolerates missing padding)."""
    if not data:
        return ""
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        logger.warning("Could not decode a Gmail body part: %s", exc)
        return ""


def strip_html(markup: str) -> str:
    """Best-effort plain text from an HTML body (no external dependency)."""
    if not markup:
        return ""
    text = _SCRIPT_RE.sub(" ", markup)
    text = _BREAK_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = "\n".join(" ".join(line.split()) for line in text.splitlines())
    return _BLANK_LINES_RE.sub("\n\n", text).strip()


def _walk_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    stack = [payload or {}]
    while stack:
        part = stack.pop(0)
        if not isinstance(part, dict):
            continue
        parts.append(part)
        children = part.get("parts")
        if isinstance(children, list):
            stack.extend(children)
    return parts


def extract_body(payload: dict[str, Any]) -> str:
    """Prefer ``text/plain``; fall back to HTML with the tags stripped."""
    plain: list[str] = []
    markup: list[str] = []
    for part in _walk_parts(payload):
        mime = str(part.get("mimeType") or "").lower()
        data = (part.get("body") or {}).get("data")
        if not data:
            continue
        if mime.startswith("text/plain"):
            plain.append(decode_body_data(data))
        elif mime.startswith("text/html"):
            markup.append(decode_body_data(data))
    if plain:
        return "\n".join(chunk for chunk in plain if chunk).strip()[:MAX_BODY_CHARS]
    if markup:
        return strip_html("\n".join(markup))[:MAX_BODY_CHARS]
    return ""


def header_map(payload: dict[str, Any]) -> dict[str, str]:
    """``{"from": ..., "subject": ...}`` — header names lowercased."""
    headers = {}
    for header in (payload or {}).get("headers") or []:
        name = str(header.get("name") or "").strip().lower()
        if name:
            headers[name] = str(header.get("value") or "")
    return headers


def _received_at(raw: dict[str, Any], headers: dict[str, str]) -> datetime:
    internal = raw.get("internalDate")
    if internal:
        try:
            return datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            logger.debug("Unusable internalDate %r", internal)
    date_header = headers.get("date")
    if date_header:
        try:
            parsed = parsedate_to_datetime(date_header)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            logger.debug("Unusable Date header %r", date_header)
    return datetime.now(timezone.utc)


def parse_message(raw: dict[str, Any], message_id: str | None = None) -> IncomingEmail:
    """Turn a ``users.messages.get(format="full")`` payload into an :class:`IncomingEmail`.

    ``message_id`` is the id that was requested; it is used when the payload does not
    echo one back.
    """
    raw = raw or {}
    payload = raw.get("payload") or {}
    headers = header_map(payload)
    body = extract_body(payload)
    provider_message_id = str(raw.get("id") or message_id or "").strip()
    if not provider_message_id:
        raise ValueError("Gmail payload has no message id")
    return IncomingEmail(
        provider_message_id=provider_message_id,
        thread_id=str(raw.get("threadId")) if raw.get("threadId") else None,
        sender=headers.get("from", "")[:500],
        recipient=(headers.get("to") or headers.get("delivered-to") or None),
        subject=headers.get("subject", "")[:1000],
        snippet=html.unescape(str(raw.get("snippet") or "")) or None,
        body_text=body or None,
        received_at=_received_at(raw, headers),
        raw_headers={key: headers[key] for key in ("from", "to", "subject", "date", "message-id", "reply-to") if key in headers},
        is_simulated=False,
    )


# --------------------------------------------------------------------------- client


class GmailClient:
    """Read-only Gmail access for one connected account.

    ``credentials_json`` is the decrypted OAuth bundle stored on ``EmailIntegration``.
    When the access token is refreshed, :attr:`refreshed` flips to ``True`` and
    :meth:`credentials_json_dict` returns the bundle the caller must re-encrypt.
    """

    def __init__(self, credentials_json: dict[str, Any], *, service: Any | None = None) -> None:
        self._credentials_json: dict[str, Any] = dict(credentials_json or {})
        self._service = service
        self._credentials: Any | None = None
        self.refreshed = False

    # -- credentials ---------------------------------------------------------

    def credentials_json_dict(self) -> dict[str, Any]:
        """The current (possibly refreshed) OAuth bundle, ready to be re-encrypted."""
        return dict(self._credentials_json)

    def _build_credentials(self) -> Any:
        from google.oauth2.credentials import Credentials  # noqa: PLC0415 - optional heavy import

        info = dict(self._credentials_json)
        scopes = info.get("scopes") or None
        try:
            return Credentials.from_authorized_user_info(info, scopes)
        except (ValueError, KeyError) as exc:
            logger.debug("from_authorized_user_info rejected the stored bundle (%s); building manually", exc)
            return Credentials(
                token=info.get("token"),
                refresh_token=info.get("refresh_token"),
                token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=info.get("client_id"),
                client_secret=info.get("client_secret"),
                scopes=scopes,
            )

    def _refresh_if_needed(self, credentials: Any) -> Any:
        if not getattr(credentials, "expired", False) or not getattr(credentials, "refresh_token", None):
            return credentials
        from google.auth.transport.requests import Request  # noqa: PLC0415 - optional heavy import

        logger.info("Refreshing the Gmail access token")
        credentials.refresh(Request())
        expiry = getattr(credentials, "expiry", None)
        self._credentials_json.update(
            {
                "token": credentials.token,
                "refresh_token": credentials.refresh_token or self._credentials_json.get("refresh_token"),
                "expiry": expiry.isoformat() if expiry else None,
            }
        )
        self.refreshed = True
        return credentials

    def _get_service(self) -> Any:
        """The Gmail API resource (injected in tests, built from credentials otherwise)."""
        if self._service is not None:
            return self._service
        try:
            from googleapiclient.discovery import build  # noqa: PLC0415 - optional heavy import

            credentials = self._refresh_if_needed(self._build_credentials())
            self._credentials = credentials
            self._service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        except ExternalServiceError:
            raise
        except Exception as exc:  # noqa: BLE001 - every google-api failure is external
            logger.exception("Could not build the Gmail client: %s", exc)
            raise ExternalServiceError("Could not connect to Gmail", code="gmail_unavailable") from exc
        return self._service

    # -- reads ---------------------------------------------------------------

    def list_job_related_messages(
        self,
        max_results: int = DEFAULT_MAX_RESULTS,
        newer_than_days: int = DEFAULT_NEWER_THAN_DAYS,
    ) -> list[str]:
        """Message ids of recent recruiting mail, newest first."""
        service = self._get_service()
        query = build_query(newer_than_days)
        try:
            response = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max(1, min(int(max_results or DEFAULT_MAX_RESULTS), 200)))
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gmail message list failed: %s", exc)
            raise ExternalServiceError("Could not list Gmail messages", code="gmail_list_failed") from exc
        messages = (response or {}).get("messages") or []
        ids = [str(item.get("id")) for item in messages if isinstance(item, dict) and item.get("id")]
        logger.info("Gmail returned %d message(s) for query %s", len(ids), query)
        return ids

    def get_message(self, message_id: str) -> IncomingEmail:
        """Fetch one message and normalise it into an :class:`IncomingEmail`."""
        service = self._get_service()
        try:
            raw = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gmail message fetch failed for %s: %s", message_id, exc)
            raise ExternalServiceError("Could not fetch a Gmail message", code="gmail_fetch_failed") from exc
        try:
            return parse_message(raw or {}, message_id=message_id)
        except ValueError as exc:
            raise ExternalServiceError("Gmail returned an unreadable message", code="gmail_bad_payload") from exc

    def get_profile_email(self) -> str | None:
        """The connected mailbox address (``users.getProfile``)."""
        service = self._get_service()
        try:
            profile = service.users().getProfile(userId="me").execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gmail profile fetch failed: %s", exc)
            raise ExternalServiceError("Could not read the Gmail profile", code="gmail_profile_failed") from exc
        address = (profile or {}).get("emailAddress")
        return str(address) if address else None


__all__ = [
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_NEWER_THAN_DAYS",
    "GmailClient",
    "build_query",
    "decode_body_data",
    "extract_body",
    "header_map",
    "parse_message",
    "strip_html",
]
