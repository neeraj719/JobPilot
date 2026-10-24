"""LinkedIn OAuth 2.0 (authorization-code flow, OpenID Connect) + the official REST calls.

What this module talks to, and nothing else (LinkedIn's terms and this project's rules
forbid scraping the profile page or automating a browser against LinkedIn; there are no
hooks for it here):

* ``{LINKEDIN_AUTH_BASE}/authorization``  — the consent screen (browser redirect);
* ``{LINKEDIN_AUTH_BASE}/accessToken``    — code → token, refresh token → token;
* ``{LINKEDIN_AUTH_BASE}/revoke``         — best-effort revocation on disconnect;
* ``{LINKEDIN_API_BASE}/v2/userinfo``     — "Sign In with LinkedIn using OpenID Connect":
  ``sub``, name, given/family name, picture, email, locale. **No positions, education or
  skills** — LinkedIn's generally available API does not return them;
* ``{LINKEDIN_API_BASE}/rest/memberSnapshotData`` — Member Data Portability (3rd party),
  only when ``LINKEDIN_DMA_ENABLED`` and the member granted ``r_dma_portability_3rd_party``
  (EU/EEA members, after LinkedIn approved the app).

CSRF / replay protection (the Gmail pattern, tightened):

* ``state`` is a JWT signed with ``SECRET_KEY`` that names the user (``sub``), expires after
  :data:`STATE_TTL_SECONDS` and carries a random ``jti``. The ``jti`` is stored on the
  connection row and cleared as soon as the callback spends it (single use), and the whole
  state is mirrored into an ``HttpOnly`` cookie that must come back with the callback (the
  browser finishing the flow is the one that started it).
* PKCE (``S256``) only when ``LINKEDIN_PKCE_ENABLED`` (default off: LinkedIn's web flow
  answered "authorization code not found" for codes requested with a ``code_challenge``).
  The verifier, when used, lives encrypted on the row, never in the browser.
* The ID token's signature is verified against LinkedIn's JWKS (cached 1 h); ``aud`` must be
  our client id, ``exp`` in the future, ``iss`` LinkedIn's. LinkedIn omits ``nonce``: a missing
  one is accepted (the state already matched), a different one is refused. Identity always
  comes from ``/v2/userinfo``.

Tokens are Fernet-encrypted (``encrypt_str``) before they touch the database and never
appear in a response, a log line, an error message or audit metadata.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.exceptions import ExternalServiceError, ValidationFailed
from app.core.security import decrypt_str, encrypt_str
from app.models.base import utcnow
from app.models.enums import Actor, AuditLevel
from app.models.linkedin import (
    LINKEDIN_CONNECTED,
    LINKEDIN_ERROR,
    LINKEDIN_EXPIRED,
    LINKEDIN_PENDING,
    LINKEDIN_REVOKED,
    LinkedInConnection,
)

logger = logging.getLogger(__name__)

BASE_SCOPES: tuple[str, ...] = ("openid", "profile", "email")
DMA_SCOPE = "r_dma_portability_3rd_party"
#: Member Snapshot API domains read on sync (same shapes as the export CSVs).
SNAPSHOT_DOMAINS: tuple[str, ...] = ("PROFILE", "POSITIONS", "EDUCATION", "SKILLS", "CERTIFICATIONS", "LANGUAGES")
#: ``LinkedIn-Version`` header for the versioned ``/rest`` API.
LINKEDIN_API_VERSION = "202312"
MAX_SNAPSHOT_PAGES = 10
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
USER_AGENT = "JobPilot-AI/1.0 (+official LinkedIn API client)"

STATE_COOKIE_NAME = "linkedin_oauth_state"
STATE_TOKEN_TYPE = "linkedin_oauth_state"
#: A consent round trip that takes longer than this is treated as stale.
STATE_TTL_SECONDS = 600
#: Refresh (or call the token expired) this long before ``token_expires_at``.
TOKEN_EXPIRY_MARGIN = timedelta(minutes=5)
MAX_ERROR_CHARS = 500

#: Injected by the tests (``httpx.MockTransport``) — the fake LinkedIn server.
_transport: httpx.BaseTransport | None = None


def set_transport(transport: httpx.BaseTransport | None) -> None:
    """Route every LinkedIn call through ``transport`` (tests); ``None`` restores the network."""
    global _transport
    _transport = transport


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=HTTP_TIMEOUT,
        transport=_transport,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


class DmaUnavailable(Exception):
    """The Member Snapshot API refused (scope not granted, member not eligible, app not approved)."""


class TokenRejected(Exception):
    """LinkedIn answered 401: the token expired or the member revoked the app."""


# --------------------------------------------------------------------------- configuration


def is_configured() -> bool:
    return bool(settings.LINKEDIN_CLIENT_ID and settings.LINKEDIN_CLIENT_SECRET)


def ensure_configured() -> None:
    if not is_configured():
        raise ValidationFailed(
            "LinkedIn is not configured on this server. Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET.",
            code="not_configured",
        )


def requested_scopes() -> list[str]:
    scopes = list(BASE_SCOPES)
    if settings.LINKEDIN_DMA_ENABLED:
        scopes.append(DMA_SCOPE)
    return scopes


def parse_scopes(raw: Any) -> list[str]:
    """LinkedIn returns ``scope`` comma-separated (``"email,openid,profile"``); accept spaces too."""
    if isinstance(raw, list):
        items = [str(s) for s in raw]
    else:
        items = str(raw or "").replace(",", " ").split()
    seen: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.append(item)
    return seen


def expected_issuer() -> str:
    """``https://www.linkedin.com/oauth`` for the default auth base (``…/oauth/v2``)."""
    base = settings.LINKEDIN_AUTH_BASE.rstrip("/")
    return base[: -len("/v2")] if base.endswith("/v2") else base


