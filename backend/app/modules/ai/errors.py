"""One error vocabulary for every AI provider (plan contract §4.3).

Every failure of a model call reaches callers as :class:`AIProviderError` — a subclass of
``ExternalServiceError``, so existing ``except ExternalServiceError`` blocks keep working —
with one of these ``code`` values:

=========================  ==========================================================
``provider_not_configured``  no key / server not reachable / provider disabled
``invalid_credentials``      the provider refused the key (401/403, "API key not valid")
``quota_exceeded``           the provider's rate limit, quota or credit balance (429/402)
``model_unavailable``        unknown model, not enabled for this key, not pulled (404)
``provider_timeout``         no answer in time
``budget_exceeded``          JobPilot's own daily call limit / monthly budget
``provider_error``           anything else (5xx, unusable response, network)
=========================  ==========================================================

Messages are written for the user and say what to do next. They never contain the API
key, a raw provider response body or the prompt: :func:`map_exception` classifies an SDK
exception by its type, status and (only for classification) its text, and then writes its
own message.
"""
from __future__ import annotations

from typing import Any

from app.core.exceptions import ExternalServiceError

PROVIDER_NOT_CONFIGURED = "provider_not_configured"
INVALID_CREDENTIALS = "invalid_credentials"
QUOTA_EXCEEDED = "quota_exceeded"
MODEL_UNAVAILABLE = "model_unavailable"
PROVIDER_TIMEOUT = "provider_timeout"
BUDGET_EXCEEDED = "budget_exceeded"
PROVIDER_ERROR = "provider_error"

ERROR_CODES: tuple[str, ...] = (
    PROVIDER_NOT_CONFIGURED,
    INVALID_CREDENTIALS,
    QUOTA_EXCEEDED,
    MODEL_UNAVAILABLE,
    PROVIDER_TIMEOUT,
    BUDGET_EXCEEDED,
    PROVIDER_ERROR,
)

_HTTP_STATUS: dict[str, int] = {
    PROVIDER_NOT_CONFIGURED: 409,
    INVALID_CREDENTIALS: 502,
    QUOTA_EXCEEDED: 429,
    MODEL_UNAVAILABLE: 502,
    PROVIDER_TIMEOUT: 504,
    BUDGET_EXCEEDED: 429,
    PROVIDER_ERROR: 502,
}

#: Worth retrying as is (the same request may succeed in a minute).
_RETRYABLE = {PROVIDER_TIMEOUT, PROVIDER_ERROR, QUOTA_EXCEEDED}

PROVIDER_LABELS: dict[str, str] = {
    "mock": "Built-in rules",
    "ollama": "Ollama",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "anthropic": "Anthropic",
    "openai_compatible": "OpenAI-compatible server",
}


def label(provider: str | None) -> str:
    return PROVIDER_LABELS.get(str(provider or ""), str(provider or "the AI provider"))


