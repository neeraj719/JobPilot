"""Google Gemini provider (official ``google-genai`` SDK, pinned in requirements.txt).

The SDK is imported inside ``__init__``: the owner's dev server runs under an interpreter
that may not have it, and the app must keep booting there. A missing package is reported as
``provider_not_configured`` with the install hint.

* ``complete_json`` uses Gemini's JSON mode: ``response_mime_type="application/json"`` plus
  ``response_json_schema`` (full JSON Schema, so pydantic's ``$defs``/``anyOf`` are fine).
  The reply is still parsed and validated by the caller.
* Thinking: Flash models can switch it off (``thinking_budget=0``), which keeps JobPilot's
  short tasks fast and cheap; models that always think get a ``max_output_tokens`` floor.
* Timeouts go through ``HttpOptions(timeout=<ms>)``; errors (``google.genai.errors.APIError``
  with ``.code``) are mapped by ``ai.errors.map_exception``.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.modules.ai.errors import PROVIDER_ERROR, PROVIDER_NOT_CONFIGURED, AIProviderError, map_exception, message_for
from app.modules.ai.provider import LLMProvider, extract_json, report_usage, schema_to_dict

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
THINKING_TOKEN_FLOOR = 4000


def _load_sdk() -> tuple[Any, Any]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise AIProviderError(
            PROVIDER_NOT_CONFIGURED,
            "The Gemini SDK is not installed on the server (pip install google-genai==1.55.0).",
            provider="gemini",
        ) from exc
    return genai, types


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: Any | None = None,
    ) -> None:
        key = api_key or settings.GOOGLE_API_KEY
        if not key and client is None:
            raise AIProviderError(
                PROVIDER_NOT_CONFIGURED, message_for(PROVIDER_NOT_CONFIGURED, self.name), provider=self.name, model=model
            )
        genai, types = _load_sdk()
        self._types = types
        self.model = model or (settings.LLM_MODEL if settings.LLM_PROVIDER == "gemini" else None) or DEFAULT_MODEL
        self._timeout = timeout if timeout is not None else float(settings.LLM_TIMEOUT_SECONDS)
        if client is not None:  # tests inject a fake client
            self._client = client
        else:
            self._client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(self._timeout * 1000)))
        logger.info("Gemini provider initialised (model=%s)", self.model)

    # ------------------------------------------------------------------

    def _config(self, *, system: str | None, max_tokens: int, temperature: float, schema: dict[str, Any] | None, json_mode: bool) -> Any:
        from app.modules.ai.registry import model_info

        entry = model_info("gemini", self.model)
        kwargs: dict[str, Any] = {"max_output_tokens": int(max_tokens), "temperature": temperature}
        if system:
            kwargs["system_instruction"] = system
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
            if schema:
                kwargs["response_json_schema"] = schema
        if entry is not None and entry.thinking_off:
            kwargs["thinking_config"] = self._types.ThinkingConfig(thinking_budget=0)
        elif entry is None or entry.thinks_by_default:
            kwargs["max_output_tokens"] = max(int(max_tokens), THINKING_TOKEN_FLOOR)
        return self._types.GenerateContentConfig(**kwargs)

    def _generate(self, prompt: str, config: Any) -> str:
        try:
            response = self._client.models.generate_content(model=self.model, contents=prompt, config=config)
        except AIProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - SDK / httpx errors
            err = map_exception(self.name, exc, model=self.model)
            logger.warning("Gemini request failed: %s (%s)", err.code, type(exc).__name__)
            raise err from exc
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            output = (getattr(meta, "candidates_token_count", None) or 0) + (getattr(meta, "thoughts_token_count", None) or 0)
            report_usage(getattr(meta, "prompt_token_count", None), output or None)
        try:
            text = response.text
        except Exception:  # noqa: BLE001 - .text raises when the candidate was blocked
            text = None
        if not text or not str(text).strip():
            feedback = getattr(response, "prompt_feedback", None)
            reason = getattr(feedback, "block_reason", None) if feedback is not None else None
            hint = " The request was blocked by Gemini's safety filters." if reason else ""
            raise AIProviderError(
                PROVIDER_ERROR, f"Gemini returned an empty answer.{hint} Retry, or choose another model.",
                provider=self.name, model=self.model,
            )
        return str(text).strip()

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> str:
        config = self._config(system=system, max_tokens=max_tokens, temperature=temperature, schema=None, json_mode=False)
        return self._generate(prompt, config)

    def complete_json(
        self,
        prompt: str,
        *,
        schema: dict[str, Any] | type[BaseModel] | None = None,
        system: str | None = None,
        max_tokens: int = 1500,
    ) -> dict[str, Any]:
        schema_dict = schema_to_dict(schema) or None
        config = self._config(system=system, max_tokens=max_tokens, temperature=0.0, schema=schema_dict, json_mode=True)
        raw = self._generate(prompt, config)
        try:
            return extract_json(raw)
        except ValueError as exc:
            raise AIProviderError(
                PROVIDER_ERROR, "Gemini returned an answer that was not valid JSON. Retry, or pick another model.",
                provider=self.name, model=self.model,
            ) from exc

    # ------------------------------------------------------------------ discovery

    def list_models(self) -> list[dict[str, Any]] | None:
        try:
            items = list(self._client.models.list())
        except Exception as exc:  # noqa: BLE001
            raise map_exception(self.name, exc, model=self.model) from exc
        models: list[dict[str, Any]] = []
        for item in items:
            name = str(getattr(item, "name", "") or "")
            actions = getattr(item, "supported_actions", None) or []
            if not name or (actions and "generateContent" not in actions):
                continue
            model_id = name.split("/", 1)[1] if name.startswith("models/") else name
            if any(tag in model_id for tag in ("embedding", "aqa", "imagen", "veo", "tts", "image")):
                continue
            models.append({
                "id": model_id,
                "display_name": getattr(item, "display_name", None),
                "context_window": getattr(item, "input_token_limit", None),
            })
        return models

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "configured": True}


__all__ = ["DEFAULT_MODEL", "GeminiProvider"]
