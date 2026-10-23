"""OpenAI chat-completions provider (official ``openai`` SDK), also used for
OpenAI-compatible servers (see ``providers/openai_compatible.py``).

Instantiated lazily, per user/model by ``app.modules.ai.runtime`` (with the user's own key)
or once by ``factory.get_llm_provider()`` (``LLM_PROVIDER=openai``, server key). The SDK is
imported inside ``__init__`` so the app boots without it.

* Reasoning models (``gpt-5*``, ``o*``) take ``max_completion_tokens`` and
  ``reasoning_effort`` and reject ``temperature``; the registry says which model is which,
  and an unknown ``gpt-5``/``o`` id is treated as a reasoning model.
* Every SDK error is mapped by ``ai.errors.map_exception``: callers see
  ``invalid_credentials`` / ``quota_exceeded`` / ``model_unavailable`` / … with an
  actionable message, never the raw provider body (which can echo part of the key).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.modules.ai.errors import PROVIDER_ERROR, PROVIDER_NOT_CONFIGURED, AIProviderError, map_exception, message_for
from app.modules.ai.provider import LLMProvider, extract_json, report_usage, schema_to_dict

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"
#: Hosted calls fail fast; one SDK retry covers a dropped connection.
MAX_RETRIES = 1
#: Reasoning tokens count against ``max_completion_tokens``; keep room for the answer.
REASONING_TOKEN_FLOOR = 4000

_REASONING_RE = re.compile(r"^(o\d|gpt-5)", re.IGNORECASE)
#: Model ids from ``GET /v1/models`` that are not chat models.
_NON_CHAT = ("embedding", "whisper", "tts", "dall-e", "davinci", "babbage", "audio", "realtime", "transcribe",
             "image", "moderation", "search", "computer-use", "codex")


def is_reasoning_model(model: str) -> bool:
    from app.modules.ai.registry import model_info

    entry = model_info("openai", model)
    if entry is not None:
        return entry.reasoning
    return bool(_REASONING_RE.match(model or ""))


class OpenAIProvider(LLMProvider):
    name = "openai"
    #: Ask for ``response_format=json_object`` (OpenAI itself; many compatible servers do not support it).
    supports_json_mode = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        base_url: str | None = None,
        require_key: bool = True,
    ) -> None:
        key = api_key or (settings.OPENAI_API_KEY if self.name == "openai" else None)
        if not key and require_key:
            raise AIProviderError(
                PROVIDER_NOT_CONFIGURED,
                message_for(PROVIDER_NOT_CONFIGURED, self.name),
                provider=self.name,
                model=model,
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise AIProviderError(
                PROVIDER_NOT_CONFIGURED, "The 'openai' package is not installed on the server.", provider=self.name
            ) from exc

        self.model = model or (settings.LLM_MODEL if settings.LLM_PROVIDER == self.name else None) or DEFAULT_MODEL
        self.base_url = base_url
        self._timeout = timeout if timeout is not None else float(settings.LLM_TIMEOUT_SECONDS)
        kwargs: dict[str, Any] = {"api_key": key or "not-needed", "timeout": self._timeout, "max_retries": MAX_RETRIES}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        logger.info("%s provider initialised (model=%s)", self.name, self.model)

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
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if self.name == "openai" and is_reasoning_model(self.model):
            kwargs["max_completion_tokens"] = max(int(max_tokens), REASONING_TOKEN_FLOOR)
            kwargs["reasoning_effort"] = "low"
        else:
            kwargs["max_tokens"] = int(max_tokens)
            kwargs["temperature"] = temperature
        if json_mode and self.supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - SDK raises many error types
            err = map_exception(self.name, exc, model=self.model)
            logger.warning("%s request failed: %s (%s)", self.name, err.code, type(exc).__name__)
            raise err from exc
        usage = getattr(response, "usage", None)
        if usage is not None:
            report_usage(getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None))
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise AIProviderError(PROVIDER_ERROR, f"{self._label} returned no answer. Retry in a moment.", provider=self.name, model=self.model)
        return (choices[0].message.content or "").strip()

    @property
    def _label(self) -> str:
        from app.modules.ai.errors import label

        return label(self.name)

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
        system_prompt = f"{system_prompt}\n\nReply with a single JSON object and nothing else.".strip()
        if schema_dict:
            system_prompt += f"\nIt must match this JSON schema:\n{json.dumps(schema_dict, ensure_ascii=False)}"
        raw = self._chat(prompt, system=system_prompt, max_tokens=max_tokens, temperature=0.0, json_mode=True)
        try:
            return extract_json(raw)
        except ValueError as exc:
            raise AIProviderError(
                PROVIDER_ERROR, f"{self._label} returned an answer that was not valid JSON. Retry, or pick another model.",
                provider=self.name, model=self.model,
            ) from exc

    # ------------------------------------------------------------------ discovery

    def list_models(self) -> list[dict[str, Any]] | None:
        try:
            page = self._client.models.list()
            items = list(getattr(page, "data", None) or page)
        except Exception as exc:  # noqa: BLE001
            raise map_exception(self.name, exc, model=self.model) from exc
        models: list[dict[str, Any]] = []
        for item in items:
            model_id = str(getattr(item, "id", "") or "")
            if not model_id:
                continue
            if self.name == "openai" and (any(tag in model_id for tag in _NON_CHAT) or not model_id.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-"))):
                continue
            models.append({"id": model_id})
        return models

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "configured": True}


__all__ = ["DEFAULT_MODEL", "OpenAIProvider", "is_reasoning_model"]
