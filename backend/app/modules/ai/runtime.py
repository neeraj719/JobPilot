"""The one way to call a language model (plan contract §4.3).

::

    from app.modules.ai import runtime
    from app.modules.ai.safety import wrap_untrusted

    data = runtime.complete_json(
        "analyze_job_description",
        "Extract the requirements.\\n" + wrap_untrusted("job_description", jd_text, max_chars=12000),
        schema=JobRequirements,
    )

Each call:

1. resolves the provider/model for **the current user and task** (``ai.context`` →
   ``ai.routing``: workflow override > user default > server default);
2. enforces the user's daily call limit and monthly budget (``budget_exceeded`` *before*
   any request is made);
3. builds — or reuses — the provider client for that (user, provider, model, credential
   version). Clients are cached per user and per credential version, so a rotated or
   deleted key is never used again and one user's key never serves another user;
4. prepends :data:`ai.safety.UNTRUSTED_RULES` to the system prompt;
5. times the call and records a usage event (tokens from the SDK, else an estimate flagged
   ``tokens_estimated``; estimated cost from the registry) in its own short transaction;
6. maps every failure to :class:`ai.errors.AIProviderError` (``provider_not_configured |
   invalid_credentials | quota_exceeded | model_unavailable | provider_timeout |
   budget_exceeded | provider_error``) with a message the user can act on;
7. tries the user's fallback **only when they enabled it**, only the target they chose,
   and records that it happened (usage event ``FALLBACK``, :func:`last_call`). Nothing ever
   switches provider silently.

The deterministic mock is not "called": callers that have rules (``ai.tasks``) check
``prepare(...).provider.supports_task`` first, and a mock call made through here is answered
in-process, unrecorded and unlimited.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select, text

from app.core.config import settings
from app.modules.ai import registry
from app.modules.ai.context import current_ai_user, current_target_override
from app.modules.ai.errors import (
    BUDGET_EXCEEDED,
    PROVIDER_NOT_CONFIGURED,
    AIProviderError,
    map_exception,
    message_for,
)
from app.modules.ai.provider import LLMProvider, usage_capture
from app.modules.ai.routing import Resolved, Target, resolve_from, server_default
from app.modules.ai.safety import redact_for_logs, with_untrusted_rules

logger = logging.getLogger(__name__)

#: Rough characters-per-token used when the SDK reports no usage.
CHARS_PER_TOKEN = 4
CLIENT_CACHE_SIZE = 64

HOSTED_PROVIDERS = frozenset({"openai", "gemini", "anthropic"})


# --------------------------------------------------------------------------- results


@dataclass
class CallInfo:
    """What actually answered the last call in this context (see :func:`last_call`)."""

    task: str
    workflow: str
    provider: str
    model: str
    source: str
    fallback_used: bool = False
    primary: dict[str, str] | None = None
    primary_error_code: str | None = None
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tokens_estimated: bool = False
    estimated_cost_usd: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


_last_call: ContextVar[CallInfo | None] = ContextVar("jobpilot_ai_last_call", default=None)


def last_call() -> CallInfo | None:
    """Metadata of the most recent successful call in this thread/task (``fallback_used``…)."""
    return _last_call.get()


@dataclass
class Prepared:
    """A resolved target plus its provider instance, ready to call."""

    resolved: Resolved
    provider: LLMProvider
    extra: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- DB helpers


def _session():  # noqa: ANN202
    from app.core.database import SessionLocal

    return SessionLocal()


def _load_user_settings(user_id: uuid.UUID):  # noqa: ANN202
    from app.modules.ai.routing import load_settings

    db = None
    try:
        db = _session()
        row = load_settings(db, user_id)
        if row is not None:
            db.expunge(row)
        return row
    except Exception as exc:  # noqa: BLE001 - e.g. the migration has not run yet
        logger.warning("Could not read AI settings for user %s (%s); using the server default", user_id, type(exc).__name__)
        return None
    finally:
        if db is not None:
            db.close()


@dataclass(frozen=True)
class _Credential:
    id: uuid.UUID
    version: int
    encrypted_api_key: str | None
    base_url: str | None


def _load_credential(user_id: uuid.UUID | None, provider: str) -> _Credential | None:
    if user_id is None:
        return None
    from app.models.ai_settings import AiProviderCredential

    db = None
    try:
        db = _session()
        row = db.scalar(
            select(AiProviderCredential).where(
                AiProviderCredential.user_id == user_id, AiProviderCredential.provider == provider
            )
        )
        if row is None:
            return None
        return _Credential(row.id, int(row.credential_version or 1), row.encrypted_api_key, row.base_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read the %s credential for user %s (%s)", provider, user_id, type(exc).__name__)
        return None
    finally:
        if db is not None:
            db.close()


# --------------------------------------------------------------------------- resolution


def resolve_current(task: str, *, user_id: uuid.UUID | None = None) -> Resolved:
    """Resolve ``task`` for ``user_id`` (default: :func:`ai.context.current_ai_user`).

    A per-run model choice published by ``ai.choice.apply_choice`` (or carried into a
    background thread by ``ai.context.ai_user(..., target_override=...)``) wins with
    ``source="per_run"`` — but only for the user it was validated for.
    """
    current = current_ai_user()
    uid = user_id if user_id is not None else current
    row = _load_user_settings(uid) if uid is not None else None
    override = current_target_override() if uid is not None and uid == current else None
    return resolve_from(row, task, user_id=uid, override=override)


# --------------------------------------------------------------------------- client cache

_cache: OrderedDict[tuple, LLMProvider] = OrderedDict()
_cache_lock = threading.Lock()


def _cache_get(key: tuple) -> LLMProvider | None:
    with _cache_lock:
        provider = _cache.get(key)
        if provider is not None:
            _cache.move_to_end(key)
        return provider


def _cache_put(key: tuple, provider: LLMProvider) -> None:
    with _cache_lock:
        _cache[key] = provider
        _cache.move_to_end(key)
        while len(_cache) > CLIENT_CACHE_SIZE:
            _cache.popitem(last=False)


def evict_clients(user_id: uuid.UUID | None, provider: str | None = None) -> int:
    """Drop cached clients of ``user_id`` (optionally one provider). Called on rotate/delete."""
    with _cache_lock:
        doomed = [k for k in _cache if k[0] == user_id and (provider is None or k[1] == provider)]
        for key in doomed:
            _cache.pop(key, None)
        return len(doomed)


def clear_client_cache() -> None:
    with _cache_lock:
        _cache.clear()


def cached_client_keys() -> list[tuple]:
    """For tests and diagnostics: the cache keys (they never contain a secret)."""
    with _cache_lock:
        return list(_cache)


def _hosted(provider: str, base_url: str | None) -> bool:
    if provider in HOSTED_PROVIDERS:
        return True
    if provider == "openai_compatible":
        from app.modules.ai.base_url import is_local_url

        return not is_local_url(base_url)
    return False


def construct_provider(provider: str, model: str, *, api_key: str | None = None, base_url: str | None = None) -> LLMProvider:
    """A fresh provider instance (no caching, no DB). Raises :class:`AIProviderError`."""
    if provider == "mock":
        from app.modules.ai.factory import get_mock_provider

        return get_mock_provider()
    if provider == "ollama":
        from app.modules.ai.providers.ollama import OllamaProvider

        return OllamaProvider(base_url=base_url or None, model=model or None)
    if provider == "openai":
        from app.modules.ai.providers.openai import OpenAIProvider

        return OpenAIProvider(api_key=api_key, model=model or None)
    if provider == "anthropic":
        from app.modules.ai.providers.anthropic import AnthropicProvider

        return AnthropicProvider(api_key=api_key, model=model or None)
    if provider == "gemini":
        from app.modules.ai.providers.gemini import GeminiProvider

        return GeminiProvider(api_key=api_key, model=model or None)
    if provider == "openai_compatible":
        from app.modules.ai.providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(base_url=base_url, api_key=api_key, model=model or None)
    raise AIProviderError(PROVIDER_NOT_CONFIGURED, f"Unknown AI provider {provider!r}.", provider=provider, model=model)


def provider_for(
    target: Target,
    user_id: uuid.UUID | None,
    *,
    server_default_factory: Callable[[], LLMProvider] | None = None,
) -> LLMProvider:
    """The provider instance for ``target`` as ``user_id`` would use it.

    * the user's own credential (key and/or base URL) when they stored one;
    * otherwise, **only** for the server's own default provider, the server configuration
      (``get_llm_provider()`` for the exact default model);
    * otherwise ``provider_not_configured`` for providers that need a key.
    """
    name = target.provider
    if name == "mock":
        if target == server_default():
            from app.modules.ai.factory import get_llm_provider

            return (server_default_factory or get_llm_provider)()
        return construct_provider("mock", target.model)
    credential = _load_credential(user_id, name)
    base_url = credential.base_url if credential else None
    if _hosted(name, base_url) and not settings.AI_ALLOW_HOSTED_PROVIDERS:
        raise AIProviderError(
            PROVIDER_NOT_CONFIGURED,
            "Hosted AI providers are disabled on this server; choose the local model or the built-in rules.",
            provider=name,
            model=target.model,
        )
    server = server_default()
    if credential is None:
        if name == server.provider:
            if target.model == server.model:
                from app.modules.ai.factory import get_llm_provider

                return (server_default_factory or get_llm_provider)()
            key = (None, name, target.model, None, None, 0)
            cached = _cache_get(key)
            if cached is None:
                cached = construct_provider(name, target.model)
                _cache_put(key, cached)
            return cached
        if name == "ollama":  # local server at OLLAMA_BASE_URL, no key needed
            key = (None, name, target.model, None, None, 0)
            cached = _cache_get(key)
            if cached is None:
                cached = construct_provider(name, target.model)
                _cache_put(key, cached)
            return cached
        raise AIProviderError(
            PROVIDER_NOT_CONFIGURED, message_for(PROVIDER_NOT_CONFIGURED, name), provider=name, model=target.model
        )

    key = (user_id, name, target.model, base_url, credential.id, credential.version)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    if base_url:
        from app.modules.ai.base_url import validate_base_url

        base_url = validate_base_url(base_url)  # re-checked whenever a client is built
    api_key = None
    if credential.encrypted_api_key:
        from app.core.security import decrypt_str

        try:
            api_key = decrypt_str(credential.encrypted_api_key)
        except ValueError as exc:
            raise AIProviderError(
                PROVIDER_NOT_CONFIGURED,
                "The stored API key can no longer be read (the server's encryption key changed). Enter it again.",
                provider=name,
                model=target.model,
            ) from exc
    instance = construct_provider(name, target.model, api_key=api_key, base_url=base_url)
    _cache_put(key, instance)
    return instance


def prepare(
    task: str,
    *,
    user_id: uuid.UUID | None = None,
    server_default_factory: Callable[[], LLMProvider] | None = None,
) -> Prepared:
    """Resolve ``task`` and build its provider (may raise :class:`AIProviderError`)."""
    resolved = resolve_current(task, user_id=user_id)
    factory = server_default_factory
    provider = provider_for(resolved.target, resolved.user_id, server_default_factory=factory)
    return Prepared(resolved=resolved, provider=provider)


# --------------------------------------------------------------------------- limits


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def check_limits(user_id: uuid.UUID | None, target: Target, row: Any = None) -> None:
    """``budget_exceeded`` when the user's daily calls or monthly spend are used up."""
    if user_id is None or target.provider == "mock":
        return
    from app.models.ai_settings import AiUsageEvent

    if row is None:
        row = _load_user_settings(user_id)
    user_limit = getattr(row, "daily_call_limit", None) if row is not None else None
    limit = user_limit
    if not limit and not registry.is_free(target.provider):
        limit = settings.AI_DEFAULT_DAILY_CALL_LIMIT or None
    budget = getattr(row, "monthly_budget_usd", None) if row is not None else None
    if not limit and budget is None:
        return
    now = datetime.now(timezone.utc)
    db = None
    try:
        db = _session()
        if limit:
            stmt = select(func.count(AiUsageEvent.id)).where(
                AiUsageEvent.user_id == user_id, AiUsageEvent.created_at >= _day_start(now)
            )
            if not user_limit:  # the server default only counts hosted calls
                stmt = stmt.where(AiUsageEvent.provider.notin_(("ollama", "mock")))
            used = int(db.scalar(stmt) or 0)
            if used >= int(limit):
                raise AIProviderError(
                    BUDGET_EXCEEDED,
                    f"You reached today's limit of {int(limit)} AI calls. Raise the daily limit in AI Model Settings "
                    "or try again tomorrow.",
                    provider=target.provider,
                    model=target.model,
                    retryable=False,
                    details={"limit": "daily_calls", "used": used, "allowed": int(limit)},
                )
        if budget is not None and not registry.is_free(target.provider):
            spent = db.scalar(
                select(func.coalesce(func.sum(AiUsageEvent.estimated_cost_usd), 0)).where(
                    AiUsageEvent.user_id == user_id, AiUsageEvent.created_at >= _month_start(now)
                )
            )
            spent_value = Decimal(str(spent or 0))
            if spent_value >= Decimal(str(budget)):
                raise AIProviderError(
                    BUDGET_EXCEEDED,
                    f"This month's estimated AI spend (${spent_value:.2f}) reached your budget of ${Decimal(str(budget)):.2f}. "
                    "Raise the budget in AI Model Settings or switch to the free local model.",
                    provider=target.provider,
                    model=target.model,
                    retryable=False,
                    details={"limit": "monthly_budget", "spent_usd": float(spent_value), "budget_usd": float(budget)},
                )
    except AIProviderError:
        raise
    except Exception as exc:  # noqa: BLE001 - a broken usage table must not stop the product
        logger.warning("AI usage limits could not be checked (%s)", type(exc).__name__)
    finally:
        if db is not None:
            db.close()


