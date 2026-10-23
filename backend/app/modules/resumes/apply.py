"""Apply resume recommendations: review, apply, save as a new version.

The product never puts a fact on a resume that the candidate has not confirmed, so the
plan splits recommendations three ways:

``ADD_SKILL``
    ``MISSING_SKILL`` with ``action="list"`` (the skill is already evidenced in the
    resume text or the profile) is safe and selected by default. ``action="add"`` needs
    the user to confirm "I have used {skill}". ``action="learn"`` is never applicable.
``REPLACE_SUMMARY``
    The ``WEAK_SUMMARY`` suggestion when it has no ``[placeholder]``, no number that is
    not in the resume or profile, and no skill the candidate has not listed; otherwise a
    summary built deterministically from the resume (title, years, top skills).
``REPLACE_BULLET``
    One change per weak bullet of an ``EXPERIENCE_BULLETS`` recommendation. Never
    selected by default, and refused while a ``[...]`` placeholder is left: the outcome
    is the candidate's to supply.

Everything else is a :class:`ManualItem`.

What is edited is ``Resume.parsed_data`` — the structured resume that matching,
autofill and the recommendations read — saved through ``service.update_parsed_data`` so
a new ``ResumeVersion`` is created. The uploaded original file (PDF/DOCX) is not touched.
"""
from __future__ import annotations

import copy
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.exceptions import ConflictError, ValidationFailed
from app.models.enums import Actor
from app.models.resume import Resume
from app.modules.ai import tasks as ai_tasks
from app.modules.ai.schemas import ParsedResume
from app.modules.ai.skills import extract_skills, normalize_skill, normalize_skills
from app.modules.resumes import recommendations as rec_mod
from app.modules.resumes import service
from app.modules.resumes.schemas import (
    AppliedChange,
    ApplicableChange,
    ApplyPlan,
    ApplyRequest,
    ApplyResult,
    ManualItem,
    Recommendation,
    SkippedChange,
)

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r"\[[^\[\]]*\]")
_EXPERIENCE_INDEX_RE = re.compile(r"^experience\[(\d+)\]$")
_BULLET_SUFFIX = "--bullet-"


def has_placeholder(text: str | None) -> bool:
    return bool(text and PLACEHOLDER_RE.search(text))


#: Shared with the recommendation engine: coaching text is never saved as resume content.
looks_like_advice = rec_mod.looks_like_advice


# --------------------------------------------------------------------------- facts


@dataclass
class _Facts:
    """What the candidate has confirmed: the resume and their profile."""

    parsed: dict[str, Any]
    raw_text: str
    inputs: rec_mod.MatchInputs

    def number_sources(self) -> tuple[Any, ...]:
        return (self.parsed, self.raw_text, self.inputs.profile_years, self.inputs.desired_titles)

    def known_skills(self) -> set[str]:
        view = rec_mod.build_view(self.parsed, raw_text=self.raw_text)
        return {s.lower() for s in view.skills} | view.text_skills | {s.lower() for s in self.inputs.base_skills}


def _load_facts(db: Session, user_id: uuid.UUID, resume: Resume) -> _Facts:
    return _Facts(
        parsed=copy.deepcopy(resume.parsed_data or {}),
        raw_text=resume.text_content or "",
        inputs=rec_mod.load_match_inputs(db, user_id),
    )


def summary_problem(text: str, facts: _Facts, *, check_skills: bool) -> str | None:
    """Why ``text`` cannot be saved as the summary, or ``None`` when it is fine."""
    if has_placeholder(text):
        return "placeholder_left"
    if looks_like_advice(text):
        return "advice_text"
    if ai_tasks.invented_numbers(text, *facts.number_sources()):
        return "invented_number"
    if check_skills:
        known = facts.known_skills()
        if any(s.lower() not in known for s in extract_skills(text)):
            return "invented_skill"
    if copies_experience(text, facts.parsed):
        return "copied_bullets"
    return None


#: A run of this many words shared with an experience bullet means the "summary" is pasted bullets.
COPY_RUN_WORDS = 6


