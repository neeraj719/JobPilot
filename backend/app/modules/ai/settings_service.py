"""AI Model Settings: per-user routing, encrypted credentials, connection tests, model lists.

Services never commit (``get_db`` owns the transaction). Every query is scoped to the
user. Secrets:

* a key is encrypted with ``app.core.security.encrypt_str`` the moment it arrives and only
  ever decrypted inside :func:`_provider_for_test` / ``ai.runtime`` to build a client;
* nothing here returns, logs or audits a key — the API sees ``masked_key`` (``••••1234``);
* removing a key soft-deletes the row **and** wipes the ciphertext and hint;
* every save bumps ``credential_version`` and evicts the runtime's cached clients, so a
  rotated key is never used again.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationFailed
from app.core.security import decrypt_str, encrypt_str
from app.core.soft_delete import soft_delete
from app.models.ai_settings import AiCredentialStatus, AiProviderCredential, AiProviderSettings
from app.models.enums import Actor
from app.models.user import User
from app.modules.ai import registry, runtime
from app.modules.ai.base_url import is_local_url, validate_base_url
from app.modules.ai.errors import AIProviderError, label, map_exception
from app.modules.ai.provider import LLMProvider
from app.modules.ai.routing import CONFIGURABLE_WORKFLOWS, Resolved, Target, resolve_from, server_default
from app.modules.ai.settings_schemas import CredentialWrite, SettingsUpdate

logger = logging.getLogger(__name__)

MASK = "••••"
#: Live model lists are cached briefly: the settings page and the save validation reuse them.
MODEL_LIST_TTL_SECONDS = 600
#: Providers whose key is mandatory; Ollama takes no key at all.
KEY_REQUIRED = frozenset({"openai", "gemini", "anthropic"})
NO_KEY = frozenset({"ollama", "mock"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- reads


def get_settings_row(db: Session, user_id: uuid.UUID) -> AiProviderSettings | None:
    return db.scalar(select(AiProviderSettings).where(AiProviderSettings.user_id == user_id))


def list_credential_rows(db: Session, user_id: uuid.UUID) -> list[AiProviderCredential]:
    return list(
        db.scalars(
            select(AiProviderCredential)
            .where(AiProviderCredential.user_id == user_id)
            .order_by(AiProviderCredential.provider)
        )
    )


def get_credential_row(db: Session, user_id: uuid.UUID, provider: str) -> AiProviderCredential | None:
    return db.scalar(
        select(AiProviderCredential).where(
            AiProviderCredential.user_id == user_id, AiProviderCredential.provider == provider
        )
    )


def credential_read(row: AiProviderCredential) -> dict[str, Any]:
    return {
        "provider": row.provider,
        "has_key": bool(row.encrypted_api_key),
        "masked_key": f"{MASK}{row.key_hint}" if row.encrypted_api_key and row.key_hint else (MASK if row.encrypted_api_key else None),
        "base_url": row.base_url,
        "credential_version": int(row.credential_version or 1),
        "status": str(row.status.value if hasattr(row.status, "value") else row.status),
        "last_tested_at": row.last_tested_at,
        "last_latency_ms": row.last_latency_ms,
        "last_error": row.last_error,
        "last_error_code": row.last_error_code,
        "rotated_at": row.rotated_at,
        "updated_at": row.updated_at,
    }


def _hosted(provider: str, base_url: str | None) -> bool:
    if provider in ("openai", "gemini", "anthropic"):
        return True
    return provider == "openai_compatible" and not is_local_url(base_url)


def _server_key(provider: str) -> bool:
    from app.modules.ai.factory import api_key_for

    return bool(api_key_for(provider))


def target_problem(provider: str, credentials: dict[str, AiProviderCredential]) -> str | None:
    """Why ``provider`` cannot be used by this user right now (``None`` = usable)."""
    if not registry.known_provider(provider):
        return f"Unknown provider {provider!r}."
    cred = credentials.get(provider)
    base_url = cred.base_url if cred else None
    if _hosted(provider, base_url) and not settings.AI_ALLOW_HOSTED_PROVIDERS:
        return "Hosted providers are disabled on this server."
    if provider in NO_KEY:
        return None
    if provider == "openai_compatible":
        return None if cred is not None and cred.base_url else "Add the server's base URL first."
    if cred is not None and cred.encrypted_api_key:
        return None
    if provider == server_default().provider and _server_key(provider):
        return None
    return f"Add your {label(provider)} API key first."


def _summary(resolved: Resolved) -> str:
    provider, model = resolved.provider, resolved.model
    info = registry.provider_info(provider)
    if provider == "mock":
        return "Built-in rules — no AI model, private, free"
    if provider == "ollama":
        return f"Local Ollama · {model} — private, free"
    if info and info.kind == "hosted":
        return f"{info.name} · {model} — hosted, billed by {info.name.split()[0]} to your API key"
    return f"{label(provider)} · {model}"


def read_settings(db: Session, user: User) -> dict[str, Any]:
    row = get_settings_row(db, user.id)
    creds = {c.provider: c for c in list_credential_rows(db, user.id)}
    effective: dict[str, Any] = {}
    for workflow in CONFIGURABLE_WORKFLOWS:
        resolved = resolve_from(row, workflow, user_id=user.id, workflow=workflow)
        problem = target_problem(resolved.provider, creds)
        effective[workflow] = {
            "provider": resolved.provider,
            "model": resolved.model,
            "source": resolved.source,
            "usable": problem is None,
            "problem": problem,
        }
    general = resolve_from(row, "general", user_id=user.id, workflow="general")
    fallback = None
    if row is not None and row.fallback_enabled and row.fallback_provider:
        fb_model = row.fallback_model or registry.provider_info(row.fallback_provider).default_model or ""  # type: ignore[union-attr]
        problem = target_problem(row.fallback_provider, creds)
        fallback = {"provider": row.fallback_provider, "model": fb_model, "source": "fallback", "usable": problem is None, "problem": problem}
    server = server_default()
    default_problem = effective["general"]["problem"]
    return {
        "default_provider": row.default_provider if row else None,
        "default_model": row.default_model if row else None,
        "workflow_models": dict(row.workflow_models or {}) if row else {},
        "fallback_enabled": bool(row.fallback_enabled) if row else False,
        "fallback_provider": row.fallback_provider if row else None,
        "fallback_model": row.fallback_model if row else None,
        "daily_call_limit": row.daily_call_limit if row else None,
        "monthly_budget_usd": float(row.monthly_budget_usd) if row and row.monthly_budget_usd is not None else None,
        "data_residency_ack": bool(row.data_residency_ack) if row else False,
        "effective": effective,
        "fallback": fallback,
        "server_default": {"provider": server.provider, "model": server.model},
        "hosted_allowed": bool(settings.AI_ALLOW_HOSTED_PROVIDERS),
        "credentials": [credential_read(c) for c in creds.values()],
        "summary": _summary(general),
        "status": {
            "provider": general.provider,
            "model": general.model,
            "source": general.source,
            "configured": default_problem is None,
            "problem": default_problem,
            "hosted": general.provider in ("openai", "gemini", "anthropic", "openai_compatible"),
        },
        "updated_at": row.updated_at if row else None,
    }


def providers_catalog(db: Session, user: User) -> dict[str, Any]:
    creds = {c.provider: c for c in list_credential_rows(db, user.id)}
    server = server_default()
    providers = []
    for provider_id in registry.PROVIDER_ORDER:
        info = registry.PROVIDERS[provider_id]
        entry = registry.catalog_entry(info)
        cred = creds.get(provider_id)
        entry["allowed"] = settings.AI_ALLOW_HOSTED_PROVIDERS or info.kind != "hosted"
        entry["is_server_default"] = provider_id == server.provider
        entry["server_key_configured"] = provider_id == server.provider and _server_key(provider_id)
        if provider_id == server.provider and provider_id != "mock" and server.model:
            entry["default_model"] = server.model
        entry["credential"] = credential_read(cred) if cred else None
        providers.append(entry)
    return {
        "providers": providers,
        "workflows": [{"id": k, "label": v} for k, v in CONFIGURABLE_WORKFLOWS.items()],
        "server_default": {"provider": server.provider, "model": server.model},
        "billing_note": registry.BILLING_NOTE,
        "hosted_allowed": bool(settings.AI_ALLOW_HOSTED_PROVIDERS),
    }


# --------------------------------------------------------------------------- live model lists

_model_cache: dict[tuple, tuple[float, list[dict[str, Any]]]] = {}
_model_cache_lock = threading.Lock()


def _model_cache_key(user_id: uuid.UUID, provider: str, cred: AiProviderCredential | None) -> tuple:
    return (user_id, provider, cred.id if cred else None, int(cred.credential_version) if cred else 0, cred.base_url if cred else None)


def _cached_models(key: tuple) -> tuple[float, list[dict[str, Any]]] | None:
    with _model_cache_lock:
        hit = _model_cache.get(key)
    if hit and time.monotonic() - hit[0] < MODEL_LIST_TTL_SECONDS:
        return hit
    return None


def _store_models(key: tuple, models: list[dict[str, Any]]) -> None:
    with _model_cache_lock:
        _model_cache[key] = (time.monotonic(), models)


def forget_models(user_id: uuid.UUID, provider: str | None = None) -> None:
    with _model_cache_lock:
        for key in [k for k in _model_cache if k[0] == user_id and (provider is None or k[1] == provider)]:
            _model_cache.pop(key, None)


def _provider_for_test(user_id: uuid.UUID, provider: str, model: str | None, cred: AiProviderCredential | None) -> LLMProvider:
    """A throw-away client for a test / model listing (never cached, never a global)."""
    info = registry.provider_info(provider)
    if info is None:
        raise NotFoundError("Unknown AI provider")
    chosen = model or ""
    if not chosen and provider == server_default().provider:
        chosen = server_default().model or ""
    chosen = chosen or info.default_model or ""
    base_url = cred.base_url if cred else None
    if base_url:
        base_url = validate_base_url(base_url)
    if _hosted(provider, base_url) and not settings.AI_ALLOW_HOSTED_PROVIDERS:
        raise AIProviderError("provider_not_configured", "Hosted providers are disabled on this server.", provider=provider)
    api_key = None
    if cred is not None and cred.encrypted_api_key:
        try:
            api_key = decrypt_str(cred.encrypted_api_key)
        except ValueError as exc:
            raise AIProviderError(
                "provider_not_configured", "The stored API key can no longer be read. Enter it again.", provider=provider
            ) from exc
    elif provider in KEY_REQUIRED and not (provider == server_default().provider and _server_key(provider)):
        raise AIProviderError("provider_not_configured", f"Add your {label(provider)} API key first.", provider=provider)
    if provider == "openai_compatible" and not chosen:
        chosen = "default"
    return runtime.construct_provider(provider, chosen, api_key=api_key, base_url=base_url)


def live_models(user: User, provider: str, cred: AiProviderCredential | None, *, refresh: bool) -> tuple[list[dict[str, Any]] | None, float | None, AIProviderError | None]:
    """``(models, fetched_monotonic, error)`` — from the short cache unless ``refresh``."""
    key = _model_cache_key(user.id, provider, cred)
    if not refresh:
        hit = _cached_models(key)
        if hit:
            return hit[1], hit[0], None
    if provider == "mock":
        return None, None, None
    try:
        client = _provider_for_test(user.id, provider, None, cred)
        models = client.list_models()
    except AIProviderError as exc:
        return None, None, exc
    except Exception as exc:  # noqa: BLE001
        return None, None, map_exception(provider, exc)
    if models is None:
        return None, None, None
    _store_models(key, models)
    return models, time.monotonic(), None


def models_for(db: Session, user: User, provider: str, *, refresh: bool = False, live: bool = True) -> dict[str, Any]:
    info = registry.provider_info(provider)
    if info is None:
        raise NotFoundError("Unknown AI provider")
    cred = get_credential_row(db, user.id, provider)
    models: list[dict[str, Any]] | None = None
    error: AIProviderError | None = None
    fetched: float | None = None
    can_list = info.supports_live_models and (provider in NO_KEY or target_problem(provider, {provider: cred} if cred else {}) is None)
    if live and can_list:
        models, fetched, error = live_models(user, provider, cred, refresh=refresh)
    elif can_list:  # no network: a recent live list is still shown
        hit = _cached_models(_model_cache_key(user.id, provider, cred))
        if hit:
            fetched, models = hit
    rows = registry.merge_models(provider, models)
    fetched_at = None
    if fetched is not None:
        fetched_at = datetime.fromtimestamp(time.time() - (time.monotonic() - fetched), tz=timezone.utc)
    return {
        "provider": provider,
        "models": rows,
        "live": models is not None,
        "fetched_at": fetched_at,
        "error_code": error.code if error else None,
        "error": error.message if error else None,
        "prices_as_of": info.prices_as_of,
    }


def model_known(db: Session, user: User, provider: str, model: str) -> bool:
    """A chosen model exists: the live list when reachable (cached), else the registry."""
    if provider == "openai_compatible":
        return True  # no registry; the user names the model their server runs
    if provider == "mock":
        return model == registry.PROVIDERS["mock"].default_model
    cred = get_credential_row(db, user.id, provider)
    models = None
    info = registry.PROVIDERS[provider]
    if info.supports_live_models and target_problem(provider, {provider: cred} if cred else {}) is None:
        models, _, _ = live_models(user, provider, cred, refresh=False)
    if models is not None:
        return any(str(m.get("id")) == model for m in models)
    return registry.model_info(provider, model) is not None or (provider == server_default().provider and model == server_default().model)


# --------------------------------------------------------------------------- settings writes


def _validate_target(db: Session, user: User, provider: str, model: str | None, creds: dict[str, AiProviderCredential], *, what: str) -> tuple[str, str]:
    problem = target_problem(provider, creds)
    if problem:
        raise ValidationFailed(f"{what}: {problem}", code="provider_not_configured", details={"field": what, "provider": provider})
    from app.modules.ai.routing import default_model_for

    chosen = (model or "").strip() or default_model_for(provider)
    if not chosen:
        raise ValidationFailed(f"{what}: choose a model.", code="model_required", details={"field": what})
    if not model_known(db, user, provider, chosen):
        raise ValidationFailed(
            f"{what}: {label(provider)} does not offer model {chosen!r}. Refresh the model list and pick one of them.",
            code="unknown_model",
            details={"field": what, "provider": provider, "model": chosen},
        )
    return provider, chosen


def update_settings(db: Session, user: User, payload: SettingsUpdate) -> dict[str, Any]:
    creds = {c.provider: c for c in list_credential_rows(db, user.id)}
    hosted_used: list[str] = []

    default_provider = payload.default_provider
    default_model = None
    if default_provider:
        default_provider, default_model = _validate_target(db, user, default_provider, payload.default_model, creds, what="Default model")
        if _hosted(default_provider, creds.get(default_provider).base_url if creds.get(default_provider) else None):
            hosted_used.append(default_provider)

    workflows: dict[str, dict[str, str]] = {}
    for workflow, target in payload.workflow_models.items():
        what = CONFIGURABLE_WORKFLOWS.get(workflow, workflow)
        provider, model = _validate_target(db, user, target.provider, target.model, creds, what=what)
        workflows[workflow] = {"provider": provider, "model": model}
        if _hosted(provider, creds.get(provider).base_url if creds.get(provider) else None):
            hosted_used.append(provider)

    fallback_provider = payload.fallback_provider
    fallback_model = None
    if payload.fallback_enabled:
        if not fallback_provider:
            raise ValidationFailed("Choose a fallback provider, or turn the fallback off.", code="fallback_required", details={"field": "fallback"})
        fallback_provider, fallback_model = _validate_target(db, user, fallback_provider, payload.fallback_model, creds, what="Fallback")
        primary = Target(default_provider, default_model) if default_provider else server_default()
        if Target(fallback_provider, fallback_model) == primary:
            raise ValidationFailed("The fallback must differ from the default model.", code="fallback_same_as_default", details={"field": "fallback"})
        if _hosted(fallback_provider, creds.get(fallback_provider).base_url if creds.get(fallback_provider) else None):
            hosted_used.append(fallback_provider)
    elif fallback_provider:
        # Remember the choice while it is switched off, but only if it is still valid.
        try:
            fallback_provider, fallback_model = _validate_target(db, user, fallback_provider, payload.fallback_model, creds, what="Fallback")
        except ValidationFailed:
            fallback_provider, fallback_model = None, None

    if hosted_used and not payload.data_residency_ack:
        raise ValidationFailed(
            "Confirm that you understand hosted providers receive your resume and job text before selecting "
            + ", ".join(sorted({label(p) for p in hosted_used}))
            + ".",
            code="data_residency_ack_required",
            details={"field": "data_residency_ack", "providers": sorted(set(hosted_used))},
        )

    row = get_settings_row(db, user.id)
    before = _settings_snapshot(row)
    if row is None:
        row = AiProviderSettings(user_id=user.id, workflow_models={})
        db.add(row)
    row.default_provider = default_provider
    row.default_model = default_model
    row.workflow_models = workflows
    row.fallback_enabled = bool(payload.fallback_enabled)
    row.fallback_provider = fallback_provider
    row.fallback_model = fallback_model
    row.daily_call_limit = payload.daily_call_limit
    row.monthly_budget_usd = Decimal(str(payload.monthly_budget_usd)) if payload.monthly_budget_usd is not None else None
    row.data_residency_ack = bool(payload.data_residency_ack)
    db.flush()
    after = _settings_snapshot(row)
    changed = sorted(k for k in after if before.get(k) != after.get(k))
    audit(
        db,
        action="ai.settings_updated",
        message="AI model settings updated",
        user_id=user.id,
        actor=Actor.USER,
        meta={"changed": changed, "default": after.get("default"), "fallback_enabled": after.get("fallback_enabled")},
    )
    db.refresh(row)
    return read_settings(db, user)


def _settings_snapshot(row: AiProviderSettings | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "default": f"{row.default_provider}/{row.default_model}" if row.default_provider else None,
        "workflow_models": dict(row.workflow_models or {}),
        "fallback_enabled": bool(row.fallback_enabled),
        "fallback": f"{row.fallback_provider}/{row.fallback_model}" if row.fallback_provider else None,
        "daily_call_limit": row.daily_call_limit,
        "monthly_budget_usd": str(row.monthly_budget_usd) if row.monthly_budget_usd is not None else None,
        "data_residency_ack": bool(row.data_residency_ack),
    }


# --------------------------------------------------------------------------- credentials


def _check_provider(provider: str) -> registry.ProviderInfo:
    info = registry.provider_info(provider)
    if info is None or provider == "mock":
        raise NotFoundError("Unknown AI provider")
    return info


def save_credential(db: Session, user: User, provider: str, payload: CredentialWrite) -> dict[str, Any]:
    """Create or rotate the user's credential for ``provider`` (requires recent auth — router)."""
    info = _check_provider(provider)
    api_key = payload.api_key
    base_url = (payload.base_url or "").strip() or None
    if provider == "ollama" and api_key:
        raise ValidationFailed("Ollama does not use an API key; set only the base URL.", code="key_not_accepted")
    if not info.supports_base_url and base_url:
        raise ValidationFailed(f"{info.name} does not take a custom base URL.", code="base_url_not_accepted")
    if base_url:
        base_url = validate_base_url(base_url)
    if provider == "openai_compatible" and not base_url:
        raise ValidationFailed("Enter the server's base URL.", code="invalid_base_url", details={"field": "base_url"})
    if provider == "ollama" and not base_url:
        raise ValidationFailed("Enter the Ollama server's base URL.", code="invalid_base_url", details={"field": "base_url"})

    row = get_credential_row(db, user.id, provider)
    rotating = row is not None
    if provider in KEY_REQUIRED and not api_key and not (row is not None and row.encrypted_api_key):
        raise ValidationFailed(f"Paste your {info.name} API key.", code="api_key_required", details={"field": "api_key"})
    if _hosted(provider, base_url) and not settings.AI_ALLOW_HOSTED_PROVIDERS:
        raise ValidationFailed("Hosted providers are disabled on this server.", code="hosted_providers_disabled")

    now = _now()
    if row is None:
        row = AiProviderCredential(user_id=user.id, provider=provider, credential_version=1)
        db.add(row)
    else:
        row.credential_version = int(row.credential_version or 1) + 1
        row.rotated_at = now
    if api_key:
        row.encrypted_api_key = encrypt_str(api_key)
        row.key_hint = api_key[-4:]
    if provider == "ollama":
        row.encrypted_api_key, row.key_hint = None, None
    row.base_url = base_url
    row.status = AiCredentialStatus.UNTESTED
    row.last_error = None
    row.last_error_code = None
    row.last_latency_ms = None
    row.last_tested_at = None
    db.flush()
    runtime.evict_clients(user.id, provider)
    forget_models(user.id, provider)
    action = "ai.credential_rotated" if rotating else "ai.credential_saved"
    audit(
        db,
        action=action,
        message=f"{info.name} credential {'rotated' if rotating else 'saved'}",
        user_id=user.id,
        actor=Actor.USER,
        meta={"provider": provider, "credential_version": row.credential_version, "has_key": bool(row.encrypted_api_key), "base_url_set": bool(base_url)},
    )
    db.refresh(row)
    return credential_read(row)


