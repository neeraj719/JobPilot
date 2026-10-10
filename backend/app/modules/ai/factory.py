"""Provider selection (CONTRACTS.md §6).

``get_llm_provider()`` is cached for the process; ``reset_llm_provider()`` clears the
cache so tests (and a settings change) can switch providers. Real providers are only
constructed here — importing this module never touches an SDK or an API key.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.modules.ai.provider import LLMProvider
from app.modules.ai.providers.mock import MockLLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODELS: dict[str, str] = {
    "mock": MockLLMProvider.model,
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5",
    "ollama": "qwen2.5:3b-instruct",
}

_provider: LLMProvider | None = None
_lock = threading.Lock()


def _build_provider(name: str) -> LLMProvider:
    key = (name or "mock").strip().lower()
    if key == "openai":
        from app.modules.ai.providers.openai import OpenAIProvider

        return OpenAIProvider()
    if key == "anthropic":
        from app.modules.ai.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    if key == "ollama":
        from app.modules.ai.providers.ollama import OllamaProvider

        return OllamaProvider()
    if key != "mock":
        logger.warning("Unknown LLM_PROVIDER %r; falling back to the mock provider", name)
    return MockLLMProvider()


def get_llm_provider() -> LLMProvider:
    """Return the process-wide provider selected by ``settings.LLM_PROVIDER``."""
    global _provider
    if _provider is not None:
        return _provider
    with _lock:
        if _provider is None:
            _provider = _build_provider(settings.LLM_PROVIDER)
            logger.info("LLM provider ready: %s (%s)", _provider.name, _provider.model)
        return _provider


def reset_llm_provider() -> None:
    """Drop the cached provider (tests, or after changing settings at runtime)."""
    global _provider
    with _lock:
        _provider = None


def get_mock_provider() -> MockLLMProvider:
    """The deterministic provider, regardless of configuration (fallback path)."""
    provider = _provider
    if isinstance(provider, MockLLMProvider):
        return provider
    return MockLLMProvider()


def api_key_for(name: str) -> str | None:
    return {"openai": settings.OPENAI_API_KEY, "anthropic": settings.ANTHROPIC_API_KEY}.get(name.lower())


def provider_status() -> dict[str, Any]:
    """``{provider, model, configured}`` without constructing a real client.

    For ``ollama`` "configured" means the local server answers and the model is pulled
    (a short HTTP probe, no API key involved); the probe's details are added too.
    """
    name = (settings.LLM_PROVIDER or "mock").strip().lower()
    if name == "mock":
        # The mock has one fixed "model"; LLM_MODEL is meant for the real providers.
        return {"provider": name, "model": MockLLMProvider.model, "configured": True}
    model = settings.LLM_MODEL or DEFAULT_MODELS.get(name)
    if name == "ollama":
        from app.modules.ai.providers import ollama

        probe = ollama.check_server(settings.OLLAMA_BASE_URL.rstrip("/"), model or ollama.DEFAULT_MODEL)
        return {
            "provider": name,
            "model": model,
            "configured": bool(probe["reachable"] and probe["model_pulled"]),
            "base_url": probe["base_url"],
            "model_pulled": probe["model_pulled"],
            "version": probe["version"],
            "error": probe["error"],
        }
    return {"provider": name, "model": model, "configured": bool(api_key_for(name))}


def check_provider() -> LLMProvider:
    """Eagerly build the configured provider, raising ``ExternalServiceError`` if it
    cannot be used. Handy for a startup/health check."""
    try:
        return get_llm_provider()
    except ExternalServiceError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise ExternalServiceError(f"Could not initialise the LLM provider: {exc}", code="llm_init_failed") from exc


__all__ = [
    "DEFAULT_MODELS",
    "check_provider",
    "get_llm_provider",
    "get_mock_provider",
    "provider_status",
    "reset_llm_provider",
]
