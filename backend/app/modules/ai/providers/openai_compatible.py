"""Self-hosted / third-party servers that speak the OpenAI chat-completions API.

vLLM, LM Studio, llama.cpp's server, LocalAI, OpenRouter… all accept the official
``openai`` SDK pointed at their ``base_url``. Differences handled here:

* the key is optional (local servers ignore it);
* ``response_format={"type": "json_object"}`` is not universally supported, so JSON is
  requested in the system prompt and parsed with ``extract_json`` instead;
* ``GET /models`` is optional: when it fails the model list falls back to what the user
  typed, and the connection test makes one tiny completion instead.

The base URL is validated by ``app.modules.ai.base_url.validate_base_url`` before it is
stored and again by the runtime before this class is built. It is never used as an
automatic fallback: only the user can select it.
"""
from __future__ import annotations

from typing import Any

from app.core.exceptions import AppError
from app.modules.ai.errors import PROVIDER_NOT_CONFIGURED, AIProviderError
from app.modules.ai.providers.openai import OpenAIProvider


class OpenAICompatibleProvider(OpenAIProvider):
    name = "openai_compatible"
    supports_json_mode = False

    def __init__(self, *, base_url: str | None, api_key: str | None = None, model: str | None = None, timeout: float | None = None) -> None:
        if not base_url:
            raise AIProviderError(
                PROVIDER_NOT_CONFIGURED,
                "Set the server's base URL for the OpenAI-compatible provider in AI Model Settings.",
                provider=self.name,
            )
        if not model:
            raise AIProviderError(
                PROVIDER_NOT_CONFIGURED, "Choose which model the OpenAI-compatible server should run.", provider=self.name
            )
        super().__init__(api_key=api_key, model=model, timeout=timeout, base_url=base_url, require_key=False)

    def list_models(self) -> list[dict[str, Any]] | None:
        try:
            return super().list_models()
        except AppError:
            return None  # many servers have no /models: test with a completion instead


__all__ = ["OpenAICompatibleProvider"]