def delete_credential(db: Session, user: User, provider: str) -> None:
    info = _check_provider(provider)
    row = get_credential_row(db, user.id, provider)
    if row is None:
        raise NotFoundError("No credential stored for this provider")
    row.encrypted_api_key = None
    row.key_hint = None
    row.status = AiCredentialStatus.UNTESTED
    row.last_error = None
    row.last_error_code = None
    soft_delete(row)
    db.flush()
    runtime.evict_clients(user.id, provider)
    forget_models(user.id, provider)
    audit(
        db,
        action="ai.credential_deleted",
        message=f"{info.name} credential removed",
        user_id=user.id,
        actor=Actor.USER,
        meta={"provider": provider},
    )


def run_connection_test(db: Session, user: User, provider: str, model: str | None = None) -> dict[str, Any]:
    """One cheap call with the stored (or server/local) configuration; result persisted."""
    info = registry.provider_info(provider)
    if info is None:
        raise NotFoundError("Unknown AI provider")
    cred = get_credential_row(db, user.id, provider)
    tested_at = _now()
    if provider == "mock":
        result = {"ok": True, "latency_ms": 0, "model": info.default_model, "model_available": True, "error_code": None, "error": None}
    else:
        chosen = (model or "").strip() or None
        if chosen is None:
            row = get_settings_row(db, user.id)
            if row is not None and row.default_provider == provider and row.default_model:
                chosen = row.default_model
        try:
            client = _provider_for_test(user.id, provider, chosen, cred)
            result = client.test_connection()
        except (AIProviderError, ValidationFailed) as exc:
            result = {"ok": False, "latency_ms": None, "model": chosen, "model_available": None, "error_code": exc.code, "error": exc.message}
        except Exception as exc:  # noqa: BLE001
            err = map_exception(provider, exc, model=chosen)
            result = {"ok": False, "latency_ms": None, "model": chosen, "model_available": None, "error_code": err.code, "error": err.message}
    if cred is not None:
        cred.status = AiCredentialStatus.OK if result["ok"] and not result.get("error_code") else AiCredentialStatus.ERROR
        cred.last_tested_at = tested_at
        cred.last_latency_ms = result.get("latency_ms")
        cred.last_error = None if cred.status == AiCredentialStatus.OK else (result.get("error") or "")[:500]
        cred.last_error_code = None if cred.status == AiCredentialStatus.OK else result.get("error_code")
        db.flush()
    if result["ok"]:
        forget_models(user.id, provider)  # the next list is fetched fresh
    audit(
        db,
        action="ai.credential_tested",
        message=f"{info.name} connection test {'passed' if result['ok'] and not result.get('error_code') else 'failed'}",
        user_id=user.id,
        actor=Actor.USER,
        meta={"provider": provider, "ok": bool(result["ok"]), "error_code": result.get("error_code"), "latency_ms": result.get("latency_ms")},
    )
    return {
        "provider": provider,
        "ok": bool(result["ok"]) and not result.get("error_code"),
        "model": result.get("model"),
        "model_available": result.get("model_available"),
        "latency_ms": result.get("latency_ms"),
        "error_code": result.get("error_code"),
        "error": result.get("error"),
        "tested_at": tested_at,
        "credential": credential_read(cred) if cred is not None else None,
    }


__all__ = [
    "delete_credential",
    "forget_models",
    "get_settings_row",
    "list_credential_rows",
    "model_known",
    "models_for",
    "providers_catalog",
    "read_settings",
    "save_credential",
    "target_problem",
    "run_connection_test",
    "update_settings",
]
