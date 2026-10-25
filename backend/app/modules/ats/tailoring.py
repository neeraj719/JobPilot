"""The AI pass of a tailoring run: rewrites that are *applied* to the tailored copy.

``targets.tailor`` (and the one-screen ``quick_tailor``) first build the tailored copy with the
rule-safe suggestions (``service.auto_optimize``), then analyse it with ``polish_task =
tailor_resume``. When a model answers that task (workflow ``generation``), the analysis stays
``RUNNING`` and :func:`tailor_pass` runs in the background thread instead of the plain polish:

1. **Summary** - one rewrite toward the posting's role (:func:`model_summary`), from the
   candidate's own facts only; checked by :func:`summary_problem` (``resumes.apply.summary_problem``
   + at most :data:`SUMMARY_MAX_WORDS` words, no claim word, name or the target title as a held
   title that the resume does not show; skills only from ``facts``).
2. **Bullets** - up to :data:`TAILOR_MAX_BULLETS`, the entries whose technologies overlap the
   posting first (:func:`plan_bullets`); each checked by ``resumes.apply.bullet_problem`` plus
   a stricter skill rule (a rewrite may only name tools its own entry names).
3. **Skills order** - the posting's skills first (``suggestions.reorder_skills``; no model).

Every step is an ``OptimizationSuggestion`` row of the analysis (``checks.tailor_pass``,
``checks.tailor_state`` pending -> accepted | rejected | unchanged | not_run), so the progress
poll can show "AI rewrite (n of m)". A rejected candidate is recorded (``checks.ai_rejected``)
and never applied. The accepted ones are applied **in one go** as a new version of the tailored
copy (``change_source`` AI), their rows marked APPLIED with ``checks.applied_to_resume_id``, and
a fresh analysis (no further polish) gives the final estimate. The source resume is never read
for writing. A model error leaves the rule-based copy as it is and puts the error on the analysis
(``service._finish(error=...)``); ``POST /ats/analyses/{id}/polish {task: tailor_resume}`` retries.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.audit import audit
from app.models.ats import AtsAnalysis, JobDescriptionSnapshot, JobTarget, OptimizationSuggestion
from app.models.enums import Actor, AtsAnalysisStatus, ResumeChangeSource, SuggestionKind, SuggestionStatus
from app.models.resume import Resume
from app.modules.ai.schemas import ParsedResume
from app.modules.ai.skills import extract_skills, normalize_skills
from app.modules.ats import llm
from app.modules.ats.schemas import StructuredJD
from app.modules.ats.suggestions import jd_skill_order, make_facts, reorder_skills
from app.modules.resumes import apply as resume_apply
from app.modules.resumes import recommendations as rec_mod

logger = logging.getLogger(__name__)

#: Bullets one tailoring pass rewrites (a local model takes 1-10 s each).
TAILOR_MAX_BULLETS = 12
#: Longest summary the pass accepts.
SUMMARY_MAX_WORDS = 60
#: Bullets shorter than this are left alone (nothing to tailor in "Built tools.").
MIN_BULLET_WORDS = 4

_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}
_BULLET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"bullet": {"type": "string"}},
    "required": ["bullet"],
}

SUMMARY_SYSTEM = (
    "You rewrite a resume summary so it speaks to one target role. Use only the candidate facts you are "
    "given: their job titles, employers, years of experience and skills. Never add a skill, tool, number, "
    "employer, job title, degree, award or claim that is not in the facts. Do not present the target role "
    "as a title the candidate held; you may say they are seeking it. Write 2-3 sentences of 35 to 55 words, "
    "third person without pronouns, no brackets, no placeholders."
)

BULLET_TAILOR_RULES = (
    "Where the bullet already shows the work, prefer the posting's own wording for it. Never add a tool, "
    "technology, number or claim the bullet does not already contain."
)

#: Words that put a target title in the future ("Seeking Senior Backend Engineer roles").
_GOAL_RE = re.compile(r"\b(seek\w*|looking for|target\w*|interested in|toward\w*|aim\w*|aspir\w*|pursu\w*|transition\w*)\b", re.I)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#&.-]*")
_EXPERIENCE_PATH = re.compile(r"^experience\[(\d+)\]\.description$")


# --------------------------------------------------------------------------- planning (pure)


def _skills_in(text: str) -> set[str]:
    return {s.lower() for s in extract_skills(text or "")}


def _entry_text(entry: dict[str, Any]) -> str:
    return " ".join([str(entry.get("description") or ""), *[str(t) for t in entry.get("technologies") or []]])


def plan_bullets(parsed: dict[str, Any], jd: StructuredJD, *, limit: int = TAILOR_MAX_BULLETS) -> list[tuple[int, str]]:
    """``(experience index, bullet)`` to rewrite: entries overlapping the posting's skills first,
    then the bullets that name those skills, then resume order. Pure."""
    wanted = set(jd_skill_order(jd))
    experience = parsed.get("experience") if isinstance(parsed.get("experience"), list) else []
    rows: list[tuple[int, int, int, int, str]] = []
    for index, entry in enumerate(experience):
        if not isinstance(entry, dict):
            continue
        description = str(entry.get("description") or "")
        entry_overlap = len(_skills_in(_entry_text(entry)) & wanted)
        for position, bullet in enumerate(rec_mod.split_bullets(description)):
            if len(bullet.split()) < MIN_BULLET_WORDS or bullet not in description:
                continue
            rows.append((-entry_overlap, -len(_skills_in(bullet) & wanted), index, position, bullet))
    rows.sort(key=lambda row: row[:4])
    return [(row[2], row[4]) for row in rows[: max(0, limit)]]


def _source_text(facts: Any) -> str:
    """Everything the candidate has stated: the resume (structured + raw text) and the profile."""
    inputs = facts.inputs
    parts = [
        json.dumps(facts.parsed or {}, ensure_ascii=False, default=str),
        facts.raw_text or "",
        " ".join(str(t) for t in getattr(inputs, "desired_titles", []) or []),
        " ".join(str(s) for s in getattr(inputs, "base_skills", []) or []),
    ]
    return "\n".join(parts)


def summary_problem(text: str, facts: Any, jd: StructuredJD) -> str | None:
    """Why a generated tailoring summary cannot be applied, or ``None`` when it is safe."""
    if not text or not text.strip():
        return "empty"
    if len(text.split()) > SUMMARY_MAX_WORDS:
        return "too_long"
    if "[" in text or "]" in text:
        return "placeholder_left"
    problem = resume_apply.summary_problem(text, facts, check_skills=True)
    if problem:
        return problem
    source = _source_text(facts)
    source_lower = source.lower()
    source_stems = {resume_apply._stem(w) for w in resume_apply._content_words(source)}
    for word in resume_apply._content_words(text):
        if word in resume_apply._CLAIM_WORDS and resume_apply._stem(word) not in source_stems:
            return "invented_claim"
    allowed = {t.lower().strip(".") for t in _TOKEN_RE.findall(f"{jd.title or ''} {jd.company or ''}")}
    source_tokens = {t.lower().strip(".") for t in _TOKEN_RE.findall(source)}
    for sentence in _SENTENCE_RE.split(text.strip()):
        tokens = _TOKEN_RE.findall(sentence)
        for token in tokens[1:]:  # the first word of a sentence is capitalised anyway
            key = token.lower().strip(".")
            if token[0].isupper() and key not in source_tokens and key not in allowed:
                return "invented_name"
    title = " ".join((jd.title or "").lower().split())
    if title and title not in source_lower:
        for sentence in _SENTENCE_RE.split(text.strip()):
            if title in " ".join(sentence.lower().split()) and not _GOAL_RE.search(sentence):
                return "claimed_title"
    return None


def bullet_problem(text: str, original: str, entry: dict[str, Any], facts: Any) -> str | None:
    """``resumes.apply.bullet_problem`` plus: a tool may only be named when its own entry names it."""
    problem = resume_apply.bullet_problem(text, original, facts)
    if problem:
        return problem
    allowed = _skills_in(original) | _skills_in(_entry_text(entry))
    if any(skill not in allowed for skill in _skills_in(text)):
        return "invented_skill"
    return None


# --------------------------------------------------------------------------- model calls


def _summary_facts(facts: Any, jd: StructuredJD) -> dict[str, Any]:
    view = rec_mod.build_view(facts.parsed, raw_text=facts.raw_text, profile_years=facts.inputs.profile_years)
    found = rec_mod.most_recent_entry(view.experience)
    known = facts.known_skills()
    listed = [str(s) for s in view.skills]
    matching = [s for s in normalize_skills(jd.required_skills + jd.preferred_skills) if s.lower() in known]
    titles = [str(e.get("title") or "").strip() for e in view.experience if isinstance(e, dict) and e.get("title")]
    employers = [str(e.get("company") or "").strip() for e in view.experience if isinstance(e, dict) and e.get("company")]
    return {
        "most_recent_title": (str(found[1].get("title") or "").strip() or None) if found else None,
        "most_recent_employer": (str(found[1].get("company") or "").strip() or None) if found else None,
        "titles_held": list(dict.fromkeys(titles))[:4],
        "employers": list(dict.fromkeys(employers))[:4],
        "years_of_experience": round(view.years, 1) if view.years else None,
        "skills_matching_the_role": matching[:8],
        "other_skills": [s for s in listed if s.lower() not in {m.lower() for m in matching}][:6],
        "target_role": jd.title,
        "target_company": jd.company,
    }


def model_summary(current: str, facts: Any, jd: StructuredJD, task: str = llm.TASK_TAILOR) -> str | None:
    """One summary rewrite toward the role; ``None`` when the model returns nothing."""
    prompt = (
        f"Current summary:\n{llm.wrap_untrusted('RESUME SUMMARY', current or '(none)', max_chars=1200)}\n\n"
        f"Candidate facts (the only facts you may use) and the target role:\n"
        f"{llm.wrap_untrusted('CANDIDATE FACTS', json.dumps(_summary_facts(facts, jd), ensure_ascii=False), max_chars=1800)}\n\n"
        "Rewrite the summary for the target role: lead with the facts that match it, keep it truthful.\n"
        'Return JSON: {"summary": "<rewritten summary>"}'
    )
    answer = llm.llm_json(task, prompt, schema=_SUMMARY_SCHEMA, system=llm.system_prompt(SUMMARY_SYSTEM), max_tokens=260)
    text = " ".join(str((answer or {}).get("summary") or "").split()).strip(" -•*\"'")
    return text or None


def model_bullet(bullet: str, entry: dict[str, Any], jd: StructuredJD, task: str = llm.TASK_TAILOR) -> str | None:
    """One bullet rewrite toward the posting; ``None`` when the model returns nothing."""
    words = resume_apply._content_words(bullet)
    first = words[0] if words else ""
    verb_rule = (
        f'Keep the opening word "{bullet.split()[0]}" exactly as it is; only add a short purpose or result clause.'
        if first and first not in resume_apply._WEAK_FIRST
        else "You may replace the weak opening word with a stronger past-tense verb of the same meaning."
    )
    wanted = set(jd_skill_order(jd))
    shown = [s for s in normalize_skills(jd.required_skills + jd.preferred_skills) if s.lower() in _skills_in(_entry_text(entry)) and s.lower() in wanted]
    context = {
        "title": entry.get("title"),
        "company": entry.get("company"),
        "technologies": entry.get("technologies") or [],
        "target_role": jd.title,
        "posting_terms_this_role_shows": shown[:8],
    }
    prompt = (
        f"Bullet to rewrite:\n{llm.wrap_untrusted('RESUME BULLET', bullet, max_chars=600)}\n\n"
        f"Role facts you may use:\n{llm.wrap_untrusted('ROLE CONTEXT', json.dumps(context, ensure_ascii=False), max_chars=900)}\n\n"
        f"{verb_rule}\n{BULLET_TAILOR_RULES}\nReturn JSON: {{\"bullet\": \"<rewritten bullet>\"}}"
    )
    answer = llm.llm_json(task, prompt, schema=_BULLET_SCHEMA, system=llm.system_prompt(resume_apply.BULLET_SYSTEM), max_tokens=200)
    text = " ".join(str((answer or {}).get("bullet") or "").split()).strip(" -•*")
    return (text.rstrip(" .;,") + ".") if text else None


# --------------------------------------------------------------------------- the pass


@dataclass
class Step:
    suggestion_id: uuid.UUID
    kind: str  # "summary" | "bullet"
    target_path: str
    before: str
    entry: dict[str, Any] = field(default_factory=dict)


def _same(a: str | None, b: str | None) -> bool:
    return (a or "").strip().rstrip(".").lower() == (b or "").strip().rstrip(".").lower()


def _prepare_steps(db: Any, analysis: AtsAnalysis, parsed: dict[str, Any], jd: StructuredJD) -> list[Step]:
    """The summary + bullet steps as suggestion rows (reused when the analysis already has one)."""
    existing: dict[tuple[str, str, str], OptimizationSuggestion] = {}
    for row in sorted(analysis.suggestions, key=lambda s: s.ordinal):
        kind = str(getattr(row.kind, "value", row.kind))
        existing.setdefault((kind, row.target_path or "", (row.before or "").strip()), row)
    ordinal = max((s.ordinal for s in analysis.suggestions), default=0)
    steps: list[Step] = []

    def add(kind: SuggestionKind, path: str, before: str, title: str, step_kind: str, entry: dict[str, Any]) -> None:
        nonlocal ordinal
        row = existing.get((kind.value, path, before.strip()))
        if row is not None and row.status in (SuggestionStatus.APPLIED, SuggestionStatus.EDITED):
            return
        if row is None:
            ordinal += 1
            row = OptimizationSuggestion(
                analysis_id=analysis.id, ordinal=ordinal, kind=kind, title=title[:300],
                rationale="The AI model is rewriting this for the posting; JobPilot's rules check the result.",
                target_path=path, before=before or None, after=None, safe=False, requires_confirmation=False,
                estimated_gain=0.0, status=SuggestionStatus.PROPOSED, checks={"tailor_created": True},
            )
            db.add(row)
        elif (row.checks or {}).get("tailor_created"):
            row.status = SuggestionStatus.PROPOSED
        checks = {k: v for k, v in (row.checks or {}).items() if k not in ("ai_rejected", "ai_candidate")}
        checks.update({"tailor_pass": True, "tailor_state": "pending"})
        row.checks = checks
        db.flush()
        steps.append(Step(suggestion_id=row.id, kind=step_kind, target_path=path, before=before, entry=entry))

    summary = str(parsed.get("summary") or "").strip()
    has_facts = bool(summary or parsed.get("skills") or parsed.get("experience"))
    if has_facts:
        add(SuggestionKind.REPLACE_SUMMARY, "summary", summary, "Summary rewritten for the role", "summary", {})
    experience = parsed.get("experience") if isinstance(parsed.get("experience"), list) else []
    for index, bullet in plan_bullets(parsed, jd):
        entry = experience[index] if isinstance(experience[index], dict) else {}
        label = rec_mod._entry_label(entry, index)
        add(
            SuggestionKind.REPLACE_BULLET, f"experience[{index}].description", bullet, f"Bullet rewritten for {label}",
            "bullet", entry,
        )
    return steps


def _generate(step: Step, facts: Any, jd: StructuredJD, task: str) -> tuple[str | None, str | None]:
    """``(candidate, problem)``; ``candidate`` None = the model offered nothing new. Raises on model errors."""
    if step.kind == "summary":
        candidate = model_summary(step.before, facts, jd, task)
        if not candidate or _same(candidate, step.before):
            return None, None
        return candidate, summary_problem(candidate, facts, jd)
    candidate = resume_apply.strip_filler(model_bullet(step.before, step.entry, jd, task), step.before)
    if not candidate or _same(candidate, step.before):
        return None, None
    return candidate, bullet_problem(candidate, step.before, step.entry, facts)


_ACCEPTED_RATIONALE = {
    "summary": (
        "Rewritten for this role by the AI model and checked by JobPilot's rules: only your own titles, employers, "
        "years and skills; no new number, skill or claim."
    ),
    "bullet": (
        "Rewritten for this posting by the AI model and checked by JobPilot's rules: every fact of the original is "
        "kept and no number, tool or claim was added."
    ),
}


def _record(step: Step, analysis_id: uuid.UUID, candidate: str | None, problem: str | None, done: int, total: int) -> bool:
    """Store one step's outcome; True when the candidate was accepted."""
    from app.core.database import session_scope

    with session_scope() as db:
        row = db.get(OptimizationSuggestion, step.suggestion_id)
        analysis = db.get(AtsAnalysis, analysis_id)
        if row is None or analysis is None:
            return False
        checks = dict(row.checks or {})
        checks["ai_attempted"] = True
        created = bool(checks.get("tailor_created"))
        accepted = False
        if candidate is None:
            checks["tailor_state"] = "unchanged"
        elif problem:
            checks.update({"tailor_state": "rejected", "ai_rejected": problem, "ai_candidate": candidate[:600]})
        else:
            checks.update({"tailor_state": "accepted", "ai_polished": True, "method": "model", "rules_after": row.after})
            row.after = candidate
            row.safe = True
            row.rationale = _ACCEPTED_RATIONALE[step.kind]
            accepted = True
        if not accepted and created:
            row.status = SuggestionStatus.IGNORED
        row.checks = checks
        analysis.progress = min(95, 40 + int(55 * done / max(1, total)))
        return accepted


