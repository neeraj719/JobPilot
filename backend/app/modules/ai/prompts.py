"""Prompt construction for every AI task.

Each prompt is an *envelope*: a task name, a strictly-JSON input block and the
expected output schema. Two consequences:

* real providers get unambiguous, structured instructions (no free-text parsing);
* the deterministic mock can recover ``(task, payload)`` from any prompt it is
  handed (:func:`parse_task_envelope`) and answer with rules instead of a model.

The system prompts encode the product's hard rule: **never invent facts**.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

from app.modules.ai.provider import schema_to_dict

INPUT_OPEN = "<<<INPUT_JSON"
INPUT_CLOSE = "INPUT_JSON>>>"

_ENVELOPE_RE = re.compile(
    rf"TASK:\s*(?P<task>[a-z_]+).*?{re.escape(INPUT_OPEN)}\s*(?P<payload>.*?)\s*{re.escape(INPUT_CLOSE)}",
    re.DOTALL,
)

BASE_SYSTEM = (
    "You are JobPilot AI, an assistant that helps a software engineer apply for jobs. "
    "You work only from the facts you are given. You never invent qualifications, employment "
    "history, education, certifications, legal/visa status, salary figures or dates. "
    "If a fact is missing, say so explicitly instead of guessing. "
    "Answer with a single JSON object and nothing else."
)

TASK_SYSTEM: dict[str, str] = {
    "parse_resume": (
        BASE_SYSTEM + " You are extracting structured data from resume text. Copy values verbatim from the "
        "text; leave a field null when the resume does not contain it."
    ),
    "explain_match": (
        BASE_SYSTEM + " You explain, in 2-4 short sentences, why a job does or does not match a candidate. "
        "Use only the supplied scores and skill lists."
    ),
    "generate_answer": (
        BASE_SYSTEM + " You fill in one job-application question. Factual questions (salary, notice period, "
        "years of experience, work authorization, sponsorship, demographics) may only be answered from the "
        "candidate's stored profile facts; if the fact is absent set needs_user_input=true and answer=null. "
        "Only open-ended motivation questions may be composed, and only from the given context."
    ),
    "generate_cover_letter": (
        BASE_SYSTEM + " You write a concise cover letter of at most 250 words using only the candidate facts "
        "provided. No invented achievements, employers, metrics or dates."
    ),
    "classify_email": (
        BASE_SYSTEM + " You classify one recruiting email into exactly one category and explain the decision "
        "in one sentence."
    ),
    "generate_interview_prep": (
        BASE_SYSTEM + " You produce interview preparation questions grouped by category. Questions must be "
        "grounded in the job's requirements and the candidate's real experience."
    ),
    "polish_resume_recommendations": (
        BASE_SYSTEM + " You reword resume-improvement advice that was already computed from data. You do not "
        "add new advice. Use only facts present in the resume payload: do not add employers, job titles, "
        "dates, degrees, skills the candidate has not listed, or metrics/numbers that are not there. Where a "
        "suggestion needs a number the resume does not contain, write a bracketed placeholder such as [X%]. "
        "Keep each detail and each suggested_text under 60 words."
    ),
}

TASK_INSTRUCTIONS: dict[str, str] = {
    "parse_resume": (
        "Extract the candidate's details from the resume text in INPUT.text.\n"
        "- skills: canonical technology names actually mentioned.\n"
        "- total_experience_years: a number the resume states or that follows from the employment dates; "
        "null if it cannot be derived.\n"
        "- experience/education/projects/certifications: one object per entry, in resume order."
    ),
    "explain_match": (
        "Write 2-4 sentences explaining the match. Mention matched skills, missing skills, experience fit, "
        "location and salary only when INPUT.scores contains them. Return {\"explanation\": \"...\"}."
    ),
    "generate_answer": (
        "Answer INPUT.question for this application.\n"
        "- Use INPUT.candidate.flat for every factual value; it is the only source of truth.\n"
        "- If INPUT.options is non-empty, the answer MUST be one of those options verbatim.\n"
        "- Never answer work authorization, sponsorship, or demographic questions from inference.\n"
        "- When the required fact is missing: answer=null, needs_user_input=true, and rationale explains which "
        "fact is missing."
    ),
    "generate_cover_letter": (
        "Write a cover letter of at most 250 words addressed to INPUT.job.company_name for the role "
        "INPUT.job.title, using only INPUT.candidate facts. Return {\"cover_letter\": \"...\"}."
    ),
    "classify_email": (
        "Classify the email. classification must be one of: APPLICATION_RECEIVED, RECRUITER_MESSAGE, INTERVIEW, "
        "ASSESSMENT, REJECTION, OFFER, OTHER. company_hint/job_title_hint are null unless clearly present."
    ),
    "generate_interview_prep": (
        "Produce 4-8 questions per category for an interview of type INPUT.interview_type. resume_based "
        "questions must reference the candidate's actual projects or employers."
    ),
    "polish_resume_recommendations": (
        "INPUT.recommendations is a list of resume recommendations computed by rules; INPUT.resume holds the "
        "candidate's resume facts.\n"
        "For each recommendation return {\"id\", \"detail\", \"suggested_text\"}:\n"
        "- id: copied verbatim from INPUT.recommendations; never invent ids.\n"
        "- detail: a clearer, friendlier rewording of the given detail (same meaning, under 60 words).\n"
        "- suggested_text: optional example text the candidate could paste, e.g. a rewritten summary or ONE "
        "example bullet, under 60 words; null when it would require facts that are not in INPUT.resume.\n"
        "- Use only facts present in INPUT.resume. Do not add employers, dates, degrees or metrics that are not "
        "there; use placeholders like [X%] or [N users] instead of numbers.\n"
        "- Never suggest claiming a skill the candidate has not listed; for action \"learn\" describe learning it.\n"
        "Return {\"items\": [...]}."
    ),
}


def _compact(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str, sort_keys=True)


def build_system_prompt(task_name: str) -> str:
    return TASK_SYSTEM.get(task_name, BASE_SYSTEM)


def build_prompt(
    task_name: str,
    payload: dict[str, Any],
    *,
    schema: dict[str, Any] | type[BaseModel] | None = None,
) -> str:
    """Build the user prompt for ``task_name``."""
    parts = [f"TASK: {task_name}", "", TASK_INSTRUCTIONS.get(task_name, "Complete the task."), ""]
    parts.append(INPUT_OPEN)
    parts.append(_compact(payload))
    parts.append(INPUT_CLOSE)
    schema_dict = schema_to_dict(schema)
    if schema_dict:
        parts += ["", "Respond with a single JSON object matching this JSON schema:", _compact(schema_dict)]
    return "\n".join(parts)


def parse_task_envelope(prompt: str) -> tuple[str, dict[str, Any]] | None:
    """Recover ``(task_name, payload)`` from a prompt built by :func:`build_prompt`."""
    if not prompt:
        return None
    match = _ENVELOPE_RE.search(prompt)
    if not match:
        return None
    try:
        payload = json.loads(match.group("payload"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return match.group("task"), payload


__all__ = ["BASE_SYSTEM", "build_prompt", "build_system_prompt", "parse_task_envelope"]
