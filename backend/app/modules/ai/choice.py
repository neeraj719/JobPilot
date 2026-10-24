""""Which model should process this?" — per-run model choice (``ai-model-choice``).

When a user has two or more usable AI models, the UI asks before each AI action which one
should process the run. Two halves:

* :func:`list_choices` (``GET /ai/choices?task=``) — the candidates for a task: the task's
  routed default first, then one entry per provider the user holds a credential for (the
  model routed for the workflow, else the provider default, plus up to three models the user
  recently used with it), the local Ollama models when the server answers, and the server
  default. Hosted providers the server forbids are hidden; a credential whose last test
  failed, a provider missing its key or a hosted provider before the data-sharing
  acknowledgement are listed with ``available: false`` and the reason. Cached per user for
  :data:`CACHE_TTL_SECONDS`; every settings / credential write calls
  :func:`invalidate_choices`.
* :func:`validate_choice` / :func:`apply_choice` — every AI endpoint accepts an optional
  ``ai: {provider, model}`` (multipart: ``ai_provider`` / ``ai_model``). The choice is
  validated here and published on the request's AI slot (``ai.context``), so
  ``ai.runtime.resolve_current`` returns it with ``source="per_run"`` for every task of the
  request — no call-site signature changes. Errors: 403 ``ai_hosted_disabled``, 409
  ``ai_credential_missing``, 422 ``ai_model_unknown`` / ``data_residency_ack_required`` /
  ``ai_choice_incomplete``.

The per-run choice is always honoured when valid; ``model_prompt_mode`` (``ask`` |
``default``) only tells the UI whether to ask.
"""
from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, ValidationFailed
from app.models.ai_settings import AiProviderCredential, AiUsageEvent, AiUsageStatus
from app.models.user import User
from app.modules.ai import context, registry, settings_service
from app.modules.ai.errors import label
from app.modules.ai.routing import (
    CONFIGURABLE_WORKFLOWS,
    SOURCE_TASK_OVERRIDE,
    SOURCE_USER_DEFAULT,
    Target,
    default_model_for,
    resolve_from,
    server_default,
)
from app.modules.ai.settings_schemas import WorkflowTarget

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60
#: Recently used models offered per provider.
RECENT_PER_PROVIDER = 3

SOURCE_MAP = {SOURCE_TASK_OVERRIDE: "workflow_default", SOURCE_USER_DEFAULT: "user_default"}

_cache: dict[tuple[uuid.UUID, str], tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


# --------------------------------------------------------------------------- cache


def invalidate_choices(user_id: uuid.UUID | None = None) -> None:
    """Forget cached candidates of ``user_id`` (everyone when ``None``)."""
    with _cache_lock:
        if user_id is None:
            _cache.clear()
            return
        for key in [k for k in _cache if k[0] == user_id]:
            _cache.pop(key, None)


def _cached(key: tuple[uuid.UUID, str]) -> dict[str, Any] | None:
    with _cache_lock:
        hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]
    return None


def _store(key: tuple[uuid.UUID, str], value: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)


# --------------------------------------------------------------------------- helpers


def choice_id(provider: str, model: str) -> str:
    return f"{provider}:{model}"


def cost_hint(provider: str, model: str, base_url: str | None = None) -> str:
    """``free, local`` | ``≈ $x per 1k tokens`` (blended registry estimate) | ``unknown``."""
    if registry.is_free(provider):
        return "free, local"
    if provider == "openai_compatible":
        from app.modules.ai.base_url import is_local_url

        return "free, local" if base_url and is_local_url(base_url) else "unknown"
    entry = registry.model_info(provider, model)
    if entry is None or entry.input_per_m is None or entry.output_per_m is None:
        return "unknown"
    per_k = float(entry.input_per_m + entry.output_per_m) / 2 / 1000
    if per_k <= 0:
        return "free"
    decimals = max(2, -int(math.floor(math.log10(per_k))) + 1)
    return f"≈ ${per_k:.{decimals}f} per 1k tokens"