def _settle_unapplied(analysis_id: uuid.UUID, step_ids: list[uuid.UUID], state: str) -> None:
    """Rows of a pass that did not apply (error or a moved resume): never left looking pending/applied."""
    from app.core.database import session_scope

    with session_scope() as db:
        for sid in step_ids:
            row = db.get(OptimizationSuggestion, sid)
            if row is None:
                continue
            checks = dict(row.checks or {})
            if checks.get("tailor_state") in ("pending", "accepted"):
                checks["tailor_state"] = state
                if checks.get("tailor_created"):
                    row.status = SuggestionStatus.IGNORED
                row.checks = checks


def _apply(analysis_id: uuid.UUID, accepted: list[Step], task: str) -> str | None:
    """Apply the accepted rewrites (+ the skills order) as one new version; returns an error or None."""
    from app.core.database import session_scope
    from app.modules.ats import service as ats
    from app.modules.resumes import service as resumes

    provider, model = llm.model_info(task)
    with session_scope() as db:
        analysis = db.get(AtsAnalysis, analysis_id)
        if analysis is None:
            return None
        resume = db.get(Resume, analysis.resume_id)
        snapshot = db.get(JobDescriptionSnapshot, analysis.snapshot_id) if analysis.snapshot_id else None
        if resume is None or snapshot is None or int(resume.current_version or 1) != analysis.resume_version:
            return "The tailored resume changed while the AI was rewriting it, so nothing was applied."
        jd = StructuredJD.model_validate(snapshot.structured or {})
        data = copy.deepcopy(resume.parsed_data or {})
        rows = {s.id: s for s in analysis.suggestions}
        applied: list[OptimizationSuggestion] = []
        for step in accepted:
            row = rows.get(step.suggestion_id)
            if row is None or not row.after:
                continue
            if step.kind == "summary":
                if not _same(str(data.get("summary") or ""), step.before):
                    continue
                data["summary"] = row.after
            else:
                match = _EXPERIENCE_PATH.match(step.target_path)
                experience = data.get("experience") if isinstance(data.get("experience"), list) else []
                index = int(match.group(1)) if match else -1
                entry = experience[index] if 0 <= index < len(experience) else None
                description = str(entry.get("description") or "") if isinstance(entry, dict) else ""
                if not step.before or step.before not in description:
                    continue
                entry["description"] = description.replace(step.before, row.after, 1)  # type: ignore[index]
            applied.append(row)
        skills = [str(s) for s in data.get("skills") or []]
        ordered = reorder_skills(skills, jd)
        reordered = ordered != skills
        data["skills"] = ordered
        if not applied and not reordered:
            return None
        target = db.get(JobTarget, analysis.job_target_id) if analysis.job_target_id else None
        label = " · ".join(p for p in ((target.company_name, target.role_title) if target else (snapshot.company, snapshot.title)) if p)
        count = len(applied) + (1 if reordered else 0)
        note = f"AI tailoring for {label or 'this job'}: {count} change{'s' if count != 1 else ''}"
        resume = resumes.update_parsed_data(
            db, analysis.user_id, resume.id, ParsedResume.model_validate(data), note=note[:500], change_source=ResumeChangeSource.AI
        )
        db.flush()
        db.refresh(resume)
        version = int(resume.current_version)
        for row in applied:
            row.status = SuggestionStatus.APPLIED
            row.applied_version = version
            row.checks = {**(row.checks or {}), "tailor_state": "applied", "applied_to_resume_id": str(resume.id)}
        if reordered:
            ordinal = max((s.ordinal for s in analysis.suggestions), default=0) + 1
            db.add(
                OptimizationSuggestion(
                    analysis_id=analysis.id, ordinal=ordinal, kind=SuggestionKind.REORDER_SECTION,
                    title="Put the posting's skills first", target_path="skills", before=", ".join(skills),
                    after=", ".join(ordered), safe=True, requires_confirmation=False, estimated_gain=0.0,
                    rationale="Moves the skills this posting asks for to the front of your skills list. Nothing is added or removed.",
                    status=SuggestionStatus.APPLIED, applied_version=version,
                    checks={"permutation": True, "tailor_pass": True, "tailor_created": True, "tailor_state": "applied",
                            "applied_to_resume_id": str(resume.id)},
                )
            )
        if target is not None:
            target.tailored_resume_version = version
            db.add(target)
        rec_mod.invalidate_resume(resume.id)
        audit(
            db,
            action="ats.tailor_ai_applied",
            message=f"{note} (resume {resume.name} v{version})",
            user_id=analysis.user_id,
            actor=Actor.SYSTEM,
            meta={
                "analysis_id": str(analysis.id),
                "resume_id": str(resume.id),
                "version": version,
                "applied": [str(r.id) for r in applied],
                "skills_reordered": reordered,
                "target_id": str(target.id) if target else None,
                "provider": provider,
                "model": model,
            },
        )
        fresh = ats.run_analysis(
            db, analysis.user_id, resume, snapshot, target=target, weights=analysis.weights, previous=analysis,
            schedule_polish=False,
        )
        fresh.ai_provider = provider
        fresh.ai_model = model
        db.add(fresh)
    return None


