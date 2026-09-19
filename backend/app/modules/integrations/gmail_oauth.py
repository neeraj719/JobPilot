"""Gmail OAuth 2.0 (authorization-code flow) — least privilege, read-only.

Only ``settings.GMAIL_SCOPES`` is ever requested (``gmail.readonly`` + the identity
scopes needed to show which mailbox is connected). The refresh/access token bundle is
Fernet-encrypted before it touches the database and is never returned by the API.

CSRF protection: a single-use ``state`` (``secrets.token_urlsafe(32)``) is stored on
``EmailIntegration.oauth_state`` when the flow starts and must come back unchanged;
it is cleared as soon as it is spent.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.exceptions import ExternalServiceError, ValidationFailed
from app.core.security import decrypt_str, encrypt_str
from app.models.base import utcnow
from app.models.email import EmailIntegration
from app.models.enums import Actor, EmailProvider, IntegrationStatus

logger = logging.getLogger(__name__)

AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REVOKE_URI = "https://oauth2.googleapis.com/revoke"
USERINFO_URI = "https://www.googleapis.com/oauth2/v3/userinfo"
STATE_BYTES = 32
HTTP_TIMEOUT_SECONDS = 15.0

#: Write-capable Gmail scopes we must never hold.
FORBIDDEN_SCOPE_FRAGMENTS = ("gmail.send", "gmail.modify", "gmail.compose", "gmail.insert", "gmail.settings", "mail.google.com")


# --------------------------------------------------------------------------- configuration


def is_configured() -> bool:
    """True when a Google OAuth client is configured for this deployment."""
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def ensure_configured() -> None:
    if not is_configured():
        raise ValidationFailed(
            "Gmail OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to enable it.",
            code="not_configured",
        )


def client_config() -> dict[str, Any]:
    return {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
        }
    }


def build_flow(state: str | None = None) -> Any:
    """A ``google_auth_oauthlib`` flow bound to our client config and redirect URI."""
    ensure_configured()
    try:
        from google_auth_oauthlib.flow import Flow  # noqa: PLC0415 - optional heavy import

        return Flow.from_client_config(
            client_config(),
            scopes=list(settings.GMAIL_SCOPES),
            state=state,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
        )
    except ValidationFailed:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not build the Gmail OAuth flow: %s", exc)
        raise ExternalServiceError("Could not start the Google sign-in flow", code="oauth_unavailable") from exc


# --------------------------------------------------------------------------- integration row


def get_integration(db: Session, user_id: uuid.UUID) -> EmailIntegration | None:
    return db.scalars(select(EmailIntegration).where(EmailIntegration.user_id == user_id)).first()


def get_or_create_integration(db: Session, user_id: uuid.UUID) -> EmailIntegration:
    integration = get_integration(db, user_id)
    if integration is None:
        integration = EmailIntegration(
            user_id=user_id,
            provider=EmailProvider.GMAIL,
            status=IntegrationStatus.DISCONNECTED,
            scopes=[],
        )
        db.add(integration)
        db.flush()
        logger.info("Created a Gmail integration row for user %s", user_id)
    return integration


def load_credentials(integration: EmailIntegration | None) -> dict[str, Any]:
    """Decrypt the stored OAuth bundle (``{}`` when there is none)."""
    if integration is None or not integration.encrypted_credentials:
        return {}
    try:
        data = json.loads(decrypt_str(integration.encrypted_credentials))
    except (ValueError, TypeError) as exc:
        logger.error("Could not decrypt the stored Gmail credentials for user %s: %s", integration.user_id, exc)
        raise ExternalServiceError("Stored Gmail credentials are unreadable; reconnect the account", code="credentials_unreadable") from exc
    return data if isinstance(data, dict) else {}


def store_credentials(integration: EmailIntegration, credentials: dict[str, Any]) -> None:
    """Encrypt and persist the OAuth bundle (never stored in the clear)."""
    integration.encrypted_credentials = encrypt_str(json.dumps(credentials))


# --------------------------------------------------------------------------- flow


def credentials_to_dict(credentials: Any) -> dict[str, Any]:
    expiry: datetime | None = getattr(credentials, "expiry", None)
    return {
        "token": getattr(credentials, "token", None),
        "refresh_token": getattr(credentials, "refresh_token", None),
        "token_uri": getattr(credentials, "token_uri", None) or TOKEN_URI,
        "client_id": getattr(credentials, "client_id", None),
        "client_secret": getattr(credentials, "client_secret", None),
        "scopes": list(getattr(credentials, "scopes", None) or []),
        "expiry": expiry.isoformat() if expiry else None,
    }


def _assert_scopes_are_read_only(scopes: list[str]) -> None:
    for scope in scopes:
        lowered = scope.lower()
        if any(fragment in lowered for fragment in FORBIDDEN_SCOPE_FRAGMENTS):
            raise ValidationFailed(
                "Google granted a write-capable Gmail scope; JobPilot only uses read-only access.",
                code="invalid_scope",
            )


def start_authorization(db: Session, user_id: uuid.UUID) -> str:
    """Begin the flow: store a fresh CSRF state and return Google's consent URL."""
    ensure_configured()
    integration = get_or_create_integration(db, user_id)
    state = secrets.token_urlsafe(STATE_BYTES)
    flow = build_flow(state=state)
    try:
        authorization_url, _ = flow.authorization_url(
            access_type="offline",  # we need a refresh token for the background sync
            include_granted_scopes="false",  # never inherit scopes granted to other apps
            prompt="consent",
            state=state,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not build the Gmail authorization URL: %s", exc)
        raise ExternalServiceError("Could not start the Google sign-in flow", code="oauth_unavailable") from exc

    integration.oauth_state = state
    if integration.status is not IntegrationStatus.CONNECTED:
        integration.status = IntegrationStatus.DISCONNECTED
    db.flush()
    audit(
        db,
        action="integration.connect_started",
        message="Started the Gmail (read-only) connection flow",
        user_id=user_id,
        actor=Actor.USER,
        meta={"provider": EmailProvider.GMAIL.value, "scopes": list(settings.GMAIL_SCOPES)},
    )
    return authorization_url


def exchange_code(code: str, state: str | None = None) -> dict[str, Any]:
    """Swap the authorization code for a token bundle."""
    flow = build_flow(state=state)
    # Google may echo the granted scopes in a different order/shape than requested;
    # oauthlib treats that as an error unless token-scope checking is relaxed.
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    try:
        flow.fetch_token(code=code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gmail token exchange failed: %s", exc)
        raise ExternalServiceError("Google rejected the authorization code", code="token_exchange_failed") from exc
    credentials = credentials_to_dict(flow.credentials)
    _assert_scopes_are_read_only(credentials.get("scopes") or [])
    return credentials


def fetch_account_email(credentials: dict[str, Any]) -> str | None:
    """The connected mailbox address — Gmail profile first, userinfo as a fallback."""
    try:
        from app.modules.emails.gmail_client import GmailClient  # noqa: PLC0415 - lazy

        address = GmailClient(credentials).get_profile_email()
        if address:
            return address
    except Exception as exc:  # noqa: BLE001 - identity is nice to have, not essential
        logger.warning("Gmail profile lookup failed (%s); trying the userinfo endpoint", exc)

    token = credentials.get("token")
    if not token:
        return None
    try:
        import httpx  # noqa: PLC0415

        response = httpx.get(USERINFO_URI, headers={"Authorization": f"Bearer {token}"}, timeout=HTTP_TIMEOUT_SECONDS)
        if response.status_code == 200:
            return response.json().get("email")
        logger.warning("Userinfo lookup returned HTTP %s", response.status_code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Userinfo lookup failed: %s", exc)
    return None


def handle_callback(db: Session, code: str, state: str) -> EmailIntegration:
    """Finish the flow: verify state, exchange the code and store the encrypted bundle."""
    ensure_configured()
    if not code or not state:
        raise ValidationFailed("Missing the authorization code or state", code="invalid_callback")
    integration = db.scalars(select(EmailIntegration).where(EmailIntegration.oauth_state == state)).first()
    if integration is None:
        logger.warning("Gmail callback with an unknown OAuth state")
        raise ValidationFailed("This sign-in link has expired. Start the connection again.", code="invalid_state")

    credentials = exchange_code(code, state=state)
    email_address = fetch_account_email(credentials)

    store_credentials(integration, credentials)
    integration.email_address = email_address
    integration.scopes = credentials.get("scopes") or list(settings.GMAIL_SCOPES)
    integration.status = IntegrationStatus.CONNECTED
    integration.connected_at = utcnow()
    integration.last_error = None
    integration.sync_enabled = True
    integration.oauth_state = None  # single use
    db.flush()

    audit(
        db,
        action="integration.connected",
        message=f"Gmail connected ({email_address or 'unknown address'})",
        user_id=integration.user_id,
        actor=Actor.USER,
        meta={"provider": EmailProvider.GMAIL.value, "scopes": integration.scopes, "email_address": email_address},
    )
    logger.info("Gmail connected for user %s", integration.user_id)
    return integration


def revoke_token(token: str | None) -> bool:
    """Best-effort token revocation at Google. Never raises."""
    if not token:
        return False
    try:
        import httpx  # noqa: PLC0415

        response = httpx.post(REVOKE_URI, data={"token": token}, timeout=HTTP_TIMEOUT_SECONDS)
        if response.status_code == 200:
            return True
        logger.warning("Google token revocation returned HTTP %s", response.status_code)
    except Exception as exc:  # noqa: BLE001 - disconnecting locally must always succeed
        logger.warning("Google token revocation failed: %s", exc)
    return False


def disconnect(db: Session, user_id: uuid.UUID) -> EmailIntegration | None:
    """Revoke at Google (best effort) and wipe every stored credential locally."""
    integration = get_integration(db, user_id)
    if integration is None:
        return None
    revoked = False
    try:
        credentials = load_credentials(integration)
        revoked = revoke_token(credentials.get("refresh_token") or credentials.get("token"))
    except ExternalServiceError:
        logger.warning("Stored Gmail credentials for user %s could not be read; wiping them anyway", user_id)

    integration.encrypted_credentials = None
    integration.scopes = []
    integration.status = IntegrationStatus.DISCONNECTED
    integration.oauth_state = None
    integration.connected_at = None
    integration.last_history_id = None
    integration.last_error = None
    db.flush()

    audit(
        db,
        action="integration.disconnected",
        message="Gmail disconnected and stored tokens wiped",
        user_id=user_id,
        actor=Actor.USER,
        meta={"provider": EmailProvider.GMAIL.value, "revoked_at_google": revoked},
    )
    logger.info("Gmail disconnected for user %s (revoked=%s)", user_id, revoked)
    return integration


__all__ = [
    "build_flow",
    "credentials_to_dict",
    "disconnect",
    "ensure_configured",
    "exchange_code",
    "fetch_account_email",
    "get_integration",
    "get_or_create_integration",
    "handle_callback",
    "is_configured",
    "load_credentials",
    "revoke_token",
    "start_authorization",
    "store_credentials",
]
