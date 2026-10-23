"""Typed AI tasks — **the only entry point other modules use** (CONTRACTS.md §6).

Every task:

1. normalises its inputs into plain JSON (no ORM objects reach a provider);
2. short-circuits to the provider's deterministic implementation when it has one
   (:meth:`LLMProvider.supports_task`), otherwise builds a prompt and calls the model;
3. validates the result into a pydantic model, falling back to the deterministic
   implementation if a real provider returns something unusable.

``CandidateContext`` is owned by the profiles module. To avoid an import cycle it is
typed as ``Any`` here and read duck-typed (``.flat`` / ``.profile`` / ``.resume``);
a plain ``dict`` with a ``flat`` key is accepted too.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.modules.ai.factory import get_llm_provider, get_mock_provider
from app.modules.ai.prompts import build_prompt, build_system_prompt
from app.modules.ai.schemas import (
    CoverLetter,
    EmailClassificationResult,
    GeneratedAnswer,
    InterviewPrep,
    JobContext,
    MatchExplanation,
    ParsedResume,
    PolishedRecommendation,
    PolishedRecommendations,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MAX_RESUME_CHARS = 40_000

# Canonical key -> attribute on ``UserProfile`` / ``JobPreference``. Used only to fill
# gaps in ``candidate.flat``; the values still come from the user's stored profile.
_PROFILE_FLAT_ATTRS: tuple[str, ...] = (
    "full_name",
    "first_name",
    "last_name",
    "email",
    "phone",
    "address",
    "city",
    "state",
    "country",
    "postal_code",
    "linkedin_url",
    "github_url",
    "portfolio_url",
    "headline",
    "summary",
    "current_designation",
    "current_company",
    "years_of_experience",
    "current_salary",
    "willing_to_relocate",
    "requires_sponsorship",
    "work_authorization",
    "skills",
    "technologies",
)
_PREFERENCE_FLAT_ATTRS: tuple[str, ...] = ("desired_salary", "min_salary", "notice_period_days")


# --------------------------------------------------------------------------- plumbing


def _run(task_name: str, payload: dict[str, Any], schema: type[BaseModel]) -> dict[str, Any]:
    """Run a task on the configured provider, with a deterministic safety net."""
    provider = get_llm_provider()
    if provider.supports_task(task_name):
        return provider.run_task(task_name, payload)

    prompt = build_prompt(task_name, payload, schema=schema)
    try:
        data = provider.complete_json(prompt, schema=schema, system=build_system_prompt(task_name))
        if isinstance(data, dict) and data:
            return data
        raise ValueError("provider returned an empty JSON object")
    except Exception as exc:  # noqa: BLE001 - any provider failure degrades to the mock
        logger.warning(
            "AI task %s failed on provider %s (%s); falling back to the deterministic implementation",
            task_name,
            provider.name,
            exc,
        )
        return get_mock_provider().run_task(task_name, payload)


def _run_validated(task_name: str, payload: dict[str, Any], model: type[T]) -> T:
    data = _run(task_name, payload, model)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        logger.warning("AI task %s returned data that failed validation (%s); using the mock result", task_name, exc)
        return model.model_validate(get_mock_provider().run_task(task_name, payload))


# --------------------------------------------------------------------------- context


def _model_dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _enrich_flat(flat: dict[str, Any], profile: Any, preferences: Any) -> dict[str, Any]:
    """Fill canonical keys the context did not set, from the stored profile itself.

    This only ever copies values the user already saved — it never derives or guesses
    a fact — so "answer only from ``flat``" still holds.
    """
    for attr in _PROFILE_FLAT_ATTRS:
        if flat.get(attr) in (None, "", [], {}):
            value = _get(profile, attr)
            if value not in (None, "", [], {}):
                flat[attr] = _model_dump(value)
    for attr in _PREFERENCE_FLAT_ATTRS:
        if flat.get(attr) in (None, "", [], {}):
            value = _get(preferences, attr)
            if value not in (None, "", [], {}):
                flat[attr] = _model_dump(value)
    return flat


def candidate_payload(candidate: Any) -> dict[str, Any]:
    """Normalise a ``CandidateContext`` (or dict) into a compact JSON payload.

    ``flat`` stays the single source of truth for factual answers; the remaining keys
    are context used only to *compose* free-text answers.
    """
    if candidate is None:
        return {"flat": {}}

    if isinstance(candidate, dict):
        payload = dict(candidate)
        payload["flat"] = _enrich_flat(dict(payload.get("flat") or {}), payload.get("profile"), payload.get("preferences"))
        return _fill_context_fields(payload, profile=payload.get("profile"), resume=payload.get("resume"))

    profile = _get(candidate, "profile")
    preferences = _get(candidate, "preferences")
    resume = _get(candidate, "resume")
    flat = _enrich_flat(dict(_get(candidate, "flat") or {}), profile, preferences)

    payload: dict[str, Any] = {}
    # Prefer the profiles module's own prompt summary when it exists (imported lazily
    # to avoid a circular import: profiles -> resumes -> ai -> profiles).
    try:
        from app.modules.profiles import service as profiles_service  # noqa: PLC0415

        to_prompt_dict = getattr(profiles_service, "candidate_context_to_prompt_dict", None)
        if callable(to_prompt_dict):
            built = to_prompt_dict(candidate)
            if isinstance(built, dict):
                payload = dict(built)
    except Exception as exc:  # noqa: BLE001 - module may not exist yet
        logger.debug("profiles.candidate_context_to_prompt_dict unavailable (%s); building context locally", exc)

    payload["flat"] = flat
    payload.setdefault("resume_name", _get(resume, "name"))
    payload.setdefault("resume_path", _get(candidate, "resume_path"))
    return _fill_context_fields(payload, profile=profile, resume=resume)


def _fill_context_fields(payload: dict[str, Any], *, profile: Any = None, resume: Any = None) -> dict[str, Any]:
    """Derive the display/composition fields from flat + profile + resume."""
    flat = payload.get("flat") or {}
    parsed = _get(resume, "parsed_data") or {}
    if isinstance(parsed, BaseModel):
        parsed = parsed.model_dump(mode="json")
    if not isinstance(parsed, dict):
        parsed = {}

    defaults = {
        "full_name": _first_nonempty(payload.get("full_name"), flat.get("full_name"), _get(profile, "full_name"), parsed.get("name")),
        "headline": _first_nonempty(payload.get("headline"), flat.get("headline"), _get(profile, "headline")),
        "current_designation": _first_nonempty(
            payload.get("current_designation"), flat.get("current_designation"), _get(profile, "current_designation")
        ),
        "current_company": _first_nonempty(payload.get("current_company"), flat.get("current_company"), _get(profile, "current_company")),
        "years_of_experience": _first_nonempty(
            payload.get("years_of_experience"),
            flat.get("years_of_experience"),
            _get(profile, "years_of_experience"),
            parsed.get("total_experience_years"),
        ),
        "summary": _first_nonempty(payload.get("summary"), flat.get("summary"), _get(profile, "summary"), parsed.get("summary")),
        "city": _first_nonempty(payload.get("city"), flat.get("city"), _get(profile, "city")),
        "country": _first_nonempty(payload.get("country"), flat.get("country"), _get(profile, "country")),
        "skills": _first_nonempty(payload.get("skills"), flat.get("skills"), _get(profile, "skills"), parsed.get("skills")) or [],
        "projects": _first_nonempty(payload.get("projects"), _get(profile, "projects"), parsed.get("projects")) or [],
        "experience": _first_nonempty(payload.get("experience"), _get(profile, "previous_companies"), parsed.get("experience")) or [],
        "education": _first_nonempty(payload.get("education"), _get(profile, "education"), parsed.get("education")) or [],
        "certifications": _first_nonempty(payload.get("certifications"), _get(profile, "certifications"), parsed.get("certifications")) or [],
    }
    for key, value in defaults.items():
        payload[key] = _model_dump(value)
    payload["flat"] = {k: _model_dump(v) for k, v in flat.items()}
    return payload


def job_payload(job: Any) -> dict[str, Any]:
    return JobContext.coerce(job).model_dump(mode="json")


# --------------------------------------------------------------------------- tasks


def parse_resume(text: str) -> ParsedResume:
    """Extract structured data from raw resume text (never invents values).

    The deterministic rule-based parser is the base. A real LLM only fills fields the rules
    left empty, and its skills are kept only when they literally appear in the text. Small
    local models routinely drop contact details, split one job into several or list headings
    as skills; this keeps a re-parse from ever being worse than the rules alone.
    """
    payload = {"text": (text or "")[:MAX_RESUME_CHARS]}
    rule = add_listed_skills(
        ParsedResume.model_validate(get_mock_provider().run_task("parse_resume", payload)), payload["text"]
    )
    if getattr(get_llm_provider(), "name", "mock") == "mock":
        return rule
    try:
        llm = _run_validated("parse_resume", payload, ParsedResume)
    except Exception as exc:  # noqa: BLE001 - the rule-based result is always usable
        logger.warning("LLM resume parse failed (%s); using the rule-based parse", exc)
        return rule
    return merge_parsed_resume(rule, llm, payload["text"])


#: An LLM-proposed skill longer than this is a phrase or a heading, not a skill.
_MAX_SKILL_WORDS = 4


def _filled(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_filled(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    return value not in (None, "")


def merge_parsed_resume(rule: ParsedResume, llm: ParsedResume, text: str) -> ParsedResume:
    """Rule-based fields win; the LLM fills only empty ones, verified against ``text``."""
    base = rule.model_dump(mode="json")
    extra = llm.model_dump(mode="json")
    lower = (text or "").lower()

    for key, value in extra.items():
        if key in {"skills", "summary"} or _filled(base.get(key)) or not _filled(value):
            continue
        if key == "links" and isinstance(value, dict) and isinstance(base.get("links"), dict):
            base["links"] = {k: base["links"].get(k) or v for k, v in value.items()}
            continue
        base[key] = value

    # Summary: only when the rules found none and the LLM's text is really in the document.
    summary = (extra.get("summary") or "").strip()
    if not base.get("summary") and summary:
        words = [w for w in re.findall(r"[a-z0-9]+", summary.lower()) if len(w) > 3]
        if words and sum(1 for w in words if w in lower) / len(words) >= 0.8:
            base["summary"] = summary

    # Skills: keep the rule-based list; add an LLM skill only when it is a known skill (any alias
    # of the taxonomy) or an item of a "Label: a, b, c" skills line in the document. Phrases the
    # model lifts from sentences ("scalable microservices", "AI-driven solutions") are dropped,
    # and aliases collapse to one canonical name ("React.js" -> "React").
    from app.modules.ai.skills import _alias_index

    aliases = _alias_index()
    list_items = _skill_list_items(text)
    skills = list(base.get("skills") or [])
    seen = {resume_skill_name(str(s)).lower() for s in skills} | {str(s).lower() for s in skills}
    for raw in extra.get("skills") or []:
        name = str(raw or "").strip()
        if not name or len(name.split()) > _MAX_SKILL_WORDS or name.lower() not in lower:
            continue
        known = name.lower() in aliases
        if not known and name.lower() not in list_items:
            continue
        canonical = resume_skill_name(name)
        if canonical.lower() in seen:
            continue
        skills.append(canonical)
        seen.add(canonical.lower())
    base["skills"] = skills
    return ParsedResume.model_validate(base)


def _split_top_level(text: str) -> list[str]:
    """Split on commas outside parentheses: "AWS (EC2, S3), Docker" -> ["AWS (EC2, S3)", "Docker"]."""
    parts: list[str] = []
    depth = 0
    current = ""
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return parts


def listed_skills(text: str) -> list[str]:
    """Items of "Label: a, b, c" lines, in order, without parenthesised details."""
    items: list[str] = []
    for line in (text or "").splitlines():
        if ":" not in line:
            continue
        label, rest = line.split(":", 1)
        parts = _split_top_level(rest)
        if len(parts) < 3 or len(label.split()) > 4:
            continue
        for item in parts:
            item = re.sub(r"\s*\([^)]*\)", "", item).strip(" .;")
            if item and len(item.split()) <= _MAX_SKILL_WORDS and not item.endswith("."):
                items.append(item)
    return items


def _skill_list_items(text: str) -> set[str]:
    """Lower-cased items of lines shaped like "Frontend: React.js, Next.js, Redux"."""
    return {item.lower() for item in listed_skills(text)}


def _spelling_variant(name: str, canonical: str) -> bool:
    """"React.js"/"React", "HTML5"/"HTML": the same skill spelled differently.

    "GitHub"/"Git" or "RAG"/"LLMs" are taxonomy relatives, not spellings: both stay listed.
    """
    a = re.sub(r"[^a-z0-9+#]", "", name.lower())
    b = re.sub(r"[^a-z0-9+#]", "", canonical.lower())
    return a == b or ((a.startswith(b) or b.startswith(a)) and abs(len(a) - len(b)) <= 2)


def resume_skill_name(name: str) -> str:
    """The name to show on the resume: the canonical spelling, but never a different skill."""
    from app.modules.ai.skills import _alias_index

    canonical = _alias_index().get(name.lower())
    return canonical if canonical and _spelling_variant(name, canonical) else name


def add_listed_skills(parsed: ParsedResume, text: str) -> ParsedResume:
    """Every item of the resume's own skills lines is a skill; spelling variants collapse."""
    skills = list(parsed.skills)
    seen = {s.lower() for s in skills} | {resume_skill_name(s).lower() for s in skills}
    for item in listed_skills(text):
        name = resume_skill_name(item)
        if name.lower() in seen:
            continue
        skills.append(name)
        seen.add(name.lower())
    return parsed.model_copy(update={"skills": skills})


