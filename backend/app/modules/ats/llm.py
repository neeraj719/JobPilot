"""The ATS module's only door to a language model, plus the untrusted-text fence.

Model calls go to the AI runtime (``app.modules.ai.runtime``), which resolves the current
user's provider and model for the task, records usage, enforces limits and prepends the
untrusted-content rules. Background threads publish the acting user with :func:`ai_user`.

Rules every caller follows:

* job-description and resume text always goes through :func:`wrap_untrusted` and the system
  prompt always starts with :data:`UNTRUSTED_RULES` - text between the markers is data;
* the model never gets tools, and its output is validated (schema + deterministic guards)
  before anything reaches a resume;
* the deterministic path never depends on this module: :func:`model_available` is ``False``
  for the mock provider, and every caller has a rule-based answer already.
"""
from __future__ import annotations

import contextlib
import logging
import uuid
from typing import Any, Iterator

from app.modules.ai import context, runtime, safety

logger = logging.getLogger(__name__)

#: Task names the AI runtime maps to workflows (``app.modules.ai.routing``).
TASK_ANALYZE_JD = "analyze_job_description"
TASK_ANALYZE_FIT = "analyze_resume_fit"
TASK_TAILOR = "tailor_resume"
TASK_REVIEW = "review_resume"
TASK_EXPLAIN = "explain_changes"


# --------------------------------------------------------------------------- untrusted text


def untrusted_rules() -> str:
    return safety.UNTRUSTED_RULES


def wrap_untrusted(label: str, text: str, *, max_chars: int = 6000) -> str:
    return safety.wrap_untrusted(label, text, max_chars=max_chars)


def system_prompt(task_rules: str) -> str:
    return safety.with_untrusted_rules(task_rules)


# --------------------------------------------------------------------------- user context


@contextlib.contextmanager
def ai_user(user_id: uuid.UUID | None) -> Iterator[None]:
    """Publish the acting user for provider resolution in a background thread."""
    if user_id is None:
        yield
        return
    with context.ai_user(user_id):
        yield


# --------------------------------------------------------------------------- model calls


def model_available(task: str | None = None) -> bool:
    """True when a real model would answer ``task`` for the current user (never for the mock)."""
    return runtime.model_available(task)


def model_info(task: str | None = None) -> tuple[str | None, str | None]:
    """``(provider, model)`` names for the record; ``(None, None)`` when unknown."""
    return runtime.model_info(task)


def llm_json(task: str, prompt: str, *, schema: dict[str, Any], system: str | None = None, max_tokens: int = 1500) -> dict[str, Any]:
    """One JSON completion for ``task``; raises on provider errors (callers keep the rule result)."""
    return runtime.complete_json(task, prompt, schema=schema, system=system, max_tokens=max_tokens)


__all__ = [
    "TASK_ANALYZE_FIT",
    "TASK_ANALYZE_JD",
    "TASK_EXPLAIN",
    "TASK_REVIEW",
    "TASK_TAILOR",
    "ai_user",
    "llm_json",
    "model_available",
    "model_info",
    "system_prompt",
    "untrusted_rules",
    "wrap_untrusted",
]