def tailor_pass(analysis_id: uuid.UUID, *, task: str = llm.TASK_TAILOR) -> None:
    """Run the AI tailoring of a tailored copy's analysis (see the module docstring)."""
    from app.core.database import session_scope
    from app.modules.ats import service as ats

    started = time.monotonic()
    steps: list[Step] = []
    facts: Any = None
    jd = StructuredJD()
    with session_scope() as db:
        analysis = db.get(AtsAnalysis, analysis_id)
        if analysis is None or analysis.status != AtsAnalysisStatus.RUNNING:
            return
        resume = db.get(Resume, analysis.resume_id)
        snapshot = db.get(JobDescriptionSnapshot, analysis.snapshot_id) if analysis.snapshot_id else None
        stale = resume is None or snapshot is None or int(resume.current_version or 1) != analysis.resume_version
        if not stale:
            parsed = copy.deepcopy(resume.parsed_data or {})
            jd = StructuredJD.model_validate(snapshot.structured or {})
            facts = make_facts(parsed, resume.text_content or "", rec_mod.load_match_inputs(db, analysis.user_id))
            steps = _prepare_steps(db, analysis, parsed, jd)
    if stale:
        ats._finish(analysis_id, started, error="The resume changed before the AI could rewrite it.", task=task)
        return

    error: str | None = None
    accepted: list[Step] = []
    for done, step in enumerate(steps, start=1):
        try:
            candidate, problem = _generate(step, facts, jd, task)
        except Exception as exc:  # noqa: BLE001 - the rule-based copy stands
            error = ats._safe_error(exc, prefix="The AI rewrite did not run")
            logger.info("Tailoring pass %s stopped: %s", analysis_id, error)
            break
        if _record(step, analysis_id, candidate, problem, done, len(steps)):
            accepted.append(step)
    ids = [s.suggestion_id for s in steps]
    if error is None:
        try:
            error = _apply(analysis_id, accepted, task)
        except Exception as exc:  # noqa: BLE001 - never leave the analysis RUNNING
            logger.exception("Tailoring pass %s could not apply its rewrites", analysis_id)
            error = ats._safe_error(exc, prefix="The AI rewrites could not be applied")
    if error is not None:
        _settle_unapplied(analysis_id, ids, "not_run")
    ats._finish(analysis_id, started, error=error, task=task)


__all__ = [
    "SUMMARY_MAX_WORDS",
    "TAILOR_MAX_BULLETS",
    "bullet_problem",
    "model_bullet",
    "model_summary",
    "plan_bullets",
    "summary_problem",
    "tailor_pass",
]
