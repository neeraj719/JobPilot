"""API schemas of AI Model Settings (``/api/v1/ai/...``).

No schema here has a field that could carry a stored secret back to the browser: a saved
key is only ever represented by ``masked_key`` (``••••1234``) and ``has_key``.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProviderId = Literal["mock", "ollama", "openai", "gemini", "anthropic", "openai_compatible"]
WorkflowId = Literal["generation", "analysis", "rewriting", "jd_analysis", "review", "general"]

_KEY_RE = re.compile(r"^[\x21-\x7e]+$")  # printable ASCII, no spaces


class WorkflowTarget(BaseModel):
    provider: ProviderId
    model: str = Field(min_length=1, max_length=200)

    @field_validator("model")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("model cannot be empty")
        return value


class CredentialRead(BaseModel):
    provider: str
    has_key: bool
    #: ``••••1234`` — the only representation of a stored key the API ever returns.
    masked_key: str | None = None
    base_url: str | None = None
    credential_version: int
    status: str
    last_tested_at: datetime | None = None
    last_latency_ms: int | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    rotated_at: datetime | None = None
    updated_at: datetime | None = None


class CredentialWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Required for OpenAI, Gemini and Anthropic; optional for an OpenAI-compatible server;
    #: not accepted for Ollama.
    api_key: str | None = Field(default=None, max_length=512)
    base_url: str | None = Field(default=None, max_length=500)

    @field_validator("api_key")
    @classmethod
    def _clean_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) < 8:
            raise ValueError("That API key is too short.")
        if not _KEY_RE.match(value):
            raise ValueError("An API key cannot contain spaces or non-ASCII characters.")
        return value


class ProviderRead(BaseModel):
    id: str
    name: str
    kind: str
    hosted: bool
    requires_key: bool
    supports_base_url: bool
    default_model: str | None = None
    docs_url: str | None = None
    key_url: str | None = None
    prices_as_of: str | None = None
    privacy_note: str
    billing_note: str | None = None
    supports_live_models: bool
    description: str
    capabilities: dict[str, Any] = Field(default_factory=dict)
    #: Allowed on this server (``AI_ALLOW_HOSTED_PROVIDERS``).
    allowed: bool = True
    is_server_default: bool = False
    #: The server has its own key for this provider (only used when it is the server default).
    server_key_configured: bool = False
    credential: CredentialRead | None = None


class WorkflowInfo(BaseModel):
    id: str
    label: str


class ProvidersResponse(BaseModel):
    providers: list[ProviderRead]
    workflows: list[WorkflowInfo]
    server_default: WorkflowTarget | dict[str, Any]
    billing_note: str
    hosted_allowed: bool


class EffectiveTarget(BaseModel):
    provider: str
    model: str
    source: str
    usable: bool = True
    problem: str | None = None


class SettingsRead(BaseModel):
    default_provider: str | None = None
    default_model: str | None = None
    workflow_models: dict[str, WorkflowTarget] = Field(default_factory=dict)
    fallback_enabled: bool = False
    fallback_provider: str | None = None
    fallback_model: str | None = None
    daily_call_limit: int | None = None
    monthly_budget_usd: float | None = None
    data_residency_ack: bool = False
    #: What each workflow resolves to right now (and whether it can be used).
    effective: dict[str, EffectiveTarget] = Field(default_factory=dict)
    fallback: EffectiveTarget | None = None
    server_default: dict[str, Any]
    hosted_allowed: bool
    credentials: list[CredentialRead] = Field(default_factory=list)
    #: One-line description of the setup, e.g. "Local Ollama · qwen2.5:3b-instruct — private, free".
    summary: str
    #: Provider status for the dashboard (plan §4.6).
    status: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None


class SettingsUpdate(BaseModel):
    """Full replacement of the user's routing (``PUT``). ``None`` = use the server default."""

    model_config = ConfigDict(extra="forbid")

    default_provider: ProviderId | None = None
    default_model: str | None = Field(default=None, max_length=200)
    workflow_models: dict[WorkflowId, WorkflowTarget] = Field(default_factory=dict)
    fallback_enabled: bool = False
    fallback_provider: ProviderId | None = None
    fallback_model: str | None = Field(default=None, max_length=200)
    daily_call_limit: int | None = Field(default=None, ge=1, le=100_000)
    monthly_budget_usd: Decimal | None = Field(default=None, ge=0, le=100_000, max_digits=10, decimal_places=2)
    data_residency_ack: bool = False

    @field_validator("default_model", "fallback_model")
    @classmethod
    def _strip_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ModelRow(BaseModel):
    id: str
    display_name: str
    in_registry: bool
    pricing_known: bool
    input_per_m_usd: float | None = None
    output_per_m_usd: float | None = None
    context_window: int | None = None
    json_mode: bool = True
    vision: bool = False
    recommended_for: list[str] = Field(default_factory=list)
    group: str
    available: bool | None = None
    notes: str | None = None


class ModelsResponse(BaseModel):
    provider: str
    models: list[ModelRow]
    #: The list came from the provider just now (or from a recent cached fetch).
    live: bool
    fetched_at: datetime | None = None
    error_code: str | None = None
    error: str | None = None
    prices_as_of: str | None = None


class ConnectionTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, max_length=200)


class ConnectionTestResult(BaseModel):
    provider: str
    ok: bool
    model: str | None = None
    model_available: bool | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    error: str | None = None
    tested_at: datetime
    credential: CredentialRead | None = None


class UsageTotals(BaseModel):
    calls: int = 0
    ok: int = 0
    errors: int = 0
    fallbacks: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    #: Calls whose model has no registry price (their cost is not in the total).
    cost_unknown_calls: int = 0
    #: Calls whose tokens were estimated from text length (the SDK reported none).
    tokens_estimated_calls: int = 0
    avg_duration_ms: int | None = None


class UsageGroup(UsageTotals):
    key: str
    label: str | None = None
    provider: str | None = None
    model: str | None = None


class UsageDay(BaseModel):
    date: str
    calls: int = 0
    errors: int = 0
    estimated_cost_usd: float = 0.0
    tokens: int = 0


class UsageResponse(BaseModel):
    range: str
    since: datetime
    totals: UsageTotals
    by_workflow: list[UsageGroup]
    by_provider: list[UsageGroup]
    daily: list[UsageDay]
    estimated: bool = True
    prices_as_of: dict[str, str] = Field(default_factory=dict)
    limits: dict[str, Any] = Field(default_factory=dict)
    note: str


__all__ = [
    "CredentialRead",
    "CredentialWrite",
    "EffectiveTarget",
    "ModelRow",
    "ModelsResponse",
    "ProviderRead",
    "ProvidersResponse",
    "SettingsRead",
    "SettingsUpdate",
    "ConnectionTestRequest",
    "ConnectionTestResult",
    "UsageResponse",
    "WorkflowTarget",
]