class AIProviderError(ExternalServiceError):
    """A model call failed. ``code`` is one of :data:`ERROR_CODES`."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        retryable: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        info: dict[str, Any] = {"provider": provider, "model": model}
        info["retryable"] = code in _RETRYABLE if retryable is None else retryable
        if details:
            info.update(details)
        super().__init__(message, code=code, details=info)
        self.status_code = _HTTP_STATUS.get(code, 502)
        self.provider = provider
        self.model = model

    @property
    def retryable(self) -> bool:
        return bool((self.details or {}).get("retryable"))


#: Codes the providers used before this module existed (Ollama still raises them; its
#: tests pin them) and what they mean in the shared vocabulary.
_LEGACY_CODES: dict[str, str] = {
    "llm_not_configured": PROVIDER_NOT_CONFIGURED,
    "llm_not_installed": PROVIDER_NOT_CONFIGURED,
    "llm_unavailable": PROVIDER_NOT_CONFIGURED,
    "llm_model_missing": MODEL_UNAVAILABLE,
    "llm_timeout": PROVIDER_TIMEOUT,
    "llm_bad_json": PROVIDER_ERROR,
    "llm_empty_response": PROVIDER_ERROR,
    "llm_request_failed": PROVIDER_ERROR,
    "llm_init_failed": PROVIDER_ERROR,
}


def _status_of(exc: BaseException) -> int | None:
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599:
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _text_of(exc: BaseException) -> str:
    """Lower-cased text used **only** to classify; never shown to anyone."""
    parts = [str(exc)]
    for attr in ("message", "status", "body"):
        value = getattr(exc, attr, None)
        if value is not None and not isinstance(value, int):
            parts.append(str(value))
    return " ".join(parts).lower()


def message_for(code: str, provider: str | None, model: str | None = None, *, hint: str | None = None) -> str:
    name = label(provider)
    what = f"model {model!r}" if model else "the selected model"
    messages = {
        PROVIDER_NOT_CONFIGURED: f"{name} is not set up yet. Add an API key (or start the local server) in AI Model Settings.",
        INVALID_CREDENTIALS: (
            f"{name} rejected the API key. Check that it is correct and active, or rotate it in AI Model Settings. "
            "A ChatGPT, Gemini or Claude subscription does not include API access — the key must come from the "
            "provider's API console."
        ),
        QUOTA_EXCEEDED: (
            f"{name} refused the request because a rate limit, quota or credit balance was reached. Wait a minute and "
            "retry, or check billing in the provider's console (API billing is separate from chat subscriptions)."
        ),
        MODEL_UNAVAILABLE: f"{name} cannot use {what}: it does not exist or this key has no access to it. Pick another model.",
        PROVIDER_TIMEOUT: f"{name} did not answer in time. Retry, or choose a faster model.",
        BUDGET_EXCEEDED: "Your AI usage limit was reached. Raise the daily call limit or the monthly budget in AI Model Settings.",
        PROVIDER_ERROR: f"{name} failed to answer. Retry in a moment, or choose another model.",
    }
    text = messages.get(code, messages[PROVIDER_ERROR])
    return f"{text} {hint}".strip() if hint else text


def map_exception(provider: str | None, exc: BaseException, *, model: str | None = None) -> AIProviderError:
    """Classify any SDK / HTTP / legacy exception into an :class:`AIProviderError`."""
    if isinstance(exc, AIProviderError):
        return exc
    if isinstance(exc, ExternalServiceError) and exc.code in _LEGACY_CODES:
        code = _LEGACY_CODES[exc.code]
        # Ollama's own messages are local and actionable ("run: ollama pull …") and carry
        # no secret; keep them.
        if provider == "ollama":
            return AIProviderError(code, exc.message, provider=provider, model=model)
        return AIProviderError(code, message_for(code, provider, model), provider=provider, model=model)
    if isinstance(exc, ExternalServiceError) and exc.code in ERROR_CODES:
        return AIProviderError(exc.code, message_for(exc.code, provider, model), provider=provider, model=model)

    name = type(exc).__name__.lower()
    status = _status_of(exc)
    text = _text_of(exc)

    if "timeout" in name or "timedout" in name or status in (408, 504) or ("deadline" in text and status is None):
        code = PROVIDER_TIMEOUT
    elif status is None and ("connect" in name or "connection" in name or "network" in name):
        return AIProviderError(
            PROVIDER_ERROR,
            f"Could not reach {label(provider)}. Check the network or the server address, then retry.",
            provider=provider,
            model=model,
            retryable=True,
        )
    elif status in (401, 403) or "authentication" in name or "permissiondenied" in name:
        code = INVALID_CREDENTIALS
    elif status == 402:
        code = QUOTA_EXCEEDED
    elif status == 404 or "notfound" in name:
        code = MODEL_UNAVAILABLE
    elif status == 429 or "ratelimit" in name or "resource_exhausted" in text:
        code = QUOTA_EXCEEDED
    elif status == 400 or "badrequest" in name or status == 422:
        if "api key" in text or "api_key" in text or "x-api-key" in text:
            code = INVALID_CREDENTIALS
        elif "credit balance" in text or "billing" in text or "quota" in text:
            code = QUOTA_EXCEEDED
        elif "model" in text and ("not found" in text or "does not exist" in text or "invalid" in text or "unknown" in text or "not supported" in text):
            code = MODEL_UNAVAILABLE
        else:
            code = PROVIDER_ERROR
    else:
        code = PROVIDER_ERROR
    return AIProviderError(code, message_for(code, provider, model), provider=provider, model=model)


__all__ = [
    "AIProviderError",
    "BUDGET_EXCEEDED",
    "ERROR_CODES",
    "INVALID_CREDENTIALS",
    "MODEL_UNAVAILABLE",
    "PROVIDER_ERROR",
    "PROVIDER_LABELS",
    "PROVIDER_NOT_CONFIGURED",
    "PROVIDER_TIMEOUT",
    "QUOTA_EXCEEDED",
    "label",
    "map_exception",
    "message_for",
]