def _label(provider: str, model: str) -> str:
    if provider == "mock":
        return "Built-in rules (no AI)"
    entry = registry.model_info(provider, model)
    return entry.display_name if entry else model


def recent_models(db: Session, user_id: uuid.UUID) -> dict[str, list[tuple[str, datetime]]]:
    """``{provider: [(model, last_used_at), ...]}`` from successful calls, newest first."""
    rows = db.execute(
        select(AiUsageEvent.provider, AiUsageEvent.model, func.max(AiUsageEvent.created_at))
        .where(
            AiUsageEvent.user_id == user_id,
            AiUsageEvent.status.in_((AiUsageStatus.OK, AiUsageStatus.FALLBACK)),
            AiUsageEvent.provider != "mock",
        )
        .group_by(AiUsageEvent.provider, AiUsageEvent.model)
        .order_by(func.max(AiUsageEvent.created_at).desc())
    ).all()
    out: dict[str, list[tuple[str, datetime]]] = {}
    for provider, model, last in rows:
        if model:
            out.setdefault(str(provider), []).append((str(model), last))
    return out


def _ollama_models(user: User, cred: AiProviderCredential | None) -> list[str] | None:
    """Models pulled on the user's Ollama server (``None`` when it does not answer).

    Uses the settings page's 10-minute model cache; a fresh probe only hits the local server.
    """
    models, _, error = settings_service.live_models(user, "ollama", cred, refresh=False)
    if error is not None or models is None:
        return None
    return [str(m.get("id")) for m in models if m.get("id")]


def _live_models_cached(user: User, provider: str, cred: AiProviderCredential | None, *, fetch: bool) -> list[str] | None:
    """The provider's live model ids: the short cache, or (``fetch``) one listing call."""
    key = settings_service._model_cache_key(user.id, provider, cred)
    hit = settings_service._cached_models(key)
    if hit:
        return [str(m.get("id")) for m in hit[1] if m.get("id")]
    if not fetch:
        return None
    models, _, error = settings_service.live_models(user, provider, cred, refresh=False)
    if error is not None or models is None:
        return None
    return [str(m.get("id")) for m in models if m.get("id")]


def _problem(provider: str, creds: dict[str, AiProviderCredential], row: Any) -> str | None:
    """Why the user cannot run ``provider`` now (``None`` = available)."""
    problem = settings_service.target_problem(provider, creds)
    if problem:
        return problem
    cred = creds.get(provider)
    if cred is not None and str(getattr(cred.status, "value", cred.status)) == "ERROR":
        return cred.last_error or "The last connection test failed. Test the connection again in AI Model Settings."
    base_url = cred.base_url if cred else None
    if settings_service._hosted(provider, base_url) and not (row is not None and row.data_residency_ack):
        return "Confirm in AI Model Settings that hosted providers may receive your resume text."
    return None


# --------------------------------------------------------------------------- candidates


def list_choices(db: Session, user: User, task: str, *, use_cache: bool = True) -> dict[str, Any]:
    """The ``GET /ai/choices`` answer for ``task`` (see the module docstring)."""
    task = (task or "general").strip() or "general"
    key = (user.id, task)
    if use_cache:
        hit = _cached(key)
        if hit is not None:
            return hit
    value = _build_choices(db, user, task)
    _store(key, value)
    return value