def explain_match(job: Any, candidate: Any, scores: dict[str, Any]) -> str:
    """2-4 sentences explaining a job match, built from the scoring output."""
    payload = {
        "job": job_payload(job),
        "candidate": candidate_payload(candidate),
        "scores": {k: _model_dump(v) for k, v in (scores or {}).items()},
    }
    return _run_validated("explain_match", payload, MatchExplanation).explanation


def generate_answer(
    question: str,
    field_type: str,
    options: list[str],
    job: Any,
    candidate: Any,
    *,
    question_key: str | None = None,
) -> GeneratedAnswer:
    """Answer one application question.

    Factual questions are answered **only** from ``candidate.flat``; sensitive ones
    (work authorization, sponsorship, demographics) are never inferred. Anything the
    profile cannot supply comes back with ``needs_user_input=True``.
    """
    payload = {
        "question": str(question or ""),
        "field_type": str(field_type or "TEXT"),  # tolerate a FieldType enum
        "options": [str(o) for o in (options or [])],
        "job": job_payload(job),
        "candidate": candidate_payload(candidate),
    }
    if question_key:
        payload["question_key"] = question_key
    return _run_validated("generate_answer", payload, GeneratedAnswer)


def generate_cover_letter(job: Any, candidate: Any) -> str:
    """A cover letter of at most 250 words, built only from supplied facts."""
    payload = {"job": job_payload(job), "candidate": candidate_payload(candidate)}
    return _run_validated("generate_cover_letter", payload, CoverLetter).cover_letter


