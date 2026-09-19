"""The answer engine (CONTRACTS.md section 11).

Rules, in order, for every question:

1. an answer the **user** typed is never overwritten;
2. a fact stored on the profile / preferences / resume wins (source
   ``PROFILE`` / ``PREFERENCE`` / ``RESUME``, confidence 1.0);
3. **sensitive** questions (work authorization, sponsorship, demographics, legal
   declarations) stop here - if the profile has no fact they become
   ``NEEDS_USER_INPUT``; the LLM is never asked;
4. anything else goes to :func:`app.modules.ai.tasks.generate_answer`, which may only
   *compose* free text from supplied context. When it cannot, the answer is
   ``NEEDS_USER_INPUT``.

No step ever invents a qualification, an employment date, a salary or a legal status.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.models.application import Application, ApplicationAnswer
from app.models.enums import (
    Actor,
    AnswerSource,
    AnswerStatus,
    ApplicationEventType,
    FieldType,
)
from app.modules.ai.answer_rules import (
    KEY_FALLBACKS,
    answer_source_for_key,
    infer_country,
    lookup_authorization,
    match_option,
)
from app.modules.applications.questions import FormQuestion, questions_for_job

logger = logging.getLogger(__name__)

#: Sources that mean "a human typed this"; regeneration must leave them alone.
PROTECTED_SOURCES: frozenset[AnswerSource] = frozenset({AnswerSource.USER})


# --------------------------------------------------------------------------- fact lookup


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def lookup_fact(flat: dict[str, Any], key: str) -> tuple[Any, str | None]:
    """Find ``key`` (or one of its documented fallbacks) in ``CandidateContext.flat``."""
    lowered = {str(k).lower(): k for k in flat}
    for candidate in (key, *KEY_FALLBACKS.get(key, ())):
        actual = lowered.get(str(candidate).lower())
        if actual is None:
            continue
        value = flat[actual]
        if _is_empty(value):
            continue
        return value, str(actual)
    return None, None


def render_fact(value: Any, key: str, field_type: FieldType) -> str | None:
    """Turn a stored fact into the string a form expects (never invents anything)."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        number = int(value) if float(value).is_integer() else value
        if key == "notice_period_days" and field_type is not FieldType.NUMBER:
            return "Immediate" if int(number) == 0 else f"{int(number)} days"
        return str(number)
    if isinstance(value, (list, tuple, set)):
        text = ", ".join(str(v).strip() for v in value if str(v).strip())
        return text or None
    if isinstance(value, dict):
        return None  # structured facts (e.g. work_authorization) are resolved separately
    text = str(value).strip()
    return text or None


def _work_authorization_answer(question: FormQuestion, candidate: Any, job: Any) -> tuple[str | None, str]:
    """Resolve a work-authorization question from the profile only (never inferred)."""
    flat = dict(getattr(candidate, "flat", None) or {})
    stored = flat.get("work_authorization")
    country = infer_country(question.text) or infer_country(
        getattr(job, "location", None), getattr(getattr(job, "company", None), "name", None)
    )
    allowed = lookup_authorization(stored, country)
    if allowed is None and isinstance(stored, bool):
        allowed = stored
    if allowed is None:
        return None, "work_authorization"
    if question.options:
        return match_option(allowed, question.options), "work_authorization"
    return ("Yes" if allowed else "No"), "work_authorization"


# --------------------------------------------------------------------------- one question


def _answer_from_profile(question: FormQuestion, candidate: Any, job: Any) -> dict[str, Any] | None:
    """A fact the user already stored, or ``None`` when nothing is on file."""
    flat = dict(getattr(candidate, "flat", None) or {})

    if question.key == "work_authorization":
        text, stored_key = _work_authorization_answer(question, candidate, job)
        if not text:
            return None
        return {
            "answer": text,
            "answer_source": AnswerSource.PROFILE,
            "confidence": 1.0,
            "rationale": f"From profile: {stored_key}",
        }

    value, stored_key = lookup_fact(flat, question.key)
    if value is None and question.key == "resume_file":
        value = getattr(candidate, "resume_path", None)
        stored_key = "resume_file"
    if value is None or stored_key is None:
        return None

    text = match_option(value, question.options) if question.options else render_fact(value, question.key, question.field_type)
    if not text:
        return None
    return {
        "answer": text,
        "answer_source": AnswerSource(answer_source_for_key(stored_key)),
        "confidence": 1.0,
        "rationale": f"From profile: {stored_key}",
    }