# --------------------------------------------------------------------------- connection row


def get_connection(db: Session, user_id: uuid.UUID) -> LinkedInConnection | None:
    """The user's live connection row (the soft-delete filter hides tombstones)."""
    return db.scalars(select(LinkedInConnection).where(LinkedInConnection.user_id == user_id)).first()


def get_or_create_connection(db: Session, user_id: uuid.UUID) -> LinkedInConnection:
    connection = get_connection(db, user_id)
    if connection is None:
        connection = LinkedInConnection(
            user_id=user_id, status=LINKEDIN_PENDING, scopes=[], profile_snapshot={}, last_sync_diff={}, auto_sync=True
        )
        db.add(connection)
        db.flush()
    return connection


def store_tokens(connection: LinkedInConnection, token: dict[str, Any]) -> None:
    """Encrypt and persist a token response (the refresh token only when LinkedIn sent one)."""
    access = token.get("access_token")
    if not access:
        raise ExternalServiceError("LinkedIn did not return an access token", code="token_exchange_failed")
    connection.encrypted_access_token = encrypt_str(str(access))
    if token.get("refresh_token"):
        connection.encrypted_refresh_token = encrypt_str(str(token["refresh_token"]))
    try:
        expires_in = int(token.get("expires_in") or 0)
    except (TypeError, ValueError):
        expires_in = 0
    # LinkedIn's member tokens live 60 days; assume that when the field is missing.
    connection.token_expires_at = utcnow() + timedelta(seconds=expires_in or 60 * 24 * 3600)
    granted = parse_scopes(token.get("scope"))
    if granted:
        connection.scopes = granted


def _decrypt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return decrypt_str(value)
    except (ValueError, TypeError) as exc:
        raise ExternalServiceError("The stored LinkedIn token is unreadable; reconnect LinkedIn", code="credentials_unreadable") from exc


def wipe_tokens(connection: LinkedInConnection) -> None:
    connection.encrypted_access_token = None
    connection.encrypted_refresh_token = None
    connection.token_expires_at = None
    connection.oauth_state = None
    connection.encrypted_oauth_pending = None


def token_is_expired(connection: LinkedInConnection) -> bool:
    expires = connection.token_expires_at
    return expires is not None and expires - TOKEN_EXPIRY_MARGIN <= utcnow()