def classify_email(subject: str, sender: str, body: str) -> EmailClassificationResult:
    """Classify one recruiting email into an ``EmailClassification``."""
    payload = {"subject": subject or "", "sender": sender or "", "body": (body or "")[:8000]}
    return _run_validated("classify_email", payload, EmailClassificationResult)


def generate_interview_prep(job: Any, candidate: Any, interview_type: str) -> InterviewPrep:
    """Interview question banks grouped by category."""
    payload = {
        "job": job_payload(job),
        "candidate": candidate_payload(candidate),
        "interview_type": (interview_type or "TECHNICAL"),
    }
    return _run_validated("generate_interview_prep", payload, InterviewPrep)


# --------------------------------------------------------------------------- resume advice

#: Upper bound the prompt asks for; longer text is clipped, never trusted as is.
MAX_POLISH_WORDS = 60
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
#: Fields of a recommendation the model gets to see (no internal score maths).
_POLISH_FIELDS: tuple[str, ...] = ("id", "category", "priority", "title", "detail", "action", "skills", "evidence")


def _clip_words(text: str | None, max_words: int = MAX_POLISH_WORDS) -> str | None:
    if text is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return None
    words = cleaned.split(" ")
    if len(words) <= max_words:
        return cleaned
    return " ".join(words[:max_words]).rstrip(",;: ") + "…"


