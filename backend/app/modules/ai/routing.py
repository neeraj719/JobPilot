"""Which provider and model answer a task (spec §8).

Task names (strings, chosen by the calling module) map to a handful of *workflows*; the user
picks a model per workflow in AI Model Settings. Resolution order, first match wins:

1. ``task_override``  — the user's model for the task's workflow (``workflow_models``);
2. ``user_default``   — the user's default provider/model;
3. ``server_default`` — ``settings.LLM_PROVIDER`` / ``LLM_MODEL`` (the free local Ollama in
   the owner's setup, the deterministic mock in tests).

The fallback is only part of the answer when the user turned it on, and it is never the
same target as the primary. Nothing here calls a provider or decrypts a key.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.ai import registry

logger = logging.getLogger(__name__)


class AiWorkflow(StrEnum):
    GENERATION = "generation"
    ANALYSIS = "analysis"
    REWRITING = "rewriting"
    JD_ANALYSIS = "jd_analysis"
    REVIEW = "review"
    GENERAL = "general"


#: Workflows a user can route separately, in display order, with their UI labels.
CONFIGURABLE_WORKFLOWS: dict[str, str] = {
    AiWorkflow.GENERATION.value: "Resume generation",
    AiWorkflow.ANALYSIS.value: "ATS analysis",
    AiWorkflow.REWRITING.value: "Bullet rewriting",
    AiWorkflow.JD_ANALYSIS.value: "Job-description analysis",
    AiWorkflow.REVIEW.value: "Final review",
    AiWorkflow.GENERAL.value: "Everything else (parsing, answers, cover letters, email)",
}

#: Every task name the app uses (plan §4.3 plus the existing ``ai.tasks``). Unknown task
#: names resolve as ``general``.
TASK_WORKFLOWS: dict[str, AiWorkflow] = {
    # resume-builder
    "generate_resume_section": AiWorkflow.GENERATION,
    "draft_summary": AiWorkflow.GENERATION,
    "rewrite_bullet": AiWorkflow.REWRITING,
    "improve_grammar": AiWorkflow.REWRITING,
    # ats
    "analyze_job_description": AiWorkflow.JD_ANALYSIS,
    "analyze_resume_fit": AiWorkflow.ANALYSIS,
    "tailor_resume": AiWorkflow.GENERATION,
    "review_resume": AiWorkflow.REVIEW,
    "explain_changes": AiWorkflow.REVIEW,
    # spec §8 unified names (aliases callers may use)
    "generate_resume": AiWorkflow.GENERATION,
    "analyze_resume": AiWorkflow.ANALYSIS,
    "optimize_resume": AiWorkflow.REWRITING,
    "tailor_resume_for_role": AiWorkflow.GENERATION,
    # existing ai.tasks
    "parse_resume": AiWorkflow.GENERAL,
    "polish_resume_recommendations": AiWorkflow.REWRITING,
    "explain_match": AiWorkflow.GENERAL,
    "generate_answer": AiWorkflow.GENERAL,
    "generate_cover_letter": AiWorkflow.GENERAL,
    "classify_email": AiWorkflow.GENERAL,
    "generate_interview_prep": AiWorkflow.GENERAL,
    # connection tests from the settings page
    "test_connection": AiWorkflow.GENERAL,
}

SOURCE_TASK_OVERRIDE = "task_override"
SOURCE_USER_DEFAULT = "user_default"
SOURCE_SERVER_DEFAULT = "server_default"


def workflow_for(task: str | None) -> AiWorkflow:
    return TASK_WORKFLOWS.get(str(task or ""), AiWorkflow.GENERAL)


@dataclass(frozen=True)
class Target:
    provider: str
    model: str


@dataclass(frozen=True)
class Resolved:
    """The answer of :func:`resolve` (``fallback`` is ``None`` unless the user enabled it)."""

    provider: str
    model: str
    source: str
    workflow: str
    task: str
    user_id: uuid.UUID | None = None
    fallback: Target | None = None

    @property
    def target(self) -> Target:
        return Target(self.provider, self.model)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "source": self.source,
            "workflow": self.workflow,
            "task": self.task,
            "fallback": {"provider": self.fallback.provider, "model": self.fallback.model} if self.fallback else None,
        }


def server_default() -> Target:
    """``settings.LLM_PROVIDER`` and its model (``LLM_MODEL`` is ignored for the mock)."""
    from app.modules.ai.factory import DEFAULT_MODELS
    from app.modules.ai.providers.mock import MockLLMProvider

    provider = (settings.LLM_PROVIDER or "mock").strip().lower()
    if provider == "mock":
        return Target("mock", MockLLMProvider.model)
    return Target(provider, settings.LLM_MODEL or DEFAULT_MODELS.get(provider) or "")


def default_model_for(provider: str) -> str:
    """The model to use when a provider was picked without one."""
    server = server_default()
    if provider == server.provider:
        return server.model
    info = registry.provider_info(provider)
    return (info.default_model if info else None) or ""


def _target(provider: Any, model: Any) -> Target | None:
    name = str(provider or "").strip()
    if not name or not registry.known_provider(name):
        return None
    chosen = str(model or "").strip() or default_model_for(name)
    return Target(name, chosen) if chosen else None


def load_settings(db: Session, user_id: uuid.UUID):  # noqa: ANN201 - AiProviderSettings | None
    from app.models.ai_settings import AiProviderSettings

    return db.scalar(select(AiProviderSettings).where(AiProviderSettings.user_id == user_id))


def resolve_from(row: Any, task: str, *, user_id: uuid.UUID | None = None, workflow: str | None = None) -> Resolved:
    """Pure resolution from a settings row (or ``None``). ``workflow`` overrides the task's."""
    workflow = AiWorkflow(workflow) if workflow else workflow_for(task)
    primary: Target | None = None
    source = SOURCE_SERVER_DEFAULT
    if row is not None:
        override = (getattr(row, "workflow_models", None) or {}).get(workflow.value)
        if isinstance(override, dict):
            primary = _target(override.get("provider"), override.get("model"))
            if primary:
                source = SOURCE_TASK_OVERRIDE
        if primary is None and getattr(row, "default_provider", None):
            primary = _target(row.default_provider, row.default_model)
            if primary:
                source = SOURCE_USER_DEFAULT
    if primary is None:
        primary = server_default()
        source = SOURCE_SERVER_DEFAULT

    fallback: Target | None = None
    if row is not None and getattr(row, "fallback_enabled", False):
        candidate = _target(row.fallback_provider, row.fallback_model)
        if candidate and candidate != primary:
            fallback = candidate
    return Resolved(
        provider=primary.provider,
        model=primary.model,
        source=source,
        workflow=workflow.value,
        task=str(task or "general"),
        user_id=user_id,
        fallback=fallback,
    )


def resolve(db: Session | None, user_id: uuid.UUID | None, task: str) -> Resolved:
    """Resolve ``task`` for ``user_id`` (``None`` = the server default)."""
    row = None
    if user_id is not None and db is not None:
        row = load_settings(db, user_id)
    return resolve_from(row, task, user_id=user_id)


__all__ = [
    "AiWorkflow",
    "CONFIGURABLE_WORKFLOWS",
    "Resolved",
    "SOURCE_SERVER_DEFAULT",
    "SOURCE_TASK_OVERRIDE",
    "SOURCE_USER_DEFAULT",
    "TASK_WORKFLOWS",
    "Target",
    "default_model_for",
    "load_settings",
    "resolve",
    "resolve_from",
    "server_default",
    "workflow_for",
]
