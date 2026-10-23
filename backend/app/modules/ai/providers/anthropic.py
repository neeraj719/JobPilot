"""Anthropic Messages-API provider (official ``anthropic`` SDK).

Instantiated lazily, per user/model by ``app.modules.ai.runtime`` (the user's own key) or
once by ``factory.get_llm_provider()`` (``LLM_PROVIDER=anthropic``, server key).

* ``complete_json`` asks for JSON in the system prompt and strips fences/prose around the
  object (``extract_json``).
* Current Claude models reject ``temperature`` and think by default; the model registry
  says which accept sampling and which take ``output_config.effort`` — JobPilot's tasks
  are short, so ``effort: low`` keeps them fast and cheap, and ``max_tokens`` gets a floor
  so thinking cannot use up the whole answer budget. Unknown (newer) models are treated
  like the current ones: no ``temperature``.
* SDK errors are mapped by ``ai.errors.map_exception`` (no raw bodies reach the user).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.modules.ai.errors import PROVIDER_ERROR, PROVIDER_NOT_CONFIGURED, AIProviderError, map_exception, message_for
from app.modules.ai.provider import LLMProvider, extract_json, report_usage, schema_to_dict

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_RETRIES = 1
THINKING_TOKEN_FLOOR = 4000


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, *, api_key: str | None = None, model: str | None = None, timeout: float | None = None) -> None:
        key = api_key or settings.ANTHROPIC_API_KEY
        if not key:
            raise AIProviderError(
                PROVIDER_NOT_CONFIGURED, message_for(PROVIDER_NOT_CONFIGURED, self.name), provider=self.name, model=model
            )
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise AIProviderError(
                PROVIDER_NOT_CONFIGURED, "The 'anthropic' package is not installed on the server.", provider=self.name
            ) from exc

        self.model = model or (settings.LLM_MODEL if settings.LLM_PROVIDER == "anthropic" else None) or DEFAULT_MODEL
        self._timeout = timeout if timeout is not None else float(settings.LLM_TIMEOUT_SECONDS)
        self._client = Anthropic(api_key=key, timeout=self._timeout, max_retries=MAX_RETRIES)
        logger.info("Anthropic provider initialised (model=%s)", self.model)

    # ------------------------------------------------------------------

    def _request_options(self, max_tokens: int, temperature: float) -> dict[str, Any]:
        from app.modules.ai.registry import model_info

        entry = model_info("anthropic", self.model)
        options: dict[str, Any] = {"max_tokens": int(max_tokens)}
        sampling = entry.sampling if entry is not None else False
        if sampling:
            options["temperature"] = temperature
        thinks = entry.thinks_by_default if entry is not None else True
        if thinks:
            options["max_tokens"] = max(int(max_tokens), THINKING_TOKEN_FLOOR)
        if entry is None or entry.effort:
            # ``output_config`` is newer than the pinned SDK's typed parameters.
            options["extra_body"] = {"output_config": {"effort": "low"}}
        return options

    def _message(self, prompt: str, *, system: str | None, max_tokens: int, temperature: float) -> str:
        kwargs: dict[str, Any] = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        kwargs.update(self._request_options(max_tokens, temperature))
        if system:
            kwargs["system"] = system
        try:
            response = self._client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - SDK raises many error types
            err = map_exception(self.name, exc, model=self.model)
            logger.warning("Anthropic request failed: %s (%s)", err.code, type(exc).__name__)
            raise err from exc

        usage = getattr(response, "usage", None)
        if usage is not None:
            report_usage(getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
        if getattr(response, "stop_reason", None) == "refusal":
            raise AIProviderError(
                PROVIDER_ERROR, "Claude declined this request. Retry, or choose another model.", provider=self.name, model=self.model
            )
        blocks = getattr(response, "content", None) or []
        text = "".join(getattr(block, "text", "") for block in blocks if getattr(block, "type", "") == "text")
        if not text.strip():
            raise AIProviderError(PROVIDER_ERROR, "Claude returned an empty answer. Retry in a moment.", provider=self.name, model=self.model)
        return text.strip()

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> str:
        return self._message(prompt, system=system, max_tokens=max_tokens, temperature=temperature)

    def complete_json(
        self,
        prompt: str,
        *,
        schema: dict[str, Any] | type[BaseModel] | None = None,
        system: str | None = None,
        max_tokens: int = 1500,
    ) -> dict[str, Any]:
        schema_dict = schema_to_dict(schema)
        system_prompt = system or ""
        system_prompt = (
            f"{system_prompt}\n\nReply with a single JSON object and nothing else — no prose, no markdown fences."
        ).strip()
        if schema_dict:
            system_prompt += f"\nIt must match this JSON schema:\n{json.dumps(schema_dict, ensure_ascii=False)}"
        raw = self._message(prompt, system=system_prompt, max_tokens=max_tokens, temperature=0.0)
        try:
            return extract_json(raw)
        except ValueError as exc:
            raise AIProviderError(
                PROVIDER_ERROR, "Claude returned an answer that was not valid JSON. Retry, or pick another model.",
                provider=self.name, model=self.model,
            ) from exc

    # ------------------------------------------------------------------ discovery

    def list_models(self) -> list[dict[str, Any]] | None:
        try:
            items = list(self._client.models.list(limit=100))
        except Exception as exc:  # noqa: BLE001
            raise map_exception(self.name, exc, model=self.model) from exc
        models = []
        for item in items:
            model_id = str(getattr(item, "id", "") or "")
            if model_id:
                models.append({
                    "id": model_id,
                    "display_name": getattr(item, "display_name", None),
                    "context_window": getattr(item, "max_input_tokens", None),
                })
        return models

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "configured": True}


__all__ = ["AnthropicProvider", "DEFAULT_MODEL"]
