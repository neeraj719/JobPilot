"""The Approval Center summary (CONTRACTS.md section 11).

``build_review`` answers one question for the human in the loop: *can this application
be submitted right now, and if not, why not?* It never mutates anything.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.models.application import Application, ApplicationAnswer
from app.models.enums import (
    AnswerSource,
    AnswerStatus,
    ApplicationStatus,
    CompanyPriority,
)

logger = logging.getLogger(__name__)

#: An application may only be submitted from one of these statuses.
SUBMITTABLE_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.QUEUED, ApplicationStatus.IN_PROGRESS}
)


class ReviewField(BaseModel):
    """One row of the review table."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    value: str | None = None
    status: AnswerStatus = AnswerStatus.NEEDS_USER_INPUT
    source: AnswerSource | None = None
    required: bool = False
    is_sensitive: bool = False


class ReviewSummary(BaseModel):
    """Everything the Approval Center shows before a human presses *Submit*."""

    model_config = ConfigDict(from_attributes=True)

    company: str = ""
    job_title: str = ""
    resume_name: str | None = None
    salary_expectation: str | None = None
    location: str | None = None
    fields: list[ReviewField] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    sensitive: list[str] = Field(default_factory=list)
    can_submit: bool = False
    blockers: list[str] = Field(default_factory=list)


def _label(answer: ApplicationAnswer) -> str:
    return (answer.question_text or answer.question_key or "").strip() or answer.question_key


def _to_field(answer: ApplicationAnswer) -> ReviewField:
    return ReviewField(
        key=answer.question_key,
        label=_label(answer),
        value=answer.answer,
        status=answer.status,
        source=answer.answer_source,
        required=bool(answer.required),
        is_sensitive=bool(answer.is_sensitive),
    )


def _company_priority(db: Session, application: Application) -> CompanyPriority:
    """The user's priority for this company (``P2`` when the module/row is absent)."""
    company = getattr(application.job, "company", None)
    if company is None:
        return CompanyPriority.P2
    try:
        from app.modules.companies.service import get_priority

        return get_priority(db, application.user_id, company)
    except Exception as exc:  # noqa: BLE001 - companies module optional at import time
        logger.debug("companies.service.get_priority unavailable (%s); defaulting to P2", exc)
        return CompanyPriority.P2


def _salary_expectation(application: Application) -> str | None:
    for answer in application.answers or []:
        if answer.question_key in {"expected_salary", "desired_salary"} and answer.answer:
            return answer.answer
    return None


def build_review(db: Session, application: Application) -> ReviewSummary:
    """Summarise an application for human approval, including every blocker."""
    job = application.job
    company = getattr(getattr(job, "company", None), "name", None) or "Unknown company"
    answers = sorted(application.answers or [], key=lambda a: (a.order, a.question_key))

    fields = [_to_field(answer) for answer in answers]
    missing = [_label(a) for a in answers if a.status == AnswerStatus.NEEDS_USER_INPUT and a.required]
    optional_missing = [_label(a) for a in answers if a.status == AnswerStatus.NEEDS_USER_INPUT and not a.required]
    sensitive = [_label(a) for a in answers if a.is_sensitive]

    blockers: list[str] = []
    for label in missing:
        blockers.append(f"Answer required: {label}")

    if _company_priority(db, application) == CompanyPriority.AVOID:
        blockers.append("Company is on your avoid list")

    if application.status not in SUBMITTABLE_STATUSES:
        blockers.append(f"Application status is {application.status.value}, not QUEUED or IN_PROGRESS")

    if not answers:
        blockers.append("No answers have been prepared yet")

    resume = getattr(application, "resume", None)
    summary = ReviewSummary(
        company=company,
        job_title=getattr(job, "title", "") or "",
        resume_name=getattr(resume, "name", None),
        salary_expectation=_salary_expectation(application),
        location=getattr(job, "location", None),
        fields=fields,
        missing=missing + optional_missing,
        sensitive=sensitive,
        can_submit=not blockers,
        blockers=blockers,
    )
    logger.debug("Review for application %s: can_submit=%s blockers=%s", application.id, summary.can_submit, blockers)
    return summary


def review_counts(applications: list[Application]) -> dict[str, int]:
    """``GET /review-summary`` counters computed from already-loaded applications."""
    pending_review = 0
    requires_input = 0
    ready_to_submit = 0
    for application in applications:
        needs_input = any(
            a.required and a.status == AnswerStatus.NEEDS_USER_INPUT for a in (application.answers or [])
        )
        has_answers = bool(application.answers)
        if needs_input:
            requires_input += 1
        if application.automation_state.value in {"PAUSED", "REQUIRES_USER"}:
            pending_review += 1
        if has_answers and not needs_input and application.status in SUBMITTABLE_STATUSES:
            ready_to_submit += 1
    return {
        "pending_review": pending_review,
        "requires_input": requires_input,
        "ready_to_submit": ready_to_submit,
    }


__all__ = ["ReviewField", "ReviewSummary", "SUBMITTABLE_STATUSES", "build_review", "review_counts"]
