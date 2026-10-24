"""Per-user AI provider configuration, encrypted credentials and usage events.

Owned by the ``ai-providers`` work stream (see ``notes/resume-studio-plan.md``). Settings and
credentials live in ``master``; usage events (append-only) live in ``transaction``. Secrets are
stored with ``app.core.security.encrypt_str`` and never leave the server unmasked.

* :class:`AiProviderSettings` — one live row per user: the default provider/model, a
  per-workflow override map, the optional fallback (off by default, never silent), usage
  limits and the user's acknowledgement that hosted providers receive resume text.
* :class:`AiProviderCredential` — one live row per (user, provider): the Fernet-encrypted
  API key (``encrypted_api_key``), a four-character hint for the UI, an optional base URL
  (self-hosted / OpenAI-compatible / a non-default Ollama), the last connection test and a
  ``credential_version`` that every save bumps (the runtime's client cache keys on it).
  Removing a key tombstones the row **and** wipes the ciphertext.
* :class:`AiUsageEvent` — one row per real model call: tokens (from the SDK, else an
  estimate flagged ``tokens_estimated``), the estimated cost from the model registry,
  duration and outcome. Never holds prompt or response text.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SCHEMA_MASTER, SCHEMA_TRANSACTION, Base, StandardColumnsMixin, UTCDateTime, soft_delete_where


class AiCredentialStatus(StrEnum):
    """Outcome of the last connection test of a stored credential."""

    UNTESTED = "UNTESTED"
    OK = "OK"
    ERROR = "ERROR"


class AiUsageStatus(StrEnum):
    """``FALLBACK``: the call was answered by the user's configured fallback after the
    primary failed (the primary's failure is its own ``ERROR`` event)."""

    OK = "OK"
    ERROR = "ERROR"
    FALLBACK = "FALLBACK"


MODEL_PROMPT_MODES = ("ask", "default")


class AiProviderSettings(StandardColumnsMixin, Base):
    __tablename__ = "ai_provider_settings"
    __table_args__ = (
        Index("uq_ai_provider_settings_user_active", "user_id", unique=True, **soft_delete_where()),
        {"schema": SCHEMA_MASTER},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    #: ``None`` = the server default (``LLM_PROVIDER``).
    default_provider: Mapped[str | None] = mapped_column(String(30))
    default_model: Mapped[str | None] = mapped_column(String(200))
    #: ``{workflow: {"provider": str, "model": str}}`` — see ``app.modules.ai.routing.AiWorkflow``.
    workflow_models: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    fallback_provider: Mapped[str | None] = mapped_column(String(30))
    fallback_model: Mapped[str | None] = mapped_column(String(200))
    fallback_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_call_limit: Mapped[int | None] = mapped_column(Integer)
    monthly_budget_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    #: The user acknowledged that hosted providers receive their resume / job text.
    data_residency_ack: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: ``ask`` = when two or more models are usable, every AI action asks which one should
    #: process the run; ``default`` = always use the routing above without asking
    #: (``ai.choice``, migration ``e6f8a0b2c4d7``). The UI decides; the API always honours a
    #: valid per-run choice.
    model_prompt_mode: Mapped[str] = mapped_column(String(10), default="ask", nullable=False)


class AiProviderCredential(StandardColumnsMixin, Base):
    __tablename__ = "ai_provider_credentials"
    __table_args__ = (
        Index("uq_ai_provider_credentials_user_provider_active", "user_id", "provider", unique=True, **soft_delete_where()),
        {"schema": SCHEMA_MASTER},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Fernet ciphertext (``app.core.security.encrypt_str``). ``None`` for a keyless local server.
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    #: Last four characters of the key, for the masked display (``••••1234``).
    key_hint: Mapped[str | None] = mapped_column(String(8))
    base_url: Mapped[str | None] = mapped_column(String(500))
    credential_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[AiCredentialStatus] = mapped_column(
        Enum(AiCredentialStatus, native_enum=False, length=20), default=AiCredentialStatus.UNTESTED, nullable=False
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_latency_ms: Mapped[int | None] = mapped_column(Integer)
    #: Sanitised, user-facing message of the last failed test (never a raw provider body).
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_code: Mapped[str | None] = mapped_column(String(40))
    rotated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AiUsageEvent(StandardColumnsMixin, Base):
    __tablename__ = "ai_usage_events"
    __table_args__ = (
        Index("ix_ai_usage_events_user_created_at", "user_id", "created_at"),
        {"schema": SCHEMA_TRANSACTION},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    task: Mapped[str] = mapped_column(String(80), nullable=False)
    workflow: Mapped[str] = mapped_column(String(30), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_estimated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: ``None`` when the model is not in the registry (pricing unknown); 0 for local models.
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[AiUsageStatus] = mapped_column(Enum(AiUsageStatus, native_enum=False, length=20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    #: How the model was chosen: ``per_run`` (picked for this run), ``task_override``,
    #: ``user_default``, ``server_default`` or ``fallback``. ``None`` on rows written before
    #: migration ``e6f8a0b2c4d7``.
    source: Mapped[str | None] = mapped_column(String(20))


__all__ = [
    "AiCredentialStatus",
    "AiProviderCredential",
    "AiProviderSettings",
    "AiUsageEvent",
    "AiUsageStatus",
    "MODEL_PROMPT_MODES",
]
