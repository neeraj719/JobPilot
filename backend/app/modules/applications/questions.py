"""The standard question set an application starts from (CONTRACTS.md section 11).

Before a browser ever opens, JobPilot already knows which questions an application of a
given :class:`~app.models.enums.ApplicationType` will ask. Those questions are answered
from the profile up-front so the Approval Center has something to show, and the live
form detector later *adds* whatever the real page asks on top (see
``browser/runner.py``).

Nothing here guesses: every question carries the canonical key from section 11 so the
answer engine can look the fact up in ``CandidateContext.flat`` (or mark it
``NEEDS_USER_INPUT``), plus ``is_sensitive`` for the questions AI must never answer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.models.enums import ApplicationType, FieldType
from app.modules.ai.answer_rules import answer_source_for_key, is_sensitive_key

logger = logging.getLogger(__name__)

#: Notice-period wording used by most Indian ATS forms (mirrors the demo ATS select).
NOTICE_PERIOD_OPTIONS: tuple[str, ...] = ("Immediate", "15 days", "30 days", "60 days", "90 days")
YES_NO_OPTIONS: tuple[str, ...] = ("Yes", "No")


@dataclass
class FormQuestion:
    """One question an application form asks.

    ``key`` is a canonical key from section 11 (``phone``, ``expected_salary``,
    ``skill_years:react``, ``custom:<slug>``...). ``selector`` is set only for questions
    discovered on a live page.
    """

    key: str
    text: str
    field_type: FieldType = FieldType.TEXT
    options: list[str] = field(default_factory=list)
    required: bool = True
    selector: str | None = None
    is_sensitive: bool = False
    mapped_profile_field: str | None = None

    def __post_init__(self) -> None:
        self.key = (self.key or "").strip() or "custom:question"
        self.options = [str(o) for o in (self.options or []) if str(o).strip()]
        if not self.is_sensitive:
            self.is_sensitive = is_sensitive_key(self.key)
        if self.mapped_profile_field is None:
            self.mapped_profile_field = profile_field_for(self.key)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "text": self.text,
            "field_type": self.field_type.value,
            "options": list(self.options),
            "required": self.required,
            "selector": self.selector,
            "is_sensitive": self.is_sensitive,
            "mapped_profile_field": self.mapped_profile_field,
        }


def profile_field_for(key: str) -> str | None:
    """Where a canonical key's value lives, for the "answered from" line in the UI."""
    if not key or key.startswith("custom:"):
        return None
    if key.startswith("skill_years:"):
        return f"profile.skill_experience.{key.split(':', 1)[1]}"
    source = answer_source_for_key(key)
    if source == "RESUME":
        return "resume.file"
    if source == "PREFERENCE":
        return f"preference.{key}"
    return f"profile.{key}"


def _q(key: str, text: str, field_type: FieldType = FieldType.TEXT, *, required: bool = True, options: tuple[str, ...] = ()) -> FormQuestion:
    return FormQuestion(key=key, text=text, field_type=field_type, options=list(options), required=required)


def _easy_apply_questions(company: str) -> list[FormQuestion]:
    """Platform "easy apply": the short set a LinkedIn/Naukri style flow pre-fills."""
    return [
        _q("full_name", "Full name"),
        _q("email", "Email address", FieldType.EMAIL),
        _q("phone", "Mobile number", FieldType.PHONE),
        _q("resume_file", "Resume", FieldType.FILE),
        _q("years_of_experience", "Total years of experience", FieldType.NUMBER),
        _q("expected_salary", "Expected CTC (annual)", FieldType.NUMBER),
        _q("notice_period_days", "Notice period (days)", FieldType.NUMBER),
        _q("linkedin_url", "LinkedIn profile", FieldType.URL, required=False),
    ]


def _hosted_form_questions(company: str) -> list[FormQuestion]:
    """Greenhouse/Lever/company-site style hosted form (ATS_FORM / EXTERNAL_FORM)."""
    return [
        _q("first_name", "First name"),
        _q("last_name", "Last name"),
        _q("email", "Email", FieldType.EMAIL),
        _q("phone", "Phone", FieldType.PHONE),
        _q("city", "Location (city)"),
        _q("linkedin_url", "LinkedIn profile", FieldType.URL, required=False),
        _q("github_url", "GitHub URL", FieldType.URL, required=False),
        _q("portfolio_url", "Portfolio", FieldType.URL, required=False),
        _q("resume_file", "Resume/CV", FieldType.FILE),
        _q("years_of_experience", "Total years of experience", FieldType.NUMBER),
        _q("current_salary", "Current CTC (annual)", FieldType.NUMBER, required=False),
        _q("expected_salary", "Expected CTC (annual)", FieldType.NUMBER),
        _q("notice_period_text", "Notice period"),
        FormQuestion(
            key="work_authorization",
            text=f"Are you legally authorized to work in the country of this {company} role?",
            field_type=FieldType.RADIO,
            options=list(YES_NO_OPTIONS),
            required=True,
            is_sensitive=True,
        ),
        _q("custom:why_us", f"Why do you want to work at {company}?", FieldType.TEXTAREA),
    ]


#: ``ApplicationType`` -> builder for its standard question set.
STANDARD_QUESTIONS: dict[ApplicationType, Any] = {
    ApplicationType.EASY_APPLY: _easy_apply_questions,
    ApplicationType.ATS_FORM: _hosted_form_questions,
    ApplicationType.EXTERNAL_FORM: _hosted_form_questions,
    ApplicationType.EMAIL: _easy_apply_questions,
    ApplicationType.UNKNOWN: _easy_apply_questions,
}


def standard_questions(application_type: ApplicationType | str | None, *, company_name: str | None = None) -> list[FormQuestion]:
    """The questions an application of ``application_type`` starts with."""
    try:
        resolved = ApplicationType(str(application_type or ApplicationType.UNKNOWN))
    except ValueError:  # pragma: no cover - defensive
        resolved = ApplicationType.UNKNOWN
    builder = STANDARD_QUESTIONS.get(resolved, _easy_apply_questions)
    company = (company_name or "").strip() or "this company"
    questions = builder(company)
    logger.debug("Standard question set for %s: %d questions", resolved.value, len(questions))
    return questions


def questions_for_job(job: Any) -> list[FormQuestion]:
    """Convenience wrapper that reads the type and company straight off a ``Job``."""
    company = getattr(getattr(job, "company", None), "name", None)
    return standard_questions(getattr(job, "application_type", None), company_name=company)


__all__ = [
    "FormQuestion",
    "NOTICE_PERIOD_OPTIONS",
    "STANDARD_QUESTIONS",
    "YES_NO_OPTIONS",
    "profile_field_for",
    "questions_for_job",
    "standard_questions",
]
