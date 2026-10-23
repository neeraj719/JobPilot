"""LLM provider abstraction (CONTRACTS.md §6).

Every provider implements the same two primitives:

* ``complete``       — free text in, free text out.
* ``complete_json``  — free text in, a JSON object out (validated by the caller).

Deterministic providers (the mock) additionally implement ``supports_task`` /
``run_task`` so ``ai.tasks`` can short-circuit prompt building entirely and return
rule-based output. Real providers leave ``supports_task`` returning ``False``.

``get_llm_provider`` / ``reset_llm_provider`` live in ``ai.factory``; they are
re-exported lazily here (PEP 562) so both import paths work without a cycle.
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class LLMProvider(ABC):
    """Base class for every language-model backend."""

    name: str = "base"
    model: str = ""
    is_deterministic: bool = False

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> str:
        """Return the model's plain-text completion."""

    @abstractmethod
    def complete_json(
        self,
        prompt: str,
        *,
        schema: dict[str, Any] | type[BaseModel],
        system: str | None = None,
        max_tokens: int = 1500,
    ) -> dict[str, Any]:
        """Return a JSON object shaped like ``schema``."""

    # -- deterministic short-circuit ---------------------------------------

    def supports_task(self, task_name: str) -> bool:
        """True when the provider can answer ``task_name`` without a model call."""
        return False

    def run_task(self, task_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Deterministic implementation of ``task_name``. Only called when
        :meth:`supports_task` returned True."""
        raise NotImplementedError(f"{self.name} provider cannot run task {task_name!r}")

    # -- discovery / health (AI Model Settings) -----------------------------

    def list_models(self) -> list[dict[str, Any]] | None:
        """Models this key/server can use, live from the provider: ``[{"id", "display_name"?,
        "context_window"?}]``. ``None`` when the provider has no listing endpoint."""
        return None

    def test_connection(self) -> dict[str, Any]:
        """One cheap call proving the key and the model work.

        Returns ``{"ok", "latency_ms", "model", "model_available", "error_code", "error"}`` and
        never raises. The default lists the models (free on every hosted API) and checks the
        chosen one is among them; without a listing it makes one tiny completion.
        """
        import time

        from app.modules.ai.errors import map_exception

        started = time.perf_counter()
        result: dict[str, Any] = {"ok": False, "latency_ms": None, "model": self.model or None,
                                  "model_available": None, "error_code": None, "error": None}
        try:
            models = self.list_models()
            if models is None:
                self.complete("Reply with the single word: ok", max_tokens=16, temperature=0.0)
                result["model_available"] = True
            else:
                ids = {str(m.get("id")) for m in models}
                result["model_available"] = (not self.model) or self.model in ids
            result["ok"] = True
        except Exception as exc:  # noqa: BLE001 - reported, never raised
            err = map_exception(self.name, exc, model=self.model)
            result["error_code"], result["error"] = err.code, err.message
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        if result["ok"] and result["model_available"] is False:
            result["error_code"] = "model_unavailable"
            result["error"] = f"The key works, but model {self.model!r} is not available to it. Pick another model."
        return result

    # -- introspection ------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        return True

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model or None, "configured": self.is_configured}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} model={self.model!r}>"


# --------------------------------------------------------------------------- usage capture
#
# Providers are cached and shared between threads, so per-call token counts cannot live on
# ``self``. A provider reports what the SDK returned with :func:`report_usage`; the runtime
# reads it back inside :func:`usage_capture`. ContextVars are per thread / per task, and the
# provider call runs in the runtime's own thread, so concurrent calls never mix.

_usage: ContextVar[dict[str, int] | None] = ContextVar("jobpilot_llm_usage", default=None)


def report_usage(input_tokens: int | None, output_tokens: int | None) -> None:
    """Add one SDK response's token counts to the current capture (no-op outside one)."""
    bucket = _usage.get()
    if bucket is None:
        return
    if isinstance(input_tokens, int):
        bucket["input_tokens"] = bucket.get("input_tokens", 0) + max(0, input_tokens)
    if isinstance(output_tokens, int):
        bucket["output_tokens"] = bucket.get("output_tokens", 0) + max(0, output_tokens)
    bucket["reports"] = bucket.get("reports", 0) + 1


@contextmanager
def usage_capture() -> Iterator[dict[str, int]]:
    bucket: dict[str, int] = {}
    token = _usage.set(bucket)
    try:
        yield bucket
    finally:
        _usage.reset(token)


# --------------------------------------------------------------------------- helpers


def schema_to_dict(schema: dict[str, Any] | type[BaseModel] | None) -> dict[str, Any]:
    """Normalise a pydantic model or raw mapping into a JSON schema dict."""
    if schema is None:
        return {}
    if isinstance(schema, dict):
        return schema
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema.model_json_schema()
    return {}


def strip_code_fences(text: str) -> str:
    """Remove ```json ...``` fences that chat models like to wrap JSON in."""
    if not text:
        return ""
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def extract_json(text: str) -> dict[str, Any]:
    """Best-effort extraction of the first JSON object in ``text``.

    Raises ``ValueError`` when nothing parseable is present — callers decide what
    to do (``ai.tasks`` falls back to the deterministic implementation).
    """
    candidate = strip_code_fences(text)
    if not candidate:
        raise ValueError("Empty model response")
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("No JSON object found in model response") from None
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Could not decode JSON from model response: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Model response was not a JSON object")
    return parsed


def __getattr__(name: str) -> Any:  # PEP 562 — lazy re-export, avoids an import cycle
    if name in {"get_llm_provider", "reset_llm_provider", "provider_status"}:
        from app.modules.ai import factory

        return getattr(factory, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "LLMProvider",
    "extract_json",
    "get_llm_provider",
    "provider_status",
    "report_usage",
    "reset_llm_provider",
    "schema_to_dict",
    "strip_code_fences",
    "usage_capture",
]