# --------------------------------------------------------------------------- state + PKCE


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def pkce_pair() -> tuple[str, str]:
    """``(code_verifier, S256 code_challenge)`` — RFC 7636."""
    verifier = _b64url(secrets.token_bytes(48))  # 64 chars, inside the 43–128 range
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def issue_state(user_id: uuid.UUID) -> tuple[str, str]:
    """A signed, user-bound, short-lived ``state`` and its ``jti``."""
    jti = secrets.token_urlsafe(24)
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(user_id), "type": STATE_TOKEN_TYPE, "jti": jti, "iat": now, "exp": now + STATE_TTL_SECONDS},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, jti


def decode_state(state: str) -> tuple[dict[str, Any], bool]:
    """``(payload, expired)``. Raises ``ValidationFailed(invalid_state)`` for a forged / malformed state."""
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        expired = False
    except jwt.ExpiredSignatureError:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], options={"verify_exp": False})
        expired = True
    except jwt.PyJWTError as exc:
        raise ValidationFailed("This sign-in link is not valid. Start the connection again.", code="invalid_state") from exc
    if payload.get("type") != STATE_TOKEN_TYPE or not payload.get("jti") or not payload.get("sub"):
        raise ValidationFailed("This sign-in link is not valid. Start the connection again.", code="invalid_state")
    return payload, expired


def start_authorization(db: Session, user_id: uuid.UUID) -> tuple[str, str]:
    """Begin the flow. Returns ``(authorization_url, state)``; the caller sets the state cookie."""
    ensure_configured()
    connection = get_or_create_connection(db, user_id)
    state, jti = issue_state(user_id)
    verifier, challenge = pkce_pair()
    nonce = secrets.token_urlsafe(24)
    # One live row per user: a new start overwrites the previous flow's jti / verifier / nonce,
    # so only the newest consent tab can finish (an older one answers ``invalid_state``).
    connection.oauth_state = jti
    pending = {"nonce": nonce, "verifier": verifier if settings.LINKEDIN_PKCE_ENABLED else None}
    connection.encrypted_oauth_pending = encrypt_str(json.dumps(pending))
    if connection.status not in (LINKEDIN_CONNECTED, LINKEDIN_EXPIRED, LINKEDIN_REVOKED, LINKEDIN_ERROR):
        connection.status = LINKEDIN_PENDING
    db.flush()

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": str(settings.LINKEDIN_CLIENT_ID),
        "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
        "state": state,
        "scope": " ".join(requested_scopes()),
        "nonce": nonce,
    }
    if settings.LINKEDIN_PKCE_ENABLED:
        params["code_challenge"] = challenge
        params["code_challenge_method"] = "S256"
    url = f"{settings.LINKEDIN_AUTH_BASE.rstrip('/')}/authorization?{urlencode(params)}"
    audit(
        db,
        action="integration.linkedin.connect_started",
        message="Started the LinkedIn connection flow",
        user_id=user_id,
        actor=Actor.USER,
        meta={"scopes": requested_scopes(), "pkce": settings.LINKEDIN_PKCE_ENABLED},
    )
    return url, state


# --------------------------------------------------------------------------- HTTP calls


def _json(response: httpx.Response) -> dict[str, Any]:
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ExternalServiceError("LinkedIn returned an unexpectedly large response", code="linkedin_bad_response")
    try:
        data = response.json()
    except ValueError as exc:
        raise ExternalServiceError("LinkedIn returned an unreadable response", code="linkedin_bad_response") from exc
    if not isinstance(data, dict):
        raise ExternalServiceError("LinkedIn returned an unexpected response", code="linkedin_bad_response")
    return data


#: Shown when LinkedIn does not recognise the authorization code (expired, already redeemed,
#: issued to another request, or a PKCE flow LinkedIn does not support for this app).
CODE_REJECTED_MESSAGE = (
    "LinkedIn did not accept the sign-in code. Start again from Create Resume; do not reuse an old tab."
)