def _build_choices(db: Session, user: User, task: str) -> dict[str, Any]:
    row = settings_service.get_settings_row(db, user.id)
    creds = {c.provider: c for c in settings_service.list_credential_rows(db, user.id)}
    resolved = resolve_from(row, task, user_id=user.id)
    workflow = resolved.workflow
    try:
        recent = recent_models(db, user.id)
    except Exception as exc:  # noqa: BLE001 - usage history is a nicety
        logger.warning("Could not read recent AI models (%s)", type(exc).__name__)
        recent = {}
    last_used = {choice_id(p, m): at for p, items in recent.items() for m, at in items}
    hosted_allowed = bool(settings.AI_ALLOW_HOSTED_PROVIDERS)

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(provider: str, model: str, source: str, *, is_default: bool = False) -> None:
        if not provider or not model:
            return
        cid = choice_id(provider, model)
        if cid in seen:
            return
        info = registry.provider_info(provider)
        if info is None:
            return
        cred = creds.get(provider)
        base_url = cred.base_url if cred else None
        hosted = settings_service._hosted(provider, base_url)
        if hosted and not hosted_allowed and not is_default:
            return  # hidden: the server forbids hosted providers
        problem = _problem(provider, creds, row) if provider != "mock" else None
        seen.add(cid)
        candidates.append(
            {
                "id": cid,
                "provider": provider,
                "provider_name": info.name,
                "model": model,
                "label": _label(provider, model),
                "source": source,
                "is_default": is_default,
                "hosted": hosted,
                "privacy_note": info.privacy_note,
                "cost_hint": cost_hint(provider, model, base_url),
                "available": problem is None,
                "unavailable_reason": problem,
                "last_used_at": last_used.get(cid),
            }
        )

    # 1. the routed default for this task
    add(resolved.provider, resolved.model, SOURCE_MAP.get(resolved.source, "server_default"), is_default=True)
    default_id = choice_id(resolved.provider, resolved.model)

    routed = (getattr(row, "workflow_models", None) or {}).get(workflow) if row is not None else None

    def preferred_model(provider: str) -> str | None:
        if isinstance(routed, dict) and routed.get("provider") == provider and routed.get("model"):
            return str(routed["model"])
        if row is not None and row.default_provider == provider and row.default_model:
            return row.default_model
        return default_model_for(provider) or None

    # 2. one entry per provider with a credential (+ recently used models of it)
    for provider in registry.PROVIDER_ORDER:
        if provider in ("mock", "ollama") or provider not in creds:
            continue
        models: list[str] = []
        first = preferred_model(provider)
        if first:
            models.append(first)
        models.extend(m for m, _ in recent.get(provider, [])[:RECENT_PER_PROVIDER])
        if not models and provider == "openai_compatible":
            live = _live_models_cached(user, provider, creds[provider], fetch=True)
            models.extend((live or [])[:1])
        for model in models:
            add(provider, model, "credential")

    # 3. local Ollama models when the server answers
    try:
        local = _ollama_models(user, creds.get("ollama"))
    except Exception as exc:  # noqa: BLE001 - a missing local server only hides its models
        logger.info("Ollama models unavailable for the model picker (%s)", type(exc).__name__)
        local = None
    if local:
        ordered = [m for m in [preferred_model("ollama")] if m and m in local] + [m for m in local]
        for model in ordered:
            add("ollama", model, "local")

    # 4. the server default, when it is a real model and usable
    server = server_default()
    if server.provider != "mock" and server.model:
        add(server.provider, server.model, "server_default")

    usable = sum(1 for c in candidates if c["available"])
    mode = settings_service.prompt_mode(row)
    return {
        "task": task,
        "workflow": workflow,
        "workflow_label": CONFIGURABLE_WORKFLOWS.get(workflow, workflow),
        "mode": mode,
        "default": default_id,
        "candidates": candidates,
        "usable_count": usable,
        "should_ask": mode == "ask" and usable >= 2,
    }


# --------------------------------------------------------------------------- validation


