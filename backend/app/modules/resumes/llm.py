"""The resume studio's door to the language model.

Every model call made by the builder goes through :func:`llm_json`, which hands it to the
AI runtime (``app.modules.ai.runtime``): the current user's provider and model for the task,
usage records, limits and the untrusted-content rules. Resume text is always fenced with
:func:`wrap_untrusted` before it reaches a prompt.
"""
from __future__ import annotations

import logging
from typing import Any

from app.modules.ai import runtime, safety

logger = logging.getLogger(__name__)

#: Task names the AI runtime maps to workflows (``app.modules.ai.routing``).
TASK_GENERATE_SECTION = "generate_resume_section"
TASK_REWRITE_BULLET = "rewrite_bullet"
TASK_IMPROVE_GRAMMAR = "improve_grammar"
TASK_DRAFT_SUMMARY = "draft_summary"


def untrusted_rules() -> str:
    return safety.UNTRUSTED_RULES


def wrap_untrusted(label: str, text: str, *, max_chars: int = 4000) -> str:
    """Fence ``text`` as data: control characters stripped, length capped, markers neutralised."""
    return safety.wrap_untrusted(label, text, max_chars=max_chars)


def provider_is_mock(task: str | None = None) -> bool:
    """True when ``task`` resolves to the deterministic mock for the current user (tests,
    no model configured): the rules answer alone and no prompt is sent."""
    return runtime.provider_is_mock(task)


def provider_label(task: str | None = None) -> str | None:
    """``"provider:model"`` that ``task`` resolves to for the current user, for the record."""
    provider, model = runtime.model_info(task)
    return ":".join(p for p in (provider, model) if p) or None


def llm_json(
    task: str,
    prompt: str,
    *,
    schema: dict[str, Any],
    system: str | None = None,
    max_tokens: int = 600,
) -> dict[str, Any]:
    """One JSON completion for ``task`` (raises on provider errors; callers own the fallback)."""
    return runtime.complete_json(task, prompt, schema=schema, system=system, max_tokens=max_tokens)


__all__ = [
    "TASK_DRAFT_SUMMARY",
    "TASK_GENERATE_SECTION",
    "TASK_IMPROVE_GRAMMAR",
    "TASK_REWRITE_BULLET",
    "llm_json",
    "provider_is_mock",
    "provider_label",
    "untrusted_rules",
    "wrap_untrusted",
]
