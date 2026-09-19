"""OpenAI chat-completions provider.

Instantiated lazily (only when ``LLM_PROVIDER=openai``) so the app boots — and the
whole test suite runs — without the ``openai`` package being configured.
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

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, *, api_key: str | None = None, model: str | None = None, timeout: float | None = None) -> None:
        key = api_key or settings.OPENAI_API_KEY
        if not key:
            raise ExternalServiceError(
                "OPENAI_API_KEY is not configured; set it or switch LLM_PROVIDER to 'mock'.",
                code="llm_not_configured",
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise ExternalServiceError("The 'openai' package is not installed", code="llm_not_installed") from exc

        self.model = model or settings.LLM_MODEL or DEFAULT_MODEL
        self._timeout = timeout if timeout is not None else float(settings.LLM_TIMEOUT_SECONDS)
        self._client = OpenAI(api_key=key, timeout=self._timeout)
        logger.info("OpenAI provider initialised (model=%s)", self.model)

    # ------------------------------------------------------------------

    def _chat(
        self,
        prompt: str,
        *,
        system: str | None,
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - SDK raises many error types
            logger.warning("OpenAI request failed: %s", exc)
            raise ExternalServiceError(f"OpenAI request failed: {exc}", code="llm_request_failed") from exc
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ExternalServiceError("OpenAI returned no choices", code="llm_empty_response")
        return (choices[0].message.content or "").strip()

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> str:
        return self._chat(prompt, system=system, max_tokens=max_tokens, temperature=temperature, json_mode=False)

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
        if schema_dict:
            system_prompt = (
                f"{system_prompt}\n\nRespond with a single JSON object matching this JSON schema:\n"
                f"{json.dumps(schema_dict, ensure_ascii=False)}"
            ).strip()
        raw = self._chat(prompt, system=system_prompt or None, max_tokens=max_tokens, temperature=0.0, json_mode=True)
        try:
            return extract_json(raw)
        except ValueError as exc:
            raise ExternalServiceError(f"OpenAI returned unusable JSON: {exc}", code="llm_bad_json") from exc


__all__ = ["DEFAULT_MODEL", "OpenAIProvider"]
