"""Writing help for the resume editor: rules first, the model only polishes.

Four helpers back the editor's per-bullet / per-field AI actions:

* :func:`rewrite_bullet` — up to three rewrites of one bullet;
* :func:`responsibility_to_achievement` — an achievement-oriented bullet that ends in a
  ``[result]`` placeholder when the input states no result (never a made-up number);
* :func:`improve_text` — grammar, clarity and tone only;
* :func:`draft_summary` — a summary built from resume/profile facts, optionally polished.

Every candidate is checked with the same guards ``resumes.apply`` uses before a user
sees it (``bullet_problem`` / ``bullet_checks``, ``summary_problem``, ``invented_numbers``,
``strip_filler``, ``looks_like_advice``). Nothing here writes to the database: the editor
applies a suggestion to its local draft, and only saving creates a version.
"""
from __future__ import annotations

import copy
import logging
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.resume import Resume
from app.modules.ai import tasks as ai_tasks
from app.modules.ai.schemas import ParsedResume
from app.modules.ai.skills import extract_skills
from app.modules.resumes import apply
from app.modules.resumes import recommendations as rec_mod
from app.modules.resumes.schemas import (
    BulletCandidate,
    BulletChecks,
    BulletSuggestions,
    ImprovedText,
    SummaryDraft,
)

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 3
RESULT_PLACEHOLDER = "[result]"

#: Weak openers and verbs of the same meaning (deterministic alternatives; each one is
#: still checked, so a verb that implies a claim is dropped by the guards).
_ALTERNATIVES: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), verbs)
    for pattern, verbs in (
        (r"^(?:was\s+)?responsible\s+for\s+(?:the\s+)?", ("Owned ", "Handled ")),
        (r"^worked\s+on\s+", ("Developed ", "Built ", "Implemented ")),
        (r"^worked\s+with\s+", ("Collaborated with ", "Partnered with ")),
        (r"^helped\s+(?:to\s+|with\s+)?", ("Contributed to ", "Supported ")),
        (r"^assisted\s+(?:in\s+|with\s+)?", ("Supported ", "Contributed to ")),
        (r"^involved\s+in\s+", ("Contributed to ", "Took part in ")),
        (r"^participated\s+in\s+", ("Contributed to ", "Took part in ")),
        (r"^did\s+", ("Delivered ", "Completed ")),
        (r"^made\s+", ("Built ", "Created ")),
        (r"^wrote\s+", ("Developed ", "Authored ")),
        (r"^handled\s+", ("Processed ", "Resolved ")),
        (r"^used\s+", ("Applied ", "Employed ")),
    )
)


# --------------------------------------------------------------------------- facts


def facts_for(db: Session, user_id: uuid.UUID, resume: Resume, parsed: ParsedResume | None = None) -> apply._Facts:  # noqa: SLF001
    """What the candidate has confirmed: the saved resume (or the editor's draft, which
    the user typed), its source text and the profile."""
    data = parsed.model_dump(mode="json") if parsed is not None else copy.deepcopy(resume.parsed_data or {})
    raw = resume.text_content or ""
    if parsed is not None:
        from app.modules.resumes.service import plain_text_of

        raw = f"{raw}\n{plain_text_of(parsed)}"
    return apply._Facts(parsed=data, raw_text=raw, inputs=rec_mod.load_match_inputs(db, user_id))  # noqa: SLF001


def _same(a: str, b: str) -> bool:
    return " ".join(a.split()).rstrip(" .").lower() == " ".join(b.split()).rstrip(" .").lower()


def _finish(text: str) -> str:
    text = " ".join((text or "").split()).strip(" -•*")
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if text.endswith((".", "]")) else text.rstrip(" ;,") + "."


def _hard_problem(text: str, original: str, facts: apply._Facts, *, allow_placeholder: bool = False) -> str | None:  # noqa: SLF001
    """Guards that never let a candidate through (as opposed to the shown checks)."""
    if not text:
        return "empty"
    if not allow_placeholder and ("[" in text or "]" in text):
        return "placeholder"
    if apply.looks_like_advice(text):
        return "advice_text"
    if len(text.split()) > apply.MAX_BULLET_WORDS + (3 if allow_placeholder else 0):
        return "too_long"
    return None