def _numbers(text: Any) -> set[str]:
    """Every number in ``text``, normalised so ``2.0`` and ``2`` compare equal."""
    found: set[str] = set()
    for raw in _NUMBER_RE.findall(text if isinstance(text, str) else json.dumps(text, default=str)):
        value = raw.replace(",", "")
        if re.fullmatch(r"\d+\.0+", value):
            value = value.split(".")[0]
        found.add(value)
    return found


def invented_numbers(text: str | None, *sources: Any) -> set[str]:
    """Numbers in ``text`` that appear in none of ``sources`` (strings or JSON-able data).

    The "no numbers that are not in the resume" check, shared by the polish filter below
    and by ``resumes.apply`` (a summary the user is about to save).
    """
    if not text:
        return set()
    allowed: set[str] = set()
    for source in sources:
        if source not in (None, "", [], {}):
            allowed |= _numbers(source)
    return _numbers(text) - allowed


def polish_resume_recommendations(
    resume_payload: dict[str, Any],
    recommendations: list[Any],
) -> PolishedRecommendations:
    """Reword deterministic resume recommendations; never adds advice or facts.

    The response is filtered before anyone sees it:

    * items whose ``id`` was not sent (or repeats one) are dropped;
    * ``detail`` / ``suggested_text`` are clipped to ``MAX_POLISH_WORDS`` words;
    * a number that appears in neither the resume payload nor the original
      recommendation is treated as an invented metric — the reworded ``detail`` is
      discarded (the original wording stays) and the ``suggested_text`` is dropped.

    Provider errors propagate; the caller (``resumes.recommendations``) owns the
    fallback to the deterministic text.
    """
    sent: list[dict[str, Any]] = []
    for rec in recommendations or []:
        data = _model_dump(rec)
        if isinstance(data, dict) and data.get("id"):
            sent.append({key: _model_dump(data.get(key)) for key in _POLISH_FIELDS})
    if not sent:
        return PolishedRecommendations()

    payload = {"resume": _model_dump(resume_payload) or {}, "recommendations": sent}
    result = _run_validated("polish_resume_recommendations", payload, PolishedRecommendations)

    by_id = {rec["id"]: rec for rec in sent}
    resume_numbers = _numbers(payload["resume"])
    kept: list[PolishedRecommendation] = []
    seen: set[str] = set()
    for item in result.items:
        original = by_id.get(item.id)
        if original is None or item.id in seen:
            logger.info("polish_resume_recommendations: dropping unknown or repeated id %r", item.id)
            continue
        seen.add(item.id)
        allowed = resume_numbers | _numbers(original.get("detail") or "") | _numbers(original.get("title") or "")
        detail = _clip_words(item.detail)
        if detail and not _numbers(detail) <= allowed:
            logger.info("polish_resume_recommendations: %s detail introduced numbers; keeping the original", item.id)
            detail = None
        suggested = _clip_words(item.suggested_text)
        if suggested and invented_numbers(suggested, payload["resume"]):
            logger.info("polish_resume_recommendations: %s suggestion introduced numbers; dropped", item.id)
            suggested = None
        kept.append(PolishedRecommendation(id=item.id, detail=detail, suggested_text=suggested))
    return PolishedRecommendations(items=kept)


__all__ = [
    "candidate_payload",
    "classify_email",
    "explain_match",
    "generate_answer",
    "generate_cover_letter",
    "generate_interview_prep",
    "invented_numbers",
    "job_payload",
    "parse_resume",
    "polish_resume_recommendations",
]
