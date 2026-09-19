"""Integration service: Gmail connection + sync, and platform accounts (contract §13).

Credentials only ever live here encrypted (``app.core.security.encrypt_str``) and are
never part of a response schema. The Gmail sync is deliberately defensive: any failure
is recorded on the integration (``status=ERROR`` + ``last_error``) so the settings page
can explain it, and :func:`sync_all_connected` never lets one broken account stop the
scheduler from syncing the rest.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError, ValidationFailed
from app.core.security import encrypt_str
from app.models.automation import ConnectedAccount
from app.models.base import utcnow
from app.models.email import EmailIntegration
from app.models.enums import Actor, EmailClassification, IntegrationStatus, JobSourceType
from app.modules.adapters.registry import get_adapter, list_adapters
from app.modules.emails import service as emails_service
from app.modules.emails.gmail_client import DEFAULT_MAX_RESULTS, DEFAULT_NEWER_THAN_DAYS, GmailClient
from app.modules.integrations import gmail_oauth
from app.modules.integrations.schemas import (
    AdapterInfoRead,
    ConnectedAccountCreate,
    ConnectedAccountRead,
    GmailStatus,
    IntegrationsOverview,
    SyncResult,
)

logger = logging.getLogger(__name__)

MAX_ERROR_CHARS = 1000


# --------------------------------------------------------------------------- gmail status


def gmail_status(db: Session, user_id: uuid.UUID) -> GmailStatus:
    """Connection state for the Gmail integration (safe to expose)."""
    integration = gmail_oauth.get_integration(db, user_id)
    configured = gmail_oauth.is_configured()
    if integration is None:
        return GmailStatus(configured=configured)
    return GmailStatus(
        status=integration.status,
        email_address=integration.email_address,
        scopes=[str(scope) for scope in (integration.scopes or [])],
        connected_at=integration.connected_at,
        last_synced_at=integration.last_synced_at,
        configured=configured,
        sync_enabled=integration.sync_enabled,
        last_error=integration.last_error,
    )


def overview(db: Session, user_id: uuid.UUID) -> IntegrationsOverview:
    """Everything the integrations screen shows: Gmail, accounts and adapters."""
    accounts = list_accounts(db, user_id)
    connected_sources = {account.source for account in accounts if account.status is IntegrationStatus.CONNECTED}
    adapters: list[AdapterInfoRead] = []
    for info in list_adapters():
        read = AdapterInfoRead.model_validate(info)
        read.connected = read.source in connected_sources
        adapters.append(read)
    return IntegrationsOverview(gmail=gmail_status(db, user_id), accounts=accounts, adapters=adapters)


# --------------------------------------------------------------------------- gmail flow


def connect_gmail(db: Session, user_id: uuid.UUID) -> tuple[str, str]:
    """Start the OAuth flow. Returns ``(consent_url, state)`` — the caller sets the cookie."""
    return gmail_oauth.start_authorization(db, user_id)


def complete_gmail_connect(db: Session, code: str, state: str, cookie_state: str | None = None) -> EmailIntegration:
    """Finish the OAuth flow (called by the unauthenticated redirect handler)."""
    return gmail_oauth.handle_callback(db, code, state, cookie_state=cookie_state)


def disconnect_gmail(db: Session, user_id: uuid.UUID) -> GmailStatus:
    """Revoke at Google (best effort) and wipe the stored tokens."""
    gmail_oauth.disconnect(db, user_id)
    return gmail_status(db, user_id)


# --------------------------------------------------------------------------- gmail sync


def _record_sync_error(db: Session, integration: EmailIntegration, exc: Exception) -> None:
    """Persist the failure on the integration so the UI can explain it.

    The session is committed before the error propagates (same pattern as
    ``auth.service``) because ``get_db`` rolls back on exceptions.
    """
    try:
        integration.status = IntegrationStatus.ERROR
        integration.last_error = str(exc)[:MAX_ERROR_CHARS]
        db.flush()
        db.commit()
    except Exception as inner:  # noqa: BLE001 - never mask the original failure
        logger.warning("Could not persist the Gmail sync error: %s", inner)
        try:
            db.rollback()
        except Exception:  # pragma: no cover - defensive
            logger.debug("Rollback after a failed sync-error write also failed")


def sync_gmail(
    db: Session,
    user_id: uuid.UUID,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    newer_than_days: int = DEFAULT_NEWER_THAN_DAYS,
    client: Any | None = None,
) -> SyncResult:
    """Fetch recent recruiting mail and run it through the email pipeline."""
    integration = gmail_oauth.get_integration(db, user_id)
    if integration is None or not integration.encrypted_credentials or integration.status is IntegrationStatus.DISCONNECTED:
        raise ValidationFailed("Gmail is not connected. Connect it from the Emails page first.", code="not_connected")

    result = SyncResult()
    try:
        gmail = client or GmailClient(gmail_oauth.load_credentials(integration))
        message_ids = gmail.list_job_related_messages(max_results=max_results, newer_than_days=newer_than_days)
        result.fetched = len(message_ids)
        for message_id in message_ids:
            if emails_service.find_by_provider_id(db, user_id, message_id) is not None:
                continue
            message = gmail.get_message(message_id)
            email = emails_service.ingest_message(db, user_id, message, integration_id=integration.id)
            result.new += 1
            if email.classification is not EmailClassification.OTHER:
                result.classified += 1
            if email.application_id is not None:
                result.linked += 1
            if email.status_applied:
                result.status_updates += 1

        if getattr(gmail, "refreshed", False):
            gmail_oauth.store_credentials(integration, gmail.credentials_json_dict())
            logger.info("Re-encrypted refreshed Gmail credentials for user %s", user_id)

        integration.last_synced_at = utcnow()
        integration.status = IntegrationStatus.CONNECTED
        integration.last_error = None
        db.flush()
    except Exception as exc:
        logger.warning("Gmail sync failed for user %s: %s", user_id, exc)
        _record_sync_error(db, integration, exc)
        raise

    audit(
        db,
        action="integration.synced",
        message=f"Gmail sync: {result.new} new of {result.fetched} message(s), {result.linked} linked",
        user_id=user_id,
        actor=Actor.SYSTEM,
        meta=result.model_dump(),
    )
    logger.info("Gmail sync for user %s: %s", user_id, result.model_dump())
    return result


def sync_all_connected(db: Session) -> dict[str, SyncResult]:
    """Sync every connected mailbox — used by the scheduler; never raises.

    Mailboxes left in ``ERROR`` by an earlier run are retried too (a failure is usually
    transient); a successful sync clears the error.
    """
    integrations = list(
        db.scalars(
            select(EmailIntegration).where(
                EmailIntegration.status.in_((IntegrationStatus.CONNECTED, IntegrationStatus.ERROR)),
                EmailIntegration.sync_enabled.is_(True),
                EmailIntegration.encrypted_credentials.is_not(None),
            )
        )
    )
    results: dict[str, SyncResult] = {}
    for integration in integrations:
        user_id = integration.user_id
        try:
            results[str(user_id)] = sync_gmail(db, user_id)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - one broken mailbox must not stop the others
            logger.warning("Scheduled Gmail sync failed for user %s: %s", user_id, exc)
            results[str(user_id)] = SyncResult(error=str(exc)[:MAX_ERROR_CHARS])
            try:
                db.rollback()
            except Exception:  # pragma: no cover - defensive
                logger.debug("Rollback after a failed scheduled sync also failed")
    logger.info("Scheduled Gmail sync finished for %d integration(s)", len(integrations))
    return results


# --------------------------------------------------------------------------- platform accounts


def list_accounts(db: Session, user_id: uuid.UUID) -> list[ConnectedAccountRead]:
    accounts = db.scalars(
        select(ConnectedAccount).where(ConnectedAccount.user_id == user_id).order_by(ConnectedAccount.created_at.asc())
    )
    return [ConnectedAccountRead.from_model(account) for account in accounts]


def get_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> ConnectedAccount:
    account = db.scalars(
        select(ConnectedAccount).where(ConnectedAccount.id == account_id, ConnectedAccount.user_id == user_id)
    ).first()
    if account is None:
        raise NotFoundError("Connected account not found")
    return account


def connect_account(db: Session, user_id: uuid.UUID, payload: ConnectedAccountCreate) -> ConnectedAccountRead:
    """Store (or update) a platform account. Credentials are encrypted at rest."""
    adapter = get_adapter(payload.source)  # raises NotFoundError for unregistered sources
    source = JobSourceType(payload.source)
    account = db.scalars(
        select(ConnectedAccount).where(ConnectedAccount.user_id == user_id, ConnectedAccount.source == source)
    ).first()
    if account is None:
        account = ConnectedAccount(user_id=user_id, source=source)
        db.add(account)

    account.account_identifier = payload.account_identifier or account.account_identifier
    account.is_mock = bool(adapter.is_mock)
    account.status = IntegrationStatus.CONNECTED
    account.connected_at = utcnow()
    account.last_error = None
    if payload.credentials is not None:
        account.encrypted_credentials = encrypt_str(json.dumps(payload.credentials.model_dump()))
        if adapter.is_mock:
            logger.info("Stored credentials for mock source %s; the mock adapter ignores them", source.value)
    db.flush()

    audit(
        db,
        action="integration.account_connected",
        message=f"Connected the {adapter.display_name} account",
        user_id=user_id,
        actor=Actor.USER,
        meta={
            "source": source.value,
            "is_mock": account.is_mock,
            "has_credentials": bool(account.encrypted_credentials),
            "account_identifier": account.account_identifier,
        },
    )
    logger.info("User %s connected the %s account", user_id, source.value)
    return ConnectedAccountRead.from_model(account)


def remove_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> None:
    account = get_account(db, user_id, account_id)
    source = account.source
    db.delete(account)
    db.flush()
    audit(
        db,
        action="integration.account_removed",
        message=f"Removed the {source.value} account",
        user_id=user_id,
        actor=Actor.USER,
        meta={"source": source.value, "account_id": str(account_id)},
    )
    logger.info("User %s removed the %s account", user_id, source.value)


def frontend_redirect(path: str) -> str:
    """Absolute URL back into the SPA (used by the OAuth callback)."""
    base = (settings.FRONTEND_URL or "").rstrip("/")
    return f"{base}{path}"


def error_code_of(exc: Exception) -> str:
    return exc.code if isinstance(exc, AppError) else "connection_failed"


__all__ = [
    "complete_gmail_connect",
    "connect_account",
    "connect_gmail",
    "disconnect_gmail",
    "error_code_of",
    "frontend_redirect",
    "get_account",
    "gmail_status",
    "list_accounts",
    "overview",
    "remove_account",
    "sync_all_connected",
    "sync_gmail",
]