def _candidate(text: str, original: str, source: str, facts: apply._Facts, *, allow_placeholder: bool = False) -> BulletCandidate | None:  # noqa: SLF001
    if _hard_problem(text, original, facts, allow_placeholder=allow_placeholder):
        return None
    checked = text.replace(RESULT_PLACEHOLDER, "") if allow_placeholder else text
    reference = original
    if source == "rule":
        # The rule swapped a weak opener for a verb of the same meaning from a fixed table
        # ("Responsible for" -> "Owned"); that verb is not a new claim.
        first = (checked.split() or [""])[0]
        reference = f"{original} {first}"
    checks = BulletChecks(**apply.bullet_checks(checked, reference, facts))
    # A candidate that adds a number or a claim is never offered: the checks shown to the
    # user are about how much was kept, not a list of risks to accept.
    if not checks.no_new_numbers or not checks.no_new_claims:
        return None
    return BulletCandidate(
        text=text, source=source, checks=checks, has_placeholder=apply.has_placeholder(text)  # type: ignore[arg-type]
    )


def _rule_rewrites(bullet: str) -> list[str]:
    text = " ".join((bullet or "").split()).strip(" -•*")
    out: list[str] = []
    for pattern, verbs in _ALTERNATIVES:
        if pattern.search(text):
            out.extend(_finish(pattern.sub(verb, text, count=1)) for verb in verbs)
            break
    out.append(apply.tidy_bullet(bullet))
    return out


def _pick(candidates: list[BulletCandidate], original: str) -> list[BulletCandidate]:
    seen: set[str] = set()
    picked: list[BulletCandidate] = []
    # Fully passing candidates first (AI before rule, the model adds variety), then the rest.
    ranked = sorted(
        candidates,
        key=lambda c: (not c.checks.kept_details, c.source != "ai"),
    )
    for cand in ranked:
        key = " ".join(cand.text.lower().split()).rstrip(".")
        if key in seen or _same(cand.text, original):
            continue
        seen.add(key)
        picked.append(cand)
        if len(picked) >= MAX_CANDIDATES:
            break
    return picked


# --------------------------------------------------------------------------- bullets


def rewrite_bullet(
    db: Session,
    user_id: uuid.UUID,
    resume: Resume,
    text: str,
    *,
    role: str | None = None,
    company: str | None = None,
) -> BulletSuggestions:
    """Up to three rewrites that keep the bullet's facts (rules + checked model output)."""
    original = " ".join((text or "").split()).strip(" -•*")
    facts = facts_for(db, user_id, resume)
    candidates: list[BulletCandidate] = []
    ai_texts = ai_tasks.rewrite_bullet_texts(original, role=role, company=company)
    for raw in ai_texts:
        cleaned = apply.strip_filler(_finish(raw), original)
        if cleaned and apply.bullet_problem(cleaned, original, facts) in (None, "dropped_details", "changed_verb", "too_much_added"):
            cand = _candidate(cleaned, original, "ai", facts)
            if cand:
                candidates.append(cand)
    for rule in _rule_rewrites(original):
        cand = _candidate(rule, original, "rule", facts)
        if cand:
            candidates.append(cand)
    picked = _pick(candidates, original)
    note = None
    if not picked:
        note = (
            "This bullet already reads well and nothing more can be said without inventing facts. "
            "Add the outcome yourself, or use “Make achievement-oriented”."
        )
    return BulletSuggestions(original=original, candidates=picked, note=note, ai_used=bool(ai_texts))


def responsibility_to_achievement(db: Session, user_id: uuid.UUID, resume: Resume, text: str) -> BulletSuggestions:
    """Responsibility -> achievement bullet. Without a stated result it ends in ``[result]``:
    the user fills in the real outcome; the app never supplies one."""
    original = " ".join((text or "").split()).strip(" -•*")
    facts = facts_for(db, user_id, resume)
    has_result = rec_mod.has_outcome(original)
    base = apply.tidy_bullet(original).rstrip(".")
    candidates: list[BulletCandidate] = []

    ai_text = ai_tasks.achievement_bullet(original)
    if ai_text:
        ai_text = _finish(ai_text)
        if not has_result and RESULT_PLACEHOLDER not in ai_text:
            ai_text = None  # a qualitative result the input does not state is a claim
        elif has_result and "[" in ai_text:
            ai_text = None
    if ai_text:
        cand = _candidate(ai_text, original, "ai", facts, allow_placeholder=not has_result)
        if cand:
            candidates.append(cand)

    if has_result:
        rule = _finish(base)
    else:
        rule = f"{base}, resulting in {RESULT_PLACEHOLDER}."
    cand = _candidate(rule, original, "rule", facts, allow_placeholder=not has_result)
    if cand:
        candidates.append(cand)
    picked = _pick(candidates, original)
    note = (
        None
        if has_result
        else "Replace [result] with the real outcome (for example time saved, errors avoided or users served). "
        "JobPilot never fills in a number for you."
    )
    if not picked:
        note = "This bullet already states a result."
    return BulletSuggestions(original=original, candidates=picked, note=note, ai_used=bool(ai_text))


# --------------------------------------------------------------------------- text


