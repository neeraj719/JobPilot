"""Integration schemas (contract §13).

Nothing here ever exposes a credential: ``ConnectedAccountRead`` carries a
``has_credentials`` flag instead of the encrypted blob, and the Gmail status shows
only the account address, granted scopes and timestamps.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import IntegrationStatus, JobSourceType


class GmailStatus(BaseModel):
    """State of the (read-only) Gmail connection for one user."""

    model_config = ConfigDict(from_attributes=True)

    status: IntegrationStatus = IntegrationStatus.DISCONNECTED
    email_address: str | None = None
    scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    configured: bool = False
    sync_enabled: bool = True
    last_error: str | None = None


class AccountCredentials(BaseModel):
    """Platform credentials. Encrypted at rest, never returned by the API."""

    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class ConnectedAccountCreate(BaseModel):
    source: JobSourceType
    account_identifier: str | None = Field(default=None, max_length=255)
    credentials: AccountCredentials | None = None


class ConnectedAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: JobSourceType
    account_identifier: str | None = None
    status: IntegrationStatus = IntegrationStatus.CONNECTED
    is_mock: bool = True
    has_credentials: bool = False
    connected_at: datetime | None = None
    last_used_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime | None = None

    @classmethod
    def from_model(cls, account: Any) -> ConnectedAccountRead:
        read = cls.model_validate(account)
        read.has_credentials = bool(getattr(account, "encrypted_credentials", None))
        return read


class AdapterInfoRead(BaseModel):
    """Public metadata for one job-source adapter (``adapters.registry.list_adapters``)."""

    model_config = ConfigDict(from_attributes=True)

    source: JobSourceType
    display_name: str
    is_mock: bool = True
    supports_auto_apply: bool = False
    requires_account: bool = False
    terms_note: str = ""
    rate_limit_per_minute: int = 60
    uses_browser: bool = False
    connected: bool = False


class IntegrationsOverview(BaseModel):
    """``GET /integrations`` — everything the settings page needs in one call."""

    gmail: GmailStatus
    accounts: list[ConnectedAccountRead] = Field(default_factory=list)
    adapters: list[AdapterInfoRead] = Field(default_factory=list)


class AuthorizationUrlResponse(BaseModel):
    """``POST /integrations/gmail/connect``."""

    authorization_url: str


class SyncResult(BaseModel):
    """Outcome of one Gmail sync."""

    fetched: int = 0
    new: int = 0
    classified: int = 0
    linked: int = 0
    status_updates: int = 0
    error: str | None = None


__all__ = [
    "AccountCredentials",
    "AdapterInfoRead",
    "AuthorizationUrlResponse",
    "ConnectedAccountCreate",
    "ConnectedAccountRead",
    "GmailStatus",
    "IntegrationsOverview",
    "SyncResult",
]
