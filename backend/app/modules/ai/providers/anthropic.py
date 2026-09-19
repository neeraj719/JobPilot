"""Anthropic messages-API provider.

Instantiated lazily (only when ``LLM_PROVIDER=anthropic``). The messages API has no
JSON mode, so ``complete_json`` asks for JSON in the system prompt and then strips
code fences / prose around the object before decoding it.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.modules.ai.provider import LLMProvider, extract_json, schema_to_dict

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-5"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, *, api_key: str | None = None, model: str | None = None, timeout: float | None = None) -> None:
        key = api_key or settings.ANTHROPIC_API_KEY
        if not key:
            raise ExternalServiceError(
                "ANTHROPIC_API_KEY is not configured; set it or switch LLM_PROVIDER to 'mock'.",
                code="llm_not_configured",
            )
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise ExternalServiceError("The 'anthropic' package is not installed", code="llm_not_installed") from exc

        self.model = model or settings.LLM_MODEL or DEFAULT_MODEL
        self._timeout = timeout if timeout is not None else float(settings.LLM_TIMEOUT_SECONDS)
        self._client = Anthropic(api_key=key, timeout=self._timeout)
        logger.info("Anthropic provider initialised (model=%s)", self.model)

    # ------------------------------------------------------------------

    def _message(self, prompt: str, *, system: str | None, max_tokens: int, temperature: float) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        try:
            response = self._client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - SDK raises many error types
            logger.warning("Anthropic request failed: %s", exc)
            raise ExternalServiceError(f"Anthropic request failed: {exc}", code="llm_request_failed") from exc

        blocks = getattr(response, "content", None) or []
        text = "".join(getattr(block, "text", "") for block in blocks if getattr(block, "type", "") == "text")
        if not text.strip():
            raise ExternalServiceError("Anthropic returned an empty response", code="llm_empty_response")
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
            raise ExternalServiceError(f"Anthropic returned unusable JSON: {exc}", code="llm_bad_json") from exc


__all__ = ["AnthropicProvider", "DEFAULT_MODEL"]