def token_error_details(response: httpx.Response, form: dict[str, str]) -> tuple[str, str]:
    """``(error, error_description)`` from a token-endpoint error, safe to log.

    LinkedIn's fields never contain the secret or the code, but anything equal to a value we
    sent (code, secret, verifier, refresh token) is stripped anyway, and both are length-capped.
    """
    try:
        data = response.json() if len(response.content) <= 64 * 1024 else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    error = str(data.get("error") or "")[:80]
    description = str(data.get("error_description") or data.get("message") or "")[:300]
    for key in ("code", "client_secret", "code_verifier", "refresh_token"):
        secret = form.get(key)
        if secret and len(secret) >= 4:
            error = error.replace(secret, "[redacted]")
            description = description.replace(secret, "[redacted]")
    return error, description


def _token_request(form: dict[str, str], *, failure_code: str) -> dict[str, Any]:
    url = f"{settings.LINKEDIN_AUTH_BASE.rstrip('/')}/accessToken"
    try:
        with _client() as client:
            response = client.post(url, data=form, headers={"Content-Type": "application/x-www-form-urlencoded"})
    except httpx.HTTPError as exc:
        logger.warning("LinkedIn token endpoint unreachable: %s", type(exc).__name__)
        raise ExternalServiceError("LinkedIn could not be reached. Try again in a moment.", code="linkedin_unreachable") from exc
    if response.status_code != 200:
        error, description = token_error_details(response, form)
        logger.warning(
            "LinkedIn token endpoint answered HTTP %s (grant=%s, pkce=%s): error=%r error_description=%r",
            response.status_code,
            form.get("grant_type"),
            "code_verifier" in form,
            error,
            description,
        )
        code_unknown = "authorization code" in description.lower() or error == "invalid_grant"
        if form.get("grant_type") == "authorization_code" and code_unknown:
            raise ExternalServiceError(CODE_REJECTED_MESSAGE, code="linkedin_code_rejected", details={"error": error, "error_description": description})
        raise ExternalServiceError(
            "LinkedIn rejected the sign-in. Start the connection again.",
            code=failure_code,
            details={"error": error, "error_description": description},
        )
    return _json(response)


def exchange_code(code: str, verifier: str | None) -> dict[str, Any]:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
        "client_id": str(settings.LINKEDIN_CLIENT_ID),
        "client_secret": str(settings.LINKEDIN_CLIENT_SECRET),
    }
    if settings.LINKEDIN_PKCE_ENABLED and verifier:
        form["code_verifier"] = verifier
    return _token_request(form, failure_code="token_exchange_failed")


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    return _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": str(settings.LINKEDIN_CLIENT_ID),
            "client_secret": str(settings.LINKEDIN_CLIENT_SECRET),
        },
        failure_code="token_refresh_failed",
    )


#: ``{jwks_url: (fetched_at, jwks)}`` — LinkedIn's signing keys, cached for an hour.
_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
JWKS_TTL_SECONDS = 3600
#: Asymmetric algorithms only: an ``HS*`` / ``none`` header can never pass the signature check.
ID_TOKEN_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "PS256")


def jwks_url() -> str:
    """``https://www.linkedin.com/oauth/openid/jwks`` for the default auth base."""
    return f"{expected_issuer()}/openid/jwks"


def _jwks(force: bool = False) -> dict[str, Any] | None:
    url = jwks_url()
    cached = _JWKS_CACHE.get(url)
    if cached and not force and time.time() - cached[0] < JWKS_TTL_SECONDS:
        return cached[1]
    try:
        with _client() as client:
            response = client.get(url)
        if response.status_code != 200:
            logger.warning("LinkedIn JWKS answered HTTP %s", response.status_code)
            return None
        data = _json(response)
    except (httpx.HTTPError, ExternalServiceError) as exc:
        logger.warning("LinkedIn JWKS unreachable: %s", type(exc).__name__)
        return None
    if not isinstance(data.get("keys"), list):
        return None
    _JWKS_CACHE[url] = (time.time(), data)
    return data