def _answer_from_ai(question: FormQuestion, candidate: Any, job: Any) -> dict[str, Any]:
    """Ask the AI task to *compose* an answer. Never called for sensitive questions."""
    from app.modules.ai import tasks as ai_tasks  # lazy: keeps import cost off module load

    try:
        generated = ai_tasks.generate_answer(
            question.text,
            question.field_type.value,
            list(question.options),
            job,
            candidate,
            question_key=question.key,
        )
    except Exception as exc:  # noqa: BLE001 - a broken provider must not fail the application
        logger.warning("generate_answer failed for %s: %s", question.key, exc)
        return {"answer": None, "answer_source": None, "confidence": 0.0, "rationale": f"AI answer unavailable: {exc}"}

    if generated.needs_user_input or not (generated.answer or "").strip():
        return {
            "answer": None,
            "answer_source": None,
            "confidence": float(generated.confidence or 0.0),
            "rationale": generated.rationale or f"Not found in profile: {question.key}",
        }
    source = generated.source if isinstance(generated.source, AnswerSource) else AnswerSource(str(generated.source))
    if source in PROTECTED_SOURCES:  # a provider must never claim the user typed it
        source = AnswerSource.AI_GENERATED
    return {
        "answer": generated.answer.strip(),
        "answer_source": source,
        "confidence": float(generated.confidence or 0.0),
        "rationale": generated.rationale or "Composed from your profile and this job posting.",
    }


def answer_question(question: FormQuestion, candidate: Any, job: Any) -> dict[str, Any]:
    """Resolve one question into the column values of an :class:`ApplicationAnswer`."""
    resolved = _answer_from_profile(question, candidate, job)
    if resolved is None and not question.is_sensitive:
        resolved = _answer_from_ai(question, candidate, job)
    if resolved is None:
        resolved = {
            "answer": None,
            "answer_source": None,
            "confidence": 0.0,
            "rationale": (
                f"Not found in profile: {question.key}. Eligibility, sponsorship and demographic "
                "questions are never answered automatically."
            ),
        }
    resolved["status"] = AnswerStatus.ANSWERED if resolved.get("answer") else AnswerStatus.NEEDS_USER_INPUT
    return resolved


# --------------------------------------------------------------------------- persistence


def _apply_to_row(row: ApplicationAnswer, question: FormQuestion, resolved: dict[str, Any], order: int) -> None:
    row.order = order
    row.question_text = question.text
    row.field_type = question.field_type
    row.options = list(question.options)
    row.required = bool(question.required)
    row.is_sensitive = bool(question.is_sensitive)
    if question.selector:
        row.field_selector = question.selector
    if question.mapped_profile_field:
        row.mapped_profile_field = question.mapped_profile_field
    row.answer = resolved.get("answer")
    row.answer_source = resolved.get("answer_source")
    row.status = resolved["status"]
    row.confidence = resolved.get("confidence")
    row.rationale = resolved.get("rationale")