# --------------------------------------------------------------------------- usage


def _estimate_tokens(*texts: str | None) -> int:
    return max(1, sum(len(t or "") for t in texts) // CHARS_PER_TOKEN)


def record_usage(
    *,
    user_id: uuid.UUID | None,
    provider: str,
    model: str,
    task: str,
    workflow: str,
    input_tokens: int,
    output_tokens: int,
    tokens_estimated: bool,
    duration_ms: int,
    status: str,
    error_code: str | None = None,
    source: str | None = None,
) -> Decimal | None:
    """Append one usage event in its own transaction (never raises). Returns the cost.

    ``source`` is how the target was chosen (``per_run`` | ``task_override`` |
    ``user_default`` | ``server_default``)."""
    cost = registry.estimate_cost(provider, model, input_tokens, output_tokens)
    if user_id is None:
        return cost
    from app.models.ai_settings import AiUsageEvent, AiUsageStatus

    db = None
    try:
        db = _session()
        if db.get_bind().dialect.name == "postgresql":
            # Never wait behind a caller's uncommitted transaction (e.g. a user row created
            # in the same request): losing one usage row beats hanging the call.
            db.execute(text("SET LOCAL lock_timeout = '2s'"))
        db.add(
            AiUsageEvent(
                user_id=user_id,
                provider=provider,
                model=(model or "")[:200],
                task=(task or "general")[:80],
                workflow=workflow,
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                tokens_estimated=bool(tokens_estimated),
                estimated_cost_usd=cost,
                duration_ms=int(duration_ms),
                status=AiUsageStatus(status),
                error_code=error_code,
                source=(source or None) and str(source)[:20],
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        if db is not None:
            db.rollback()
        logger.warning("Could not record an AI usage event (%s)", type(exc).__name__)
    finally:
        if db is not None:
            db.close()
    return cost


# --------------------------------------------------------------------------- calls


def _attempt(
    kind: str,
    resolved: Resolved,
    target: Target,
    provider: LLMProvider | None,
    *,
    prompt: str,
    system: str,
    schema: Any,
    max_tokens: int,
    temperature: float,
    status_on_success: str,
) -> tuple[Any, CallInfo]:
    user_id = resolved.user_id
    if provider is None:
        provider = provider_for(target, user_id)
    if getattr(provider, "name", "") == "mock" or getattr(provider, "is_deterministic", False):
        data = (
            provider.complete_json(prompt, schema=schema, system=system, max_tokens=max_tokens)
            if kind == "json"
            else provider.complete(prompt, system=system, max_tokens=max_tokens, temperature=temperature)
        )
        return data, CallInfo(resolved.task, resolved.workflow, "mock", provider.model or target.model, resolved.source)

    check_limits(user_id, target)
    usage_source = resolved.source if target == resolved.target else "fallback"
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("AI %s -> %s/%s prompt: %s", resolved.task, target.provider, target.model, redact_for_logs(prompt))
    started = time.perf_counter()
    with usage_capture() as usage:
        try:
            if kind == "json":
                data = provider.complete_json(prompt, schema=schema, system=system, max_tokens=max_tokens)
                if not isinstance(data, dict):
                    raise ValueError("provider returned a non-object JSON value")
            else:
                data = provider.complete(prompt, system=system, max_tokens=max_tokens, temperature=temperature)
        except Exception as exc:  # noqa: BLE001 - mapped below
            duration = int((time.perf_counter() - started) * 1000)
            err = map_exception(target.provider, exc, model=target.model)
            record_usage(
                user_id=user_id, provider=target.provider, model=target.model, task=resolved.task,
                workflow=resolved.workflow, input_tokens=usage.get("input_tokens", 0) or 0,
                output_tokens=usage.get("output_tokens", 0) or 0, tokens_estimated=not usage.get("reports"),
                duration_ms=duration, status="ERROR", error_code=err.code, source=usage_source,
            )
            if err is not exc:
                raise err from exc
            raise
    duration = int((time.perf_counter() - started) * 1000)
    reported = bool(usage.get("reports"))
    input_tokens = usage.get("input_tokens", 0) if reported else _estimate_tokens(system, prompt)
    output_text = data if isinstance(data, str) else str(data)
    output_tokens = usage.get("output_tokens", 0) if reported else _estimate_tokens(output_text)
    cost = record_usage(
        user_id=user_id, provider=target.provider, model=target.model, task=resolved.task, workflow=resolved.workflow,
        input_tokens=input_tokens, output_tokens=output_tokens, tokens_estimated=not reported,
        duration_ms=duration, status=status_on_success, source=usage_source,
    )
    info = CallInfo(
        task=resolved.task,
        workflow=resolved.workflow,
        provider=target.provider,
        model=target.model,
        source=resolved.source,
        duration_ms=duration,
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        tokens_estimated=not reported,
        estimated_cost_usd=float(cost) if cost is not None else None,
    )
    return data, info


def _call(
    kind: str,
    task: str,
    prompt: str,
    *,
    system: str | None,
    schema: Any = None,
    max_tokens: int,
    temperature: float = 0.2,
    prepared: Prepared | None = None,
) -> Any:
    if prepared is not None:
        resolved, primary_provider = prepared.resolved, prepared.provider
    else:
        resolved, primary_provider = resolve_current(task), None
    full_system = with_untrusted_rules(system)
    common = dict(prompt=prompt, system=full_system, schema=schema, max_tokens=max_tokens, temperature=temperature)
    try:
        data, info = _attempt(kind, resolved, resolved.target, primary_provider, status_on_success="OK", **common)
    except AIProviderError as err:
        fallback = resolved.fallback
        if fallback is None or err.code == BUDGET_EXCEEDED:
            raise
        logger.info(
            "AI %s failed on %s/%s (%s); trying the user's fallback %s/%s",
            task, resolved.provider, resolved.model, err.code, fallback.provider, fallback.model,
        )
        try:
            data, info = _attempt(kind, resolved, fallback, None, status_on_success="FALLBACK", **common)
        except AIProviderError as fallback_err:
            details = dict(err.details or {})
            details["fallback"] = {"provider": fallback.provider, "model": fallback.model, "error_code": fallback_err.code}
            err.details = details
            raise err from fallback_err
        info.fallback_used = True
        info.primary = {"provider": resolved.provider, "model": resolved.model}
        info.primary_error_code = err.code
    _last_call.set(info)
    return data


def complete_json(
    task: str,
    prompt: str,
    *,
    schema: dict[str, Any] | type[BaseModel] | None,
    system: str | None = None,
    max_tokens: int = 1500,
    prepared: Prepared | None = None,
) -> dict[str, Any]:
    """A JSON object from the model configured for ``task`` (validate it before use)."""
    return _call("json", task, prompt, system=system, schema=schema, max_tokens=max_tokens, prepared=prepared)


def complete(
    task: str,
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 800,
    temperature: float = 0.2,
    prepared: Prepared | None = None,
) -> str:
    """Plain text from the model configured for ``task``."""
    return _call("text", task, prompt, system=system, max_tokens=max_tokens, temperature=temperature, prepared=prepared)


def effective_target(task: str, *, user_id: uuid.UUID | None = None) -> dict[str, Any]:
    """``{provider, model, source, workflow, fallback}`` for ``task`` — no provider is built."""
    return resolve_current(task, user_id=user_id).as_dict()


def provider_is_mock(task: str | None = None) -> bool:
    """True when ``task`` resolves to the deterministic rules (no model would answer)."""
    try:
        return resolve_current(task or "general").provider == "mock"
    except Exception:  # noqa: BLE001
        return True


def model_available(task: str | None = None) -> bool:
    """True when a real model is configured for ``task`` for the current user.

    Builds (or reuses) the client, so a missing key reads as "not available"; it does not
    make a request, so an unreachable server still reads as available until a call fails.
    """
    try:
        prepared = prepare(task or "general")
    except Exception:  # noqa: BLE001
        return False
    provider = prepared.provider
    return not getattr(provider, "is_deterministic", False) and getattr(provider, "name", "mock") != "mock"


def model_info(task: str | None = None) -> tuple[str | None, str | None]:
    """``(provider, model)`` that ``task`` resolves to for the current user."""
    try:
        resolved = resolve_current(task or "general")
        return resolved.provider, resolved.model
    except Exception:  # noqa: BLE001
        return None, None


__all__ = [
    "CallInfo",
    "Prepared",
    "cached_client_keys",
    "check_limits",
    "clear_client_cache",
    "complete",
    "complete_json",
    "construct_provider",
    "effective_target",
    "evict_clients",
    "last_call",
    "model_available",
    "model_info",
    "prepare",
    "provider_is_mock",
    "provider_for",
    "record_usage",
    "resolve_current",
]