def _verify_signature(id_token: str) -> bool:
    """``True`` = signature verified against LinkedIn's JWKS; ``False`` = keys unavailable
    (the caller then trusts only ``/v2/userinfo``). A bad signature raises."""
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise ExternalServiceError("LinkedIn returned an unreadable ID token", code="id_token_invalid") from exc
    alg, kid = header.get("alg"), header.get("kid")
    if alg not in ID_TOKEN_ALGORITHMS:
        raise ValidationFailed("The sign-in response is not signed the way LinkedIn signs it.", code="id_token_invalid")
    for attempt in range(2):  # refetch once: LinkedIn may have rotated its keys
        jwks = _jwks(force=attempt == 1)
        if jwks is None:
            return False
        key_data = next((k for k in jwks["keys"] if isinstance(k, dict) and (kid is None or k.get("kid") == kid)), None)
        if key_data is None:
            continue
        try:
            key = jwt.PyJWK(key_data, algorithm=alg).key
            jwt.decode(id_token, key, algorithms=[alg], options={"verify_exp": False, "verify_aud": False})
            return True
        except jwt.PyJWTError as exc:
            raise ValidationFailed("The sign-in response failed LinkedIn's signature check.", code="id_token_invalid") from exc
    logger.warning("LinkedIn ID token kid=%s not in the JWKS; relying on /v2/userinfo", kid)
    return False


def verify_id_token(id_token: str | None, nonce: str | None) -> dict[str, Any]:
    """Check the ID token: signature (LinkedIn's JWKS, cached 1 h), ``aud``, ``exp``, ``iss``
    and — when the claim is present — ``nonce``.

    LinkedIn's ID token documents ``iss, aud, iat, exp, sub, name, given_name, family_name,
    picture, email, email_verified, locale`` and in practice **omits ``nonce``**. Only call
    this after the signed, user-bound, single-use, cookie-checked ``state`` matched: that is
    what binds the response to this request when the nonce is absent. The returned claims
    carry ``_signature_verified``; identity is always taken from ``/v2/userinfo``.
    """
    if not id_token:
        raise ExternalServiceError("LinkedIn did not return an ID token", code="id_token_missing")
    try:
        claims = jwt.decode(id_token, options={"verify_signature": False, "verify_exp": False, "verify_aud": False})
    except jwt.PyJWTError as exc:
        raise ExternalServiceError("LinkedIn returned an unreadable ID token", code="id_token_invalid") from exc
    claims["_signature_verified"] = _verify_signature(id_token)
    claim_nonce = claims.get("nonce")
    if claim_nonce in (None, ""):
        logger.info("linkedin id_token without nonce claim (LinkedIn omits it); the signed state already matched")
    elif not nonce or not secrets.compare_digest(str(claim_nonce), str(nonce)):
        raise ValidationFailed("The sign-in response did not match this request. Start again.", code="nonce_mismatch")
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if str(settings.LINKEDIN_CLIENT_ID) not in [str(a) for a in audiences]:
        raise ValidationFailed("The sign-in response was issued for another app.", code="id_token_invalid")
    try:
        if int(claims.get("exp") or 0) < time.time() - 60:
            raise ValidationFailed("The sign-in response has expired. Start again.", code="id_token_invalid")
    except (TypeError, ValueError) as exc:
        raise ValidationFailed("The sign-in response is malformed.", code="id_token_invalid") from exc
    issuer = claims.get("iss")
    if issuer and str(issuer).rstrip("/") != expected_issuer():
        raise ValidationFailed("The sign-in response came from an unexpected issuer.", code="id_token_invalid")
    return claims


def fetch_userinfo(access_token: str) -> dict[str, Any]:
    url = f"{settings.LINKEDIN_API_BASE.rstrip('/')}/v2/userinfo"
    try:
        with _client() as client:
            response = client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    except httpx.HTTPError as exc:
        raise ExternalServiceError("LinkedIn could not be reached. Try again in a moment.", code="linkedin_unreachable") from exc
    if response.status_code == 401:
        raise TokenRejected("userinfo answered 401")
    if response.status_code != 200:
        logger.warning("LinkedIn userinfo answered HTTP %s", response.status_code)
        raise ExternalServiceError("LinkedIn did not return your profile basics. Try again.", code="userinfo_failed")
    return _json(response)