def generate_answers(
    db: Session,
    application: Application,
    candidate: Any,
    questions: Sequence[FormQuestion] | None = None,
) -> list[ApplicationAnswer]:
    """Answer ``questions`` (or the standard set for the job) and upsert the rows.

    Answers the user typed are preserved verbatim. Returns every answer row the
    application has, in form order.
    """
    job = application.job
    question_list = list(questions) if questions is not None else questions_for_job(job)
    existing: dict[str, ApplicationAnswer] = {}
    for row in application.answers or []:
        existing.setdefault(row.question_key, row)

    produced: list[ApplicationAnswer] = []
    counts = {"answered": 0, "needs_user_input": 0, "kept": 0, "ai_generated": 0}

    for order, question in enumerate(question_list):
        row = existing.get(question.key)
        if row is not None and row.answer_source in PROTECTED_SOURCES:
            row.order = order
            if question.selector and not row.field_selector:
                row.field_selector = question.selector
            counts["kept"] += 1
            produced.append(row)
            continue

        resolved = answer_question(question, candidate, job)
        if row is None:
            row = ApplicationAnswer(application_id=application.id, question_key=question.key)
            db.add(row)
            if application.answers is not None:
                application.answers.append(row)
        _apply_to_row(row, question, resolved, order)
        if row.status == AnswerStatus.ANSWERED:
            counts["answered"] += 1
            if row.answer_source == AnswerSource.AI_GENERATED:
                counts["ai_generated"] += 1
        else:
            counts["needs_user_input"] += 1
        produced.append(row)

    # Answers discovered earlier (e.g. by a previous form detection) stay, after the set.
    tail_order = len(question_list)
    for key, row in existing.items():
        if any(row is item for item in produced):
            continue
        row.order = tail_order
        tail_order += 1
        produced.append(row)

    db.flush()

    from app.modules.applications import service as applications_service  # lazy: circular

    applications_service.record_event(
        db,
        application,
        ApplicationEventType.ANSWERS_GENERATED,
        f"Prepared {counts['answered']} of {len(question_list)} answers "
        f"({counts['needs_user_input']} need your input)",
        actor=Actor.AUTOMATION,
        meta=dict(counts, questions=len(question_list)),
    )
    audit(
        db,
        action="application.answers_generated",
        message=(
            f"Generated answers for {_job_label(job)}: {counts['answered']} answered, "
            f"{counts['needs_user_input']} need user input"
        ),
        user_id=application.user_id,
        application_id=application.id,
        actor=Actor.AUTOMATION,
        meta=dict(counts, questions=len(question_list)),
    )
    logger.info("Answers for application %s: %s", application.id, counts)
    return produced


def save_user_answers(db: Session, application: Application, updates: Iterable[Any]) -> list[ApplicationAnswer]:
    """Persist user-typed answers (``{id, answer}`` items). Source becomes ``USER``."""
    from app.core.exceptions import NotFoundError

    by_id = {str(row.id): row for row in (application.answers or [])}
    changed: list[ApplicationAnswer] = []
    for update in updates or []:
        answer_id = str(getattr(update, "id", None) or (update.get("id") if isinstance(update, dict) else ""))
        text = getattr(update, "answer", None) if not isinstance(update, dict) else update.get("answer")
        row = by_id.get(answer_id)
        if row is None:
            raise NotFoundError(f"Answer {answer_id} does not belong to this application")
        row.answer = (str(text) if text is not None else "").strip() or None
        row.answer_source = AnswerSource.USER
        row.status = AnswerStatus.ANSWERED if row.answer else AnswerStatus.NEEDS_USER_INPUT
        row.confidence = 1.0 if row.answer else 0.0
        row.rationale = "Provided by you"
        changed.append(row)
    db.flush()
    logger.info("Saved %d user answers on application %s", len(changed), application.id)
    return changed


def missing_required(application: Application) -> list[ApplicationAnswer]:
    """Required answers still waiting on the user."""
    return [
        row
        for row in (application.answers or [])
        if row.required and row.status == AnswerStatus.NEEDS_USER_INPUT
    ]


def _job_label(job: Any) -> str:
    company = getattr(getattr(job, "company", None), "name", None) or "Unknown company"
    return f"{company} - {getattr(job, 'title', 'role')}"


__all__ = [
    "answer_question",
    "generate_answers",
    "lookup_fact",
    "missing_required",
    "render_fact",
    "save_user_answers",
]