def copies_experience(text: str, parsed: dict[str, Any]) -> bool:
    """True when ``text`` repeats a run of words from the experience descriptions."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    if len(words) < COPY_RUN_WORDS:
        return False
    source = " ".join(
        str(entry.get("description") or "") for entry in (parsed.get("experience") or []) if isinstance(entry, dict)
    )
    source_words = re.findall(r"[a-z0-9]+", source.lower())
    runs = {tuple(source_words[i : i + COPY_RUN_WORDS]) for i in range(len(source_words) - COPY_RUN_WORDS + 1)}
    return any(tuple(words[i : i + COPY_RUN_WORDS]) in runs for i in range(len(words) - COPY_RUN_WORDS + 1))


# --------------------------------------------------------------------------- bullet rewrite
#
# A ticked bullet must apply as finished text, so the plan never offers a "[placeholder]".
# The rewrite may only rephrase what the resume already says: stronger verb, clearer scope,
# a qualitative result. It may not add numbers, tools or claims (checked below).

MAX_BULLET_WORDS = 32

#: Weak openers -> strong verbs (deterministic fallback, and a cheap first pass).
_WEAK_OPENERS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), verb)
    for pattern, verb in (
        (r"^(?:was\s+)?responsible\s+for\s+(?:the\s+)?", "Owned "),
        (r"^worked\s+on\s+", "Developed "),
        (r"^worked\s+with\s+", "Collaborated with "),
        (r"^helped\s+(?:to\s+|with\s+)?", "Contributed to "),
        (r"^assisted\s+(?:in\s+|with\s+)?", "Supported "),
        (r"^involved\s+in\s+", "Contributed to "),
        (r"^did\s+", "Delivered "),
        (r"^made\s+", "Built "),
        (r"^wrote\s+", "Developed "),
        (r"^handled\s+", "Managed "),
        (r"^used\s+", "Applied "),
    )
)

_BULLET_CACHE: dict[tuple[str, str], str] = {}
_BULLET_CACHE_MAX = 512

BULLET_SYSTEM = (
    "You lightly edit one resume bullet. Keep every fact, technology and detail from the original, "
    "in the same meaning. You may only: (1) replace the opening verb with a stronger past-tense verb "
    "of the same meaning, and (2) add one short clause at the end saying the purpose or result, when "
    "the bullet or role context clearly implies it. Never claim leadership (led, managed, mentored), "
    "scale (high-traffic, millions, large-scale), awards, numbers, percentages, dates, tools or "
    "technologies that are not already in the text. One sentence, at most 30 words, no brackets."
)


#: Claims a rewrite may not introduce unless the original already makes them.
_CLAIM_WORDS = frozenset(
    """led lead leading headed spearheaded managed manager mentored mentoring supervised directed owned
    architected pioneered award awarded million millions billion thousands high-traffic large-scale
    enterprise-wide global worldwide revenue profit percent record fortune
    significantly dramatically greatly highly vastly massively drastically substantially tremendously
    advanced cutting-edge state-of-the-art world-class best-in-class innovative revolutionary
    transformed transforming seamless seamlessly robust purposes""".split()
)

#: Verbs that already make a strong opening; a rewrite must keep them rather than swap the meaning.
_WEAK_FIRST = frozenset("worked helped assisted involved did made wrote handled used responsible was participated".split())
_STOP = frozenset(
    """a an and the of for to in on with by at from as into via using use used that this these those
    its it their our my your be is are was were has have had or nor but so such which who whom across
    while within without over under per through""".split()
)
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9.+#/-]*", re.IGNORECASE)
#: Share of the original's content words a rewrite must keep.
MIN_KEPT_SHARE = 0.8
#: Content words a rewrite may add (a stronger verb plus a short purpose clause).
MAX_NEW_WORDS = 10


def _content_words(text: str) -> list[str]:
    words = [w.strip(".,;:").lower() for w in _WORD_RE.findall(text or "")]
    return [w for w in words if len(w) > 2 and w not in _STOP]


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tidy_bullet(bullet: str) -> str:
    """Deterministic polish: strong opening verb, capitalised, single trailing period."""
    text = " ".join((bullet or "").split()).strip(" -•*")
    for pattern, verb in _WEAK_OPENERS:
        if pattern.search(text):
            text = pattern.sub(verb, text, count=1)
            break
    if text:
        text = text[0].upper() + text[1:]
        text = text.rstrip(" .;,") + "."
    return text


def bullet_problem(text: str, original: str, facts: _Facts) -> str | None:
    """Why a generated bullet cannot be offered, or ``None`` when it is safe."""
    if not text or has_placeholder(text) or "[" in text or "]" in text:
        return "placeholder"
    if looks_like_advice(text):
        return "advice_text"
    if len(text.split()) > MAX_BULLET_WORDS:
        return "too_long"
    if ai_tasks.invented_numbers(text, original, *facts.number_sources()):
        return "invented_number"
    known = facts.known_skills() | {s.lower() for s in extract_skills(original)}
    if any(s.lower() not in known for s in extract_skills(text)):
        return "invented_skill"
    original_words = _content_words(original)
    new_words = _content_words(text)
    new_stems = {_stem(w) for w in new_words}
    original_stems = {_stem(w) for w in original_words}
    # Keep the original's details (skip its opening verb, which may be swapped for a stronger one).
    body = [w for w in original_words[1:]] or original_words
    if body:
        kept = sum(1 for w in body if _stem(w) in new_stems)
        if kept / len(body) < MIN_KEPT_SHARE:
            return "dropped_details"
    first_original = original_words[0] if original_words else ""
    first_new = new_words[0] if new_words else ""
    if first_original and first_original not in _WEAK_FIRST and _stem(first_new) != _stem(first_original):
        return "changed_verb"
    added = [w for w in new_words if _stem(w) not in original_stems]
    if len(added) > MAX_NEW_WORDS:
        return "too_much_added"
    if any(w in _CLAIM_WORDS and _stem(w) not in original_stems for w in added):
        return "invented_claim"
    return None


def _llm_bullet(bullet: str, entry: dict[str, Any]) -> str | None:
    """Ask the configured model for a rewrite; ``None`` when it is the mock or anything fails."""
    try:
        from app.modules.ai.factory import get_llm_provider

        provider = get_llm_provider()
        if getattr(provider, "name", "") == "mock":
            return None
        context = {
            "title": entry.get("title"),
            "company": entry.get("company"),
            "role_description": str(entry.get("description") or "")[:1200],
            "technologies": entry.get("technologies") or [],
        }
        words = _content_words(bullet)
        first = words[0] if words else ""
        # Same rule as bullet_problem: a strong opening verb must stay, so tell the model so.
        verb_rule = (
            f'Keep the opening word "{bullet.split()[0]}" exactly as it is; only add a short purpose or result clause.'
            if first and first not in _WEAK_FIRST
            else "You may replace the weak opening word with a stronger past-tense verb of the same meaning."
        )
        result = provider.complete_json(
            f"Bullet to rewrite:\n{bullet}\n\nResume context for this role (facts you may use):\n{context}\n\n"
            f"{verb_rule}\n"
            'Return JSON: {"bullet": "<rewritten bullet>"}',
            schema={"type": "object", "properties": {"bullet": {"type": "string"}}, "required": ["bullet"]},
            system=BULLET_SYSTEM,
            max_tokens=200,
        )
        text = " ".join(str((result or {}).get("bullet") or "").split()).strip(" -•*")
        return (text.rstrip(" .;,") + ".") if text else None
    except Exception as exc:  # noqa: BLE001 - the deterministic polish is always available
        logger.info("Bullet rewrite fell back to the deterministic polish: %s", exc)
        return None


#: Generic result clauses small models bolt on ("..., enhancing operational efficiency",
#: "... to deliver robust enterprise applications"). They add words, not information.
_FILLER_VERBS = (
    r"enhanc|improv|ensur|boost|driv|deliver|increas|optimi[sz]|streamlin|maximi[sz]|achiev|support|"
    r"enabl|strengthen|elevat|foster|facilitat|empower|accelerat|provid|offer|contribut|lead|result"
)
_FILLER_NOUNS = (
    r"efficiency|performance|productivity|outcomes?|reliability|quality|value|results?|experiences?|success|"
    r"operations|effectiveness|scalability|growth|satisfaction|applications|solutions|systems?|processes|"
    r"workflows?|insights|decision[- ]making|capabilit(?:y|ies)|excellence|impact|engagement|usability|stability"
)
_FILLER_TAIL_RE = re.compile(
    r"(?:,?\s+(?:(?:in order |so as )?to |thereby |for |while |and |, )?"
    r"(?:" + _FILLER_VERBS + r")\w*\s+(?:[\w-]+\s+){0,6}?"
    r"|,?\s+for\s+(?:better|improved|greater|enhanced|increased|optimal|maximum|higher|stronger|seamless)\s+(?:[\w-]+\s+){0,3}?)"
    r"(?:" + _FILLER_NOUNS + r")\s*\.?\s*$",
    re.IGNORECASE,
)


def strip_filler(text: str | None, original: str) -> str | None:
    """Drop a generic trailing result clause that the original bullet did not contain."""
    if not text:
        return text
    match = _FILLER_TAIL_RE.search(text)
    if not match:
        return text
    tail = match.group(0)
    tail_words = {_stem(w) for w in _content_words(tail)}
    original_words = {_stem(w) for w in _content_words(original)}
    if tail_words and tail_words <= original_words:
        return text  # the clause repeats the bullet's own words: it is real content, keep it
    kept = text[: match.start()].rstrip(" ,;-")
    return (kept + ".") if kept else None


def strengthen_bullet(bullet: str, entry: dict[str, Any], facts: _Facts, suggested: str | None = None) -> str:
    """Finished, placeholder-free rewrite of ``bullet``; never invents facts."""
    from app.modules.ai.factory import get_llm_provider

    try:
        provider_key = f"{getattr(get_llm_provider(), 'name', '')}:{getattr(get_llm_provider(), 'model', '')}"
    except Exception:  # noqa: BLE001
        provider_key = "unknown"
    key = (provider_key, bullet)
    cached = _BULLET_CACHE.get(key)
    if cached is not None:
        return cached

    candidates = [strip_filler(c, bullet) if c else c for c in (suggested, _llm_bullet(bullet, entry))]
    chosen = next(
        (c for c in candidates if c and c.strip().rstrip(".") != bullet.strip().rstrip(".") and bullet_problem(c, bullet, facts) is None),
        None,
    )
    result = chosen or tidy_bullet(bullet)
    if len(_BULLET_CACHE) >= _BULLET_CACHE_MAX:
        _BULLET_CACHE.clear()
    _BULLET_CACHE[key] = result
    return result


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def build_factual_summary(facts: _Facts, skills_hint: list[str] | None = None) -> str | None:
    """A summary made only of resume / profile facts: title, years, top three skills.

    The opening names the most recent title (falling back to the first desired title);
    a desired title that differs is stated as the goal ("Seeking ... roles"), never as
    a role the candidate held.
    """
    view = rec_mod.build_view(facts.parsed, profile_years=facts.inputs.profile_years)
    found = rec_mod.most_recent_entry(view.experience)
    recent_title = (str(found[1].get("title") or "").strip() or None) if found else None
    recent_company = (str(found[1].get("company") or "").strip() or None) if found else None
    target = next((t.strip() for t in facts.inputs.desired_titles if t and t.strip()), None)

    listed = {s.lower(): s for s in view.skills}
    hinted = [listed[s.lower()] for s in (skills_hint or []) if s.lower() in listed]
    skills = list(dict.fromkeys([*hinted, *view.skills]))[:3]

    head = recent_title or target
    if not head and not skills:
        return None
    years = f"{rec_mod._format_years(view.years)} years of experience" if view.years else None
    if head:
        opening = head + (f" with {years}" if years else "")
        if skills:
            opening += f" working with {_join(skills)}"
    else:
        opening = (years[0].upper() + years[1:] + " working with " if years else "Experienced with ") + _join(skills)
    sentences = [opening.rstrip(".") + "."]
    if recent_title and recent_company:
        current = found is not None and rec_mod._is_current(found[1].get("end"))
        sentences.append(f"{'Currently' if current else 'Most recently'} {recent_title} at {recent_company}.")
    if target and recent_title and rec_mod._core_title(target) != rec_mod._core_title(recent_title):
        sentences.append(f"Seeking {target} roles.")
    return " ".join(sentences)


# --------------------------------------------------------------------------- plan


def _manual(rec: Recommendation) -> ManualItem:
    return ManualItem(
        recommendation_id=rec.id, title=rec.title, detail=rec.detail, category=rec.category, priority=rec.priority
    )


def _skill_change(rec: Recommendation, current_skills: set[str]) -> ApplicableChange | None:
    if not rec.skills:
        return None
    skill = normalize_skill(rec.skills[0])
    if not skill or skill.lower() in current_skills:
        return None
    confirm = rec.action == "add"
    return ApplicableChange(
        id=rec.id,
        recommendation_id=rec.id,
        kind="ADD_SKILL",
        title=f"Add {skill} to your skills",
        before=None,
        after=skill,
        target="skills",
        selected_by_default=not confirm,
        requires_confirmation=confirm,
        confirmation_label=f"I have used {skill}" if confirm else None,
        has_placeholders=False,
        estimated_score_gain=rec.estimated_score_gain,
    )


def _summary_change(rec: Recommendation, facts: _Facts) -> ApplicableChange | None:
    current = str(facts.parsed.get("summary") or "").strip() or None
    text = (rec.suggested_text or "").strip()
    if not text or summary_problem(text, facts, check_skills=True):
        text = build_factual_summary(facts, rec.skills) or ""
    if not text or text == current or summary_problem(text, facts, check_skills=True):
        return None
    # A full summary the candidate wrote is never replaced automatically: generated text only
    # fills a missing or thin one. Improving a full summary stays advice ("mention X").
    if current and len(current.split()) >= rec_mod.SUMMARY_MIN_WORDS:
        return None
    return ApplicableChange(
        id=rec.id,
        recommendation_id=rec.id,
        kind="REPLACE_SUMMARY",
        title="Replace your summary" if current else "Add a summary",
        before=current,
        after=text,
        target="summary",
        selected_by_default=True,
        requires_confirmation=False,
        has_placeholders=False,
        estimated_score_gain=rec.estimated_score_gain,
    )


def _bullet_changes(rec: Recommendation, facts: _Facts) -> list[ApplicableChange]:
    index: int | None = None
    for evidence in rec.evidence:
        match = _EXPERIENCE_INDEX_RE.match(evidence.field or "")
        if match:
            index = int(match.group(1))
            break
    experience = facts.parsed.get("experience") if isinstance(facts.parsed.get("experience"), list) else []
    if index is None or index >= len(experience) or not isinstance(experience[index], dict):
        return []
    description = str(experience[index].get("description") or "")
    label = rec_mod._entry_label(experience[index], index)
    weak = [e.label for e in rec.evidence if (e.field or "").endswith(".bullet") and e.label]
    changes: list[ApplicableChange] = []
    for n, bullet in enumerate(weak, start=1):
        if bullet not in description:
            continue
        after = strengthen_bullet(bullet, experience[index], facts)
        if after.strip().rstrip(".") == bullet.strip().rstrip("."):
            continue  # nothing better to offer without inventing facts
        changes.append(
            ApplicableChange(
                id=f"{rec.id}{_BULLET_SUFFIX}{n}",
                recommendation_id=rec.id,
                kind="REPLACE_BULLET",
                title=f"Rewrite a bullet for {label}",
                before=bullet,
                after=after,
                target=f"experience[{index}].description",
                selected_by_default=True,
                requires_confirmation=False,
                confirmation_label=None,
                has_placeholders=False,
                estimated_score_gain=rec.estimated_score_gain if n == 1 else 0.0,
            )
        )
    return changes


def plan_from(resume: Resume, recommendations: list[Recommendation], facts: _Facts) -> ApplyPlan:
    """Pure: turn recommendations into applicable changes and manual items."""
    current_skills = {s.lower() for s in normalize_skills([str(s) for s in facts.parsed.get("skills") or []])}
    changes: list[ApplicableChange] = []
    manual: list[ManualItem] = []
    for rec in recommendations:
        built: list[ApplicableChange] = []
        if rec.category == "MISSING_SKILL" and rec.action in ("list", "add"):
            change = _skill_change(rec, current_skills)
            built = [change] if change else []
        elif rec.category == "WEAK_SUMMARY":
            change = _summary_change(rec, facts)
            built = [change] if change else []
        elif rec.category == "EXPERIENCE_BULLETS":
            built = _bullet_changes(rec, facts)
        if built:
            changes.extend(built)
        else:
            manual.append(_manual(rec))
    return ApplyPlan(resume_id=resume.id, resume_version=int(resume.current_version or 1), changes=changes, manual=manual)


def build_apply_plan(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> ApplyPlan:
    """The applicable changes for one of the user's resumes (404 for anyone else's)."""
    resume = service.get_resume(db, user_id, resume_id)
    recs = service.get_recommendations(db, user_id, resume_id)
    return plan_from(resume, recs.recommendations, _load_facts(db, user_id, resume))


# --------------------------------------------------------------------------- apply


def _clean_text(text: str, *, single_line: bool) -> str:
    cleaned = text.strip()
    if single_line:
        cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def apply_to_parsed(
    parsed: dict[str, Any], changes: list[ApplicableChange]
) -> tuple[dict[str, Any], list[ApplicableChange], list[SkippedChange]]:
    """Pure: apply validated changes to a deep copy of ``parsed``."""
    data = copy.deepcopy(parsed or {})
    applied: list[ApplicableChange] = []
    skipped: list[SkippedChange] = []
    for change in changes:
        if change.kind == "ADD_SKILL":
            skills = [str(s) for s in data.get("skills") or []]
            skill = normalize_skill(change.after)
            if skill.lower() in {s.lower() for s in normalize_skills(skills)}:
                skipped.append(SkippedChange(id=change.id, reason="already_listed"))
                continue
            data["skills"] = [*skills, skill]
        elif change.kind == "REPLACE_SUMMARY":
            data["summary"] = change.after
        elif change.kind == "REPLACE_BULLET":
            match = re.match(r"^experience\[(\d+)\]\.description$", change.target)
            experience = data.get("experience") if isinstance(data.get("experience"), list) else []
            index = int(match.group(1)) if match else -1
            entry = experience[index] if 0 <= index < len(experience) else None
            description = str(entry.get("description") or "") if isinstance(entry, dict) else ""
            if not change.before or change.before not in description:
                skipped.append(SkippedChange(id=change.id, reason="bullet_not_found"))
                continue
            entry["description"] = description.replace(change.before, change.after, 1)  # type: ignore[index]
        applied.append(change)
    return data, applied, skipped


def apply_changes(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID, request: ApplyRequest) -> ApplyResult:
    """Apply the requested plan changes and save them as a new resume version.

    Only ids the client sends are applied, and each is looked up in a plan rebuilt here:
    the client's ``kind``, ``target`` or skill names are never read.
    """
    resume = service.get_resume(db, user_id, resume_id)
    if int(request.resume_version) != int(resume.current_version or 1):
        raise ConflictError(
            "This resume changed since the suggestions were loaded. Review them again.",
            code="stale_plan",
            details={"current_version": int(resume.current_version or 1)},
        )

    facts = _load_facts(db, user_id, resume)
    recs = service.get_recommendations(db, user_id, resume_id)
    plan = plan_from(resume, recs.recommendations, facts)
    by_id = {change.id: change for change in plan.changes}

    chosen: list[ApplicableChange] = []
    seen: set[str] = set()
    for item in request.changes:
        if item.id in seen:
            continue
        seen.add(item.id)
        change = by_id.get(item.id)
        if change is None:
            raise ValidationFailed(
                f"“{item.id}” is not one of this resume's suggestions.", code="unknown_change", details={"id": item.id}
            )
        if change.kind == "ADD_SKILL":
            chosen.append(change)
            continue
        single_line = change.kind == "REPLACE_BULLET"
        after = _clean_text(item.after if item.after is not None else change.after, single_line=single_line)
        if not after:
            raise ValidationFailed("The text cannot be empty.", code="empty_text", details={"id": item.id})
        if has_placeholder(after):
            raise ValidationFailed(
                "Replace the bracketed part with your real result before applying.",
                code="placeholder_left",
                details={"id": item.id},
            )
        if change.kind == "REPLACE_SUMMARY":
            invented = ai_tasks.invented_numbers(after, *facts.number_sources())
            if invented:
                raise ValidationFailed(
                    f"The summary mentions {', '.join(sorted(invented))}, which is not on your resume. "
                    "Use only numbers your resume already states.",
                    code="invented_number",
                    details={"id": item.id, "numbers": sorted(invented)},
                )
        chosen.append(change.model_copy(update={"after": after}))

    new_parsed, applied, skipped = apply_to_parsed(facts.parsed, chosen)
    if applied:
        note = f"Applied {len(applied)} suggestion{'s' if len(applied) != 1 else ''}"
        resume = service.update_parsed_data(db, user_id, resume_id, ParsedResume.model_validate(new_parsed), note=note)
        db.flush()
        db.refresh(resume)  # updated_at is set by the database; the cache key reads it
        audit(
            db,
            action="resume.suggestions_applied",
            message=f"{note} to resume {resume.name} (v{resume.current_version})",
            user_id=user_id,
            actor=Actor.USER,
            meta={
                "resume_id": str(resume.id),
                "version": resume.current_version,
                "applied": [c.id for c in applied],
                "skipped": [s.id for s in skipped],
            },
        )
    rec_mod.invalidate_resume(resume.id)
    fresh = service.get_recommendations(db, user_id, resume_id, refresh=True)
    logger.info("Applied %d suggestions to resume %s (skipped %d)", len(applied), resume.id, len(skipped))
    return ApplyResult(
        resume=service.resume_to_read(resume),
        applied=[AppliedChange(id=c.id, kind=c.kind, title=c.title) for c in applied],
        skipped=skipped,
        recommendations=fresh,
    )


__all__ = [
    "apply_changes",
    "apply_to_parsed",
    "build_apply_plan",
    "build_factual_summary",
    "has_placeholder",
    "plan_from",
    "summary_problem",
]