def fetch_snapshot(access_token: str, domains: tuple[str, ...] = SNAPSHOT_DOMAINS) -> dict[str, list[dict[str, Any]]]:
    """Member Snapshot API → ``{"POSITIONS": [row, ...], ...}`` (rows use LinkedIn's export field names)."""
    base = f"{settings.LINKEDIN_API_BASE.rstrip('/')}/rest/memberSnapshotData"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }
    out: dict[str, list[dict[str, Any]]] = {}
    with _client() as client:
        for domain in domains:
            rows: list[dict[str, Any]] = []
            start = 0
            for _page in range(MAX_SNAPSHOT_PAGES):
                try:
                    response = client.get(base, params={"q": "criteria", "domain": domain, "start": start}, headers=headers)
                except httpx.HTTPError as exc:
                    raise ExternalServiceError("LinkedIn could not be reached. Try again in a moment.", code="linkedin_unreachable") from exc
                if response.status_code == 401:
                    raise TokenRejected("memberSnapshotData answered 401")
                if response.status_code == 403:
                    raise DmaUnavailable("Member Data Portability is not available for this member or app")
                if response.status_code == 404:
                    break  # nothing in this domain
                if response.status_code != 200:
                    logger.warning("LinkedIn memberSnapshotData %s answered HTTP %s", domain, response.status_code)
                    raise ExternalServiceError("LinkedIn did not return your full profile. Try again.", code="snapshot_failed")
                data = _json(response)
                page_rows = 0
                for element in data.get("elements") or []:
                    if not isinstance(element, dict):
                        continue
                    if element.get("snapshotDomain") not in (None, domain):
                        continue
                    for row in element.get("snapshotData") or []:
                        if isinstance(row, dict):
                            rows.append({str(k): ("" if v is None else str(v)) for k, v in row.items()})
                            page_rows += 1
                links = (data.get("paging") or {}).get("links") or []
                has_next = any(isinstance(link, dict) and link.get("rel") == "next" for link in links)
                if not has_next or page_rows == 0:
                    break
                start += max(page_rows, 1)
            out[domain] = rows
    return out


def revoke_token(token: str | None) -> bool:
    """Best-effort revocation at LinkedIn. Never raises."""
    if not token or not is_configured():
        return False
    url = f"{settings.LINKEDIN_AUTH_BASE.rstrip('/')}/revoke"
    try:
        with _client() as client:
            response = client.post(
                url,
                data={"token": token, "client_id": str(settings.LINKEDIN_CLIENT_ID), "client_secret": str(settings.LINKEDIN_CLIENT_SECRET)},
            )
        if response.status_code == 200:
            return True
        logger.warning("LinkedIn token revocation answered HTTP %s", response.status_code)
    except Exception as exc:  # noqa: BLE001 - disconnecting locally must always succeed
        logger.warning("LinkedIn token revocation failed: %s", type(exc).__name__)
    return False


# --------------------------------------------------------------------------- identity


def normalise_identity(info: dict[str, Any]) -> dict[str, Any]:
    """``/v2/userinfo`` → ``{sub, name, given_name, family_name, email, email_verified, picture, locale}``."""

    def s(value: Any) -> str | None:
        text = " ".join(str(value or "").split())
        return text or None

    locale = info.get("locale")
    if isinstance(locale, dict):  # LinkedIn sends {"country": "US", "language": "en"}
        language, country = s(locale.get("language")), s(locale.get("country"))
        locale_text = "_".join(p for p in (language, country) if p) or None
    else:
        locale_text = s(locale)
    given, family = s(info.get("given_name")), s(info.get("family_name"))
    picture = s(info.get("picture"))
    if picture and not picture.lower().startswith(("https://", "http://")):
        picture = None
    return {
        "sub": s(info.get("sub")),
        "name": s(info.get("name")) or s(" ".join(p for p in (given, family) if p)),
        "given_name": given,
        "family_name": family,
        "email": s(info.get("email")),
        "email_verified": info.get("email_verified") if isinstance(info.get("email_verified"), bool) else None,
        "picture": picture[:1000] if picture else None,
        "locale": locale_text[:20] if locale_text else None,
    }