def _model_ok(db: Session, user: User, provider: str, model: str, row: Any, cred: AiProviderCredential | None) -> bool:
    if provider == "mock":
        return model == registry.PROVIDERS["mock"].default_model
    # what the user's routing already points at, and the server default, are always fine
    known: set[tuple[str, str]] = {(server_default().provider, server_default().model)}
    if row is not None:
        if row.default_provider and row.default_model:
            known.add((row.default_provider, row.default_model))
        for target in (row.workflow_models or {}).values():
            if isinstance(target, dict):
                known.add((str(target.get("provider")), str(target.get("model"))))
        if row.fallback_provider and row.fallback_model:
            known.add((row.fallback_provider, row.fallback_model))
    if (provider, model) in known:
        return True
    if any(m == model for m, _ in recent_models(db, user.id).get(provider, [])):
        return True
    if provider == "ollama":
        local = _ollama_models(user, cred)
        if local is not None:
            return model in local
        return registry.model_info(provider, model) is not None
    if provider == "openai_compatible":
        live = _live_models_cached(user, provider, cred, fetch=True)
        return True if live is None else model in live
    live = _live_models_cached(user, provider, cred, fetch=False)  # hosted: never a network call per run
    if live is not None and model in live:
        return True
    return registry.model_info(provider, model) is not None


def validate_choice(db: Session, user: User, target: WorkflowTarget) -> Target:
    """Check a per-run choice; return the routing target to publish.

    403 ``ai_hosted_disabled`` · 409 ``ai_credential_missing`` · 422 ``ai_model_unknown`` /
    ``data_residency_ack_required``.
    """
    provider = target.provider
    model = (target.model or "").strip()
    info = registry.provider_info(provider)
    if info is None:
        raise ValidationFailed(f"Unknown AI provider {provider!r}.", code="ai_model_unknown", details={"provider": provider})
    creds = {c.provider: c for c in settings_service.list_credential_rows(db, user.id)}
    cred = creds.get(provider)
    base_url = cred.base_url if cred else None
    hosted = settings_service._hosted(provider, base_url)
    if hosted and not settings.AI_ALLOW_HOSTED_PROVIDERS:
        raise ForbiddenError(
            "Hosted AI providers are disabled on this server; choose the local model or the built-in rules.",
            code="ai_hosted_disabled",
            details={"provider": provider},
        )
    problem = settings_service.target_problem(provider, creds) if provider != "mock" else None
    if problem:
        raise ConflictError(problem, code="ai_credential_missing", details={"provider": provider})
    row = settings_service.get_settings_row(db, user.id)
    if hosted and not (row is not None and row.data_residency_ack):
        raise ValidationFailed(
            f"Confirm in AI Model Settings that hosted providers receive your resume and job text before using {label(provider)}.",
            code="data_residency_ack_required",
            details={"provider": provider},
        )
    if not model or not _model_ok(db, user, provider, model, row, cred):
        raise ValidationFailed(
            f"{label(provider)} does not offer model {model!r}. Pick one of the listed models.",
            code="ai_model_unknown",
            details={"provider": provider, "model": model},
        )
    return Target(provider, model)


def apply_choice(db: Session, user: User, target: WorkflowTarget | None) -> Target | None:
    """Validate ``target`` and make it the model of every AI call in this request."""
    if target is None:
        return None
    chosen = validate_choice(db, user, target)
    if not context.set_target_override(chosen):  # pragma: no cover - every request has a slot
        logger.warning("No AI context slot for a per-run model choice; the routing applies")
    return chosen


def form_target(provider: str | None, model: str | None) -> WorkflowTarget | None:
    """The multipart form fields ``ai_provider`` / ``ai_model`` as a :class:`WorkflowTarget`."""
    provider = (provider or "").strip()
    model = (model or "").strip()
    if not provider and not model:
        return None
    if not provider or not model:
        raise ValidationFailed("Send both ai_provider and ai_model, or neither.", code="ai_choice_incomplete")
    try:
        return WorkflowTarget(provider=provider, model=model)  # type: ignore[arg-type]
    except ValidationError as exc:
        raise ValidationFailed(f"Unknown AI provider {provider!r}.", code="ai_model_unknown", details={"provider": provider}) from exc


__all__ = [
    "CACHE_TTL_SECONDS",
    "apply_choice",
    "choice_id",
    "cost_hint",
    "form_target",
    "invalidate_choices",
    "list_choices",
    "recent_models",
    "validate_choice",
]
