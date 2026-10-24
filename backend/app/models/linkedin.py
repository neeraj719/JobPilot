"""LinkedIn connection (official OAuth only).

One live row per user (partial unique on ``user_id``). The access / refresh tokens and the
in-flight PKCE verifier are Fernet-encrypted (``app.core.security.encrypt_str``) and never
leave the backend. ``profile_snapshot`` holds what LinkedIn returned, already normalised:

``{"identity": {...}, "dma": <ParsedResume dict> | null, "export": <ParsedResume dict> | null,
"fetched_at": iso, "dma_error": str | null}``

``dma`` is filled only when the member granted ``r_dma_portability_3rd_party`` (Member Data
Portability, EU/EEA); ``export`` only from a LinkedIn "Get a copy of your data" ZIP the user
uploaded while connected. Raw export files are never stored.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SCHEMA_MASTER, Base, StandardColumnsMixin, UTCDateTime, soft_delete_where

#: ``LinkedInConnection.status`` values.
LINKEDIN_PENDING = "pending"  # a connect flow was started and has not completed yet
LINKEDIN_CONNECTED = "connected"
LINKEDIN_EXPIRED = "expired"  # the (60-day) access token lapsed and there is no refresh token
LINKEDIN_REVOKED = "revoked"  # LinkedIn refused the token (the member removed the app)
LINKEDIN_ERROR = "error"
LINKEDIN_STATUSES = (LINKEDIN_PENDING, LINKEDIN_CONNECTED, LINKEDIN_EXPIRED, LINKEDIN_REVOKED, LINKEDIN_ERROR)

#: ``LinkedInConnection.snapshot_source`` values: where the richest data came from.
SNAPSHOT_OIDC = "oidc"
SNAPSHOT_DMA = "dma"
SNAPSHOT_EXPORT = "export"


class LinkedInConnection(StandardColumnsMixin, Base):
    __tablename__ = "linkedin_connections"
    __table_args__ = (
        Index("uq_linkedin_connections_user_active", "user_id", unique=True, **soft_delete_where()),
        {"schema": SCHEMA_MASTER},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))  # LinkedIn ``sub``
    name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    picture_url: Mapped[str | None] = mapped_column(String(1000))
    locale: Mapped[str | None] = mapped_column(String(20))
    scopes: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(20), default=LINKEDIN_PENDING, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    auto_sync: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    snapshot_source: Mapped[str | None] = mapped_column(String(10))
    export_imported_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_sync_diff: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    #: ``jti`` of the signed OAuth ``state`` in flight (single use; cleared when spent).
    oauth_state: Mapped[str | None] = mapped_column(String(64))
    #: Encrypted ``{"verifier": PKCE code_verifier, "nonce": OIDC nonce}`` for that flow.
    encrypted_oauth_pending: Mapped[str | None] = mapped_column(Text)


__all__ = [
    "LINKEDIN_CONNECTED",
    "LINKEDIN_ERROR",
    "LINKEDIN_EXPIRED",
    "LINKEDIN_PENDING",
    "LINKEDIN_REVOKED",
    "LINKEDIN_STATUSES",
    "LinkedInConnection",
    "SNAPSHOT_DMA",
    "SNAPSHOT_EXPORT",
    "SNAPSHOT_OIDC",
]