def apply_identity(connection: LinkedInConnection, identity: dict[str, Any]) -> None:
    connection.subject = identity.get("sub") or connection.subject
    connection.name = (identity.get("name") or "")[:255] or None
    connection.email = (identity.get("email") or "")[:255] or None
    connection.picture_url = identity.get("picture")
    connection.locale = identity.get("locale")
    snapshot = dict(connection.profile_snapshot or {})
    snapshot["identity"] = identity
    connection.profile_snapshot = snapshot


# --------------------------------------------------------------------------- callback


def _burn(db: Session, connection: LinkedInConnection) -> None:
    connection.oauth_state = None
    connection.encrypted_oauth_pending = None
    db.flush()


def handle_callback(db: Session, code: str, state: str, *, cookie_state: str | None = None) -> LinkedInConnection:
    """Finish the flow: verify state (+cookie, +single use), exchange the code with the PKCE
    verifier, check the ID token nonce, read ``/v2/userinfo`` and store the encrypted tokens."""
    ensure_configured()
    if not code or not state:
        raise ValidationFailed("Missing the authorization code or state", code="invalid_callback")
    payload, expired = decode_state(state)
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except ValueError as exc:
        raise ValidationFailed("This sign-in link is not valid. Start the connection again.", code="invalid_state") from exc
    # Row lock: a second request for the same callback (a retried / prefetched GET) waits here
    # until the first commits, then finds the state already burnt — the code is redeemed once.
    connection = db.scalars(
        select(LinkedInConnection).where(LinkedInConnection.user_id == user_id).with_for_update()
    ).first()
    if connection is None or not connection.oauth_state or not secrets.compare_digest(str(connection.oauth_state), str(payload["jti"])):
        logger.warning("LinkedIn callback with an unknown or already used state for user %s", user_id)
        raise ValidationFailed("This sign-in link was already used. Start the connection again.", code="invalid_state")

    if not cookie_state or not secrets.compare_digest(str(cookie_state), str(state)):
        _burn(db, connection)
        audit(
            db,
            action="integration.linkedin.connect_rejected",
            message="LinkedIn callback rejected: the sign-in did not start in this browser",
            user_id=user_id,
            actor=Actor.USER,
            level=AuditLevel.WARN,
            meta={"reason": "state_cookie_mismatch"},
        )
        raise ValidationFailed("This sign-in did not start in this browser. Start the connection again.", code="state_mismatch")
    if expired:
        _burn(db, connection)
        raise ValidationFailed("This sign-in link has expired. Start the connection again.", code="state_expired")

    pending: dict[str, Any] = {}
    if connection.encrypted_oauth_pending:
        try:
            pending = json.loads(decrypt_str(connection.encrypted_oauth_pending))
        except (ValueError, TypeError):
            pending = {}
    _burn(db, connection)  # single use from here on, whatever happens next

    try:
        token = exchange_code(code, pending.get("verifier"))
    except ExternalServiceError as exc:
        details = exc.details if isinstance(exc.details, dict) else {}
        connection.last_error = f"{exc.message} ({details.get('error') or exc.code})"[:MAX_ERROR_CHARS]
        db.flush()
        audit(
            db,
            action="integration.linkedin.connect_failed",
            message=f"LinkedIn token exchange failed: {exc.code}",
            user_id=user_id,
            actor=Actor.USER,
            level=AuditLevel.WARN,
            meta={
                "code": exc.code,
                "error": details.get("error"),
                "error_description": details.get("error_description"),
                "pkce": bool(settings.LINKEDIN_PKCE_ENABLED and pending.get("verifier")),
            },
        )
        raise
    claims = verify_id_token(token.get("id_token"), pending.get("nonce"))
    access = str(token.get("access_token") or "")
    try:
        info = fetch_userinfo(access)
    except TokenRejected as exc:
        raise ExternalServiceError("LinkedIn did not accept the new token", code="userinfo_failed") from exc
    identity = normalise_identity(info)
    # Identity always comes from /v2/userinfo (fetched with the access token); a *verified* ID
    # token naming another member is a mix-up worth refusing, an unverified one is just ignored.
    if claims.get("_signature_verified") and claims.get("sub") and identity.get("sub") and str(claims["sub"]) != identity["sub"]:
        raise ValidationFailed("LinkedIn returned two different accounts. Start again.", code="id_token_invalid")

    if connection.subject and identity.get("sub") and connection.subject != identity["sub"]:
        # A different LinkedIn account than last time: nothing of the old one carries over.
        connection.profile_snapshot = {}
        connection.export_imported_at = None
        connection.last_sync_diff = {}
        connection.snapshot_source = None
        connection.encrypted_refresh_token = None
    store_tokens(connection, token)
    if not parse_scopes(token.get("scope")):
        connection.scopes = requested_scopes()
    apply_identity(connection, identity)
    connection.status = LINKEDIN_CONNECTED
    connection.connected_at = utcnow()
    connection.last_error = None
    if not connection.snapshot_source:
        connection.snapshot_source = "oidc"
    db.flush()
    audit(
        db,
        action="integration.linkedin.connected",
        message="LinkedIn connected",
        user_id=user_id,
        actor=Actor.USER,
        meta={"scopes": list(connection.scopes or []), "dma_granted": DMA_SCOPE in (connection.scopes or [])},
    )
    logger.info("LinkedIn connected for user %s", user_id)
    return connection