_DUPLICATE_WORD_RE = re.compile(r"\b(\w+)(\s+\1\b)+", re.IGNORECASE)
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")
_MISSING_SPACE_RE = re.compile(r"([,;:])(?=[A-Za-z])")
_LONE_I_RE = re.compile(r"\bi\b")
_SENTENCE_START_RE = re.compile(r"([.!?]\s+)([a-z])")
_DATE_RE = re.compile(
    r"\b(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?(?:19|20)\d{2}\b", re.IGNORECASE
)
_NAME_RE = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z0-9&.+-]{2,}")


def rule_polish(text: str, field: str) -> str:
    """Deterministic grammar/punctuation fixes that cannot change a fact."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    fixed: list[str] = []
    for line in lines:
        value = " ".join(line.split())
        if not value:
            fixed.append("")
            continue
        value = _DUPLICATE_WORD_RE.sub(lambda m: m.group(1), value)
        value = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", value)
        value = _MISSING_SPACE_RE.sub(r"\1 ", value)
        value = _LONE_I_RE.sub("I", value)
        value = _SENTENCE_START_RE.sub(lambda m: m.group(1) + m.group(2).upper(), value)
        value = re.sub(r"\.{2,}$", ".", value)
        if value[0].isalpha():
            value = value[0].upper() + value[1:]
        if field in ("summary", "description") and value[-1].isalnum():
            value += "."
        fixed.append(value)
    return "\n".join(fixed).strip()


def _new_names(candidate: str, original: str) -> set[str]:
    """Capitalised words (employers, products, places) the original does not contain."""
    source = original.lower()
    found = set()
    for match in _NAME_RE.finditer(candidate):
        word = match.group(0).rstrip(".")
        if word.lower() not in source and word.lower() not in {"i"}:
            found.add(word)
    return found


def text_problem(candidate: str, original: str, facts: apply._Facts | None = None) -> str | None:  # noqa: SLF001
    """Why a model's "improved" text cannot replace ``original``; ``None`` when it is safe.

    Grammar help may not add a number, skill, employer/product name or date that the input
    does not contain, and may not turn into advice or change the length drastically.
    """
    if not candidate.strip():
        return "empty"
    sources: tuple[Any, ...] = (original,)
    if ai_tasks.invented_numbers(candidate, *sources):
        return "invented_number"
    before_skills = {s.lower() for s in extract_skills(original)}
    if any(s.lower() not in before_skills for s in extract_skills(candidate)):
        return "invented_skill"
    before_dates = {d.lower() for d in _DATE_RE.findall(original)}
    if any(d.lower() not in before_dates for d in _DATE_RE.findall(candidate)):
        return "invented_date"
    if _new_names(candidate, original):
        return "invented_name"
    if apply.looks_like_advice(candidate) and not apply.looks_like_advice(original):
        return "advice_text"
    if "[" in candidate and "[" not in original:
        return "placeholder"
    ratio = len(candidate.split()) / max(1, len(original.split()))
    if ratio > 1.6 or ratio < 0.5:
        return "length_changed"
    return None


def improve_text(text: str, field: str) -> ImprovedText:
    """Grammar, clarity and tone only. A model version is used only when it passes
    :func:`text_problem`; otherwise the deterministic fixes stand."""
    original = (text or "").strip()
    rule = rule_polish(original, field)
    polished = ai_tasks.improve_text(rule, field=field)
    if polished:
        polished = rule_polish(polished, field)
        problem = text_problem(polished, original)
        if problem is None and polished != rule:
            return ImprovedText(text=polished, changed=polished != original, source="ai")
        if problem:
            return ImprovedText(text=rule, changed=rule != original, source="rule", reason=problem)
    return ImprovedText(text=rule, changed=rule != original, source="rule")


def draft_summary(db: Session, user_id: uuid.UUID, resume: Resume, parsed: ParsedResume | None = None) -> SummaryDraft:
    """A summary made of facts (most recent title, years, top skills), optionally polished."""
    facts = facts_for(db, user_id, resume, parsed)
    base = apply.build_factual_summary(facts)
    if not base:
        return SummaryDraft(
            text=None,
            reason="not_enough_facts",
        )
    polished = ai_tasks.polish_summary(base)
    if polished and not _same(polished, base):
        problem = apply.summary_problem(polished, facts, check_skills=True) or text_problem(polished, base)
        if problem is None:
            return SummaryDraft(text=polished, source="ai")
        logger.info("Summary polish refused (%s); using the fact-built draft", problem)
        return SummaryDraft(text=base, source="rule", reason=problem)
    return SummaryDraft(text=base, source="rule")


__all__ = [
    "draft_summary",
    "facts_for",
    "improve_text",
    "responsibility_to_achievement",
    "rewrite_bullet",
    "rule_polish",
    "text_problem",
]
