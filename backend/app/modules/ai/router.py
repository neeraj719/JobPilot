"""AI router — mounted at ``/api/v1/ai`` by ``app.main`` (CONTRACTS.md §6).

AI Model Settings endpoints (bring-your-own provider):

* ``GET  /ai/providers``                     catalog (privacy/billing notes, key pages) + the user's credential status
* ``GET  /ai/settings`` / ``PUT /ai/settings`` default model, per-workflow models, fallback, limits
* ``PUT  /ai/credentials/{provider}``         save / rotate a key or base URL (recent sign-in required)
* ``DELETE /ai/credentials/{provider}``       remove it (recent sign-in required; ciphertext wiped)
* ``POST /ai/credentials/{provider}/test``    one cheap call, result stored (rate limited)
* ``GET  /ai/providers/{provider}/models``    live list merged with the registry (rate limited when it hits the network)
* ``GET  /ai/usage?range=7d|30d|month``       calls, tokens, estimated cost
* ``GET  /ai/status``                         server provider + the user's effective setup

No response ever contains a stored key: credentials are represented by ``masked_key``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_recent_auth
from app.core.exceptions import NotFoundError, RateLimitedError
from app.core.rate_limit import rate_limiter
from app.models.user import User
from app.modules.ai import registry, settings_service
from app.modules.ai.factory import provider_status
from app.modules.ai.schemas import AIStatus
from app.modules.ai.settings_schemas import (
    ConnectionTestRequest,
    ConnectionTestResult,
    CredentialRead,
    CredentialWrite,
    ModelsResponse,
    ProvidersResponse,
    SettingsRead,
    SettingsUpdate,
    UsageResponse,
)
from app.modules.ai.usage import usage_summary

logger = logging.getLogger(__name__)

router = APIRouter()


def _provider_or_404(provider: str, *, allow_mock: bool = True) -> str:
    if not registry.known_provider(provider) or (provider == "mock" and not allow_mock):
        raise NotFoundError("Unknown AI provider")
    return provider


def _limit_outbound(user: User, bucket: str) -> None:
    """Per-user limit on calls that reach a provider (tests, live model lists)."""
    allowed, _ = rate_limiter.check(f"ai:{bucket}:{user.id}", max(1, settings.AI_TEST_RATE_LIMIT_PER_MINUTE), 60)
    if not allowed:
        raise RateLimitedError("Too many provider checks. Wait a minute and try again.")


@router.get("/status", response_model=AIStatus, response_model_exclude_none=True, summary="Which LLM provider is active")
def get_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AIStatus:
    """The server's default provider/model (``configured`` is always true for the mock,
    which needs no key) plus ``effective``: what this user's calls resolve to."""
    status = provider_status()
    try:
        status["effective"] = settings_service.read_settings(db, user)["status"]
    except Exception as exc:  # noqa: BLE001 - the server status must always answer
        logger.warning("Could not read the user's AI settings for /ai/status (%s)", type(exc).__name__)
    return AIStatus.model_validate(status)


@router.get("/providers", response_model=ProvidersResponse, summary="AI providers and this user's credential status")
def list_providers(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProvidersResponse:
    return ProvidersResponse.model_validate(settings_service.providers_catalog(db, user))


@router.get("/settings", response_model=SettingsRead, summary="The user's AI model settings")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SettingsRead:
    return SettingsRead.model_validate(settings_service.read_settings(db, user))


@router.put("/settings", response_model=SettingsRead, summary="Replace the user's AI model settings")
def put_settings(payload: SettingsUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SettingsRead:
    return SettingsRead.model_validate(settings_service.update_settings(db, user, payload))


@router.put("/credentials/{provider}", response_model=CredentialRead, summary="Save or rotate a provider credential")
def put_credential(
    provider: str,
    payload: CredentialWrite,
    user: User = Depends(require_recent_auth),
    db: Session = Depends(get_db),
) -> CredentialRead:
    _provider_or_404(provider, allow_mock=False)
    return CredentialRead.model_validate(settings_service.save_credential(db, user, provider, payload))


@router.delete("/credentials/{provider}", status_code=204, summary="Remove a provider credential")
def delete_credential(provider: str, user: User = Depends(require_recent_auth), db: Session = Depends(get_db)) -> Response:
    _provider_or_404(provider, allow_mock=False)
    settings_service.delete_credential(db, user, provider)
    return Response(status_code=204)


@router.post("/credentials/{provider}/test", response_model=ConnectionTestResult, summary="Test a provider connection")
def test_credential(
    provider: str,
    payload: ConnectionTestRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectionTestResult:
    _provider_or_404(provider)
    _limit_outbound(user, "test")
    model = payload.model if payload else None
    return ConnectionTestResult.model_validate(settings_service.run_connection_test(db, user, provider, model))


@router.get("/providers/{provider}/models", response_model=ModelsResponse, summary="Models available to this user")
def list_models(
    provider: str,
    refresh: bool = Query(default=False, description="Fetch the live list again instead of the 10-minute cache"),
    live: bool = Query(default=True, description="false = registry only, no provider call"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ModelsResponse:
    _provider_or_404(provider)
    if live and (refresh or provider != "ollama"):
        _limit_outbound(user, "models")
    return ModelsResponse.model_validate(settings_service.models_for(db, user, provider, refresh=refresh, live=live))


@router.get("/usage", response_model=UsageResponse, summary="AI calls, tokens and estimated cost")
def get_usage(
    range: str = Query(default="30d", pattern="^(7d|30d|month)$"),  # noqa: A002 - the public query name
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UsageResponse:
    row = settings_service.get_settings_row(db, user.id)
    return UsageResponse.model_validate(usage_summary(db, user.id, range, settings_row=row))