# --------------------------------------------------------------------------- token freshness


def access_token_for(db: Session, connection: LinkedInConnection) -> str:
    """A usable access token: refreshed when possible, else the row is marked ``expired``."""
    if connection.status not in (LINKEDIN_CONNECTED, LINKEDIN_ERROR) or not connection.encrypted_access_token:
        raise ValidationFailed("LinkedIn is not connected. Connect it again.", code="reconnect_required")
    if token_is_expired(connection):
        refresh = _decrypt(connection.encrypted_refresh_token)
        if not refresh:
            mark_expired(db, connection)
            raise ValidationFailed("Your LinkedIn sign-in expired (LinkedIn tokens last 60 days). Reconnect LinkedIn.", code="reconnect_required")
        try:
            store_tokens(connection, refresh_access_token(refresh))
        except ExternalServiceError:
            mark_expired(db, connection)
            raise ValidationFailed("LinkedIn did not renew the sign-in. Reconnect LinkedIn.", code="reconnect_required") from None
        db.flush()
    token = _decrypt(connection.encrypted_access_token)
    if not token:  # pragma: no cover - guarded above
        raise ValidationFailed("LinkedIn is not connected. Connect it again.", code="reconnect_required")
    return token


def mark_expired(db: Session, connection: LinkedInConnection) -> None:
    connection.status = LINKEDIN_EXPIRED
    connection.last_error = "The LinkedIn sign-in expired. Reconnect to keep syncing."
    connection.encrypted_access_token = None
    db.flush()


def mark_revoked(db: Session, connection: LinkedInConnection) -> None:
    connection.status = LINKEDIN_REVOKED
    connection.last_error = "LinkedIn no longer accepts this connection (it may have been removed on LinkedIn). Reconnect."
    wipe_tokens(connection)
    db.flush()


__all__ = [
    "BASE_SCOPES",
    "DMA_SCOPE",
    "DmaUnavailable",
    "SNAPSHOT_DOMAINS",
    "STATE_COOKIE_NAME",
    "STATE_TTL_SECONDS",
    "TokenRejected",
    "access_token_for",
    "apply_identity",
    "decode_state",
    "ensure_configured",
    "exchange_code",
    "fetch_snapshot",
    "fetch_userinfo",
    "get_connection",
    "get_or_create_connection",
    "handle_callback",
    "is_configured",
    "issue_state",
    "mark_expired",
    "mark_revoked",
    "normalise_identity",
    "parse_scopes",
    "pkce_pair",
    "refresh_access_token",
    "requested_scopes",
    "revoke_token",
    "set_transport",
    "start_authorization",
    "store_tokens",
    "token_is_expired",
    "verify_id_token",
    "wipe_tokens",
]
