"""ATS analyses: run, persist, apply, ignore, auto-optimize, undo - and the background polish.

Everything is scoped to the user: another user's analysis, resume, snapshot or target is a
404. Services never commit; ``get_db`` (requests) and ``session_scope`` (the polish thread)
own the transactions.

Flow
    ``create_analysis`` resolves the job description into a snapshot, scores the resume
    deterministically (``scoring``), builds the suggestions (``suggestions``) and stores both.
    That is the whole answer, synchronously. When a real model is configured and there are
    bullets to rewrite, the analysis is left ``RUNNING`` and a daemon thread asks the model for
    better rewrites, keeps only the ones that pass ``resumes.apply.bullet_problem`` and marks
    the analysis ``DONE``. A failed polish never fails the analysis.

Applying
    Only ids the client sends are applied, each looked up in the stored suggestions (the
    client's kind/target/text are never trusted; ``edits`` are the user's own words and are
    checked for placeholders and - in a summary - numbers the resume does not contain). The
    result is saved through ``resumes.service.update_parsed_data`` as a new version
    (``change_source`` AI, or USER when the user edited a text) and the analysis is re-run on
    that version.
"""
from __future__ import annotations

import copy
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.models.ats import AtsAnalysis, JobDescriptionSnapshot, JobTarget, OptimizationSuggestion
from app.models.base import utcnow
from app.models.enums import (
    Actor,
    AtsAnalysisStatus,
    JdSource,
    JobTargetStatus,
    ResumeChangeSource,
    ResumeKind,
    ResumeParseStatus,
    SuggestionKind,
    SuggestionStatus,
)
from app.models.job import Job
from app.models.profile import UserProfile
from app.models.resume import Resume, ResumeVersion
from app.modules.ai.schemas import ParsedResume
from app.modules.ai.skills import normalize_skills
from app.modules.ats import jd as jd_mod
from app.modules.ats import llm
from app.modules.ats.schemas import (
    AnalysisCreate,
    AnalysisListItem,
    AnalysisRead,
    AppliedItem,
    ApplyRequest,
    ApplyResult,
    AutoOptimizeResult,
    CategoryScore,
    Explanation,
    IgnoreRequest,
    JdInput,
    KeywordHit,
    KeywordMiss,
    ParseRisk,
    SkippedItem,
    SnapshotSummary,
    StructuredJD,
    SuggestionRead,
    UndoResult,
    WeakItem,
)
from app.modules.ats.scoring import METHODOLOGY_VERSION, resolve_weights, score_resume
from app.modules.ats.suggestions import apply_to_parsed, build_drafts, invented_numbers, make_facts
from app.modules.resumes import apply as resume_apply
from app.modules.resumes import recommendations as rec_mod
from app.modules.resumes import service as resumes

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\[[^\[\]]*\]")
#: Bullets the background polish rewrites per analysis (a local model takes 1-10 s each).
POLISH_MAX_BULLETS = 6
#: How long the polish thread waits for the request that created the analysis to commit.
POLISH_START_TIMEOUT = 15.0


# --------------------------------------------------------------------------- profile facts


@dataclass
class ProfileFacts:
    skills: set[str]
    years: float | None
    text: str
    inputs: rec_mod.MatchInputs


def load_profile(db: Session, user_id: uuid.UUID) -> ProfileFacts:
    """The user's verified facts: profile skills, years and free text (projects, achievements...)."""
    inputs = rec_mod.load_match_inputs(db, user_id)
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == user_id)).first()
    parts: list[str] = []
    if profile is not None:
        parts += [profile.summary or "", profile.headline or ""]
        for key in ("projects", "achievements", "previous_companies", "certifications"):
            for item in getattr(profile, key, None) or []:
                if isinstance(item, dict):
                    parts += [str(v) for v in item.values() if isinstance(v, (str, int, float))]
                elif isinstance(item, str):
                    parts.append(item)
    return ProfileFacts(
        skills={s.lower() for s in normalize_skills(list(inputs.base_skills))},
        years=inputs.profile_years,
        text="\n".join(p for p in parts if p),
        inputs=inputs,
    )


# --------------------------------------------------------------------------- lookups


def get_analysis(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID) -> AtsAnalysis:
    analysis = db.scalar(select(AtsAnalysis).where(AtsAnalysis.id == analysis_id, AtsAnalysis.user_id == user_id))
    if analysis is None:
        raise NotFoundError("Analysis not found")
    return analysis


def get_snapshot(db: Session, user_id: uuid.UUID, snapshot_id: uuid.UUID) -> JobDescriptionSnapshot:
    snapshot = db.scalar(
        select(JobDescriptionSnapshot).where(JobDescriptionSnapshot.id == snapshot_id, JobDescriptionSnapshot.user_id == user_id)
    )
    if snapshot is None:
        raise NotFoundError("Job description not found")
    return snapshot


def get_target(db: Session, user_id: uuid.UUID, target_id: uuid.UUID) -> JobTarget:
    target = db.scalar(select(JobTarget).where(JobTarget.id == target_id, JobTarget.user_id == user_id))
    if target is None:
        raise NotFoundError("Job target not found")
    return target


def target_label(target: JobTarget | None, snapshot: JobDescriptionSnapshot | None) -> str:
    company = (target.company_name if target else None) or (snapshot.company if snapshot else None)
    role = (target.role_title if target else None) or (snapshot.title if snapshot else None)
    label = " ".join(p for p in (company, role) if p)
    return label or "this job description"


# --------------------------------------------------------------------------- snapshots


def _skill_changes(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, list[str]]:
    previous = previous or {}

    def diff(key: str) -> tuple[list[str], list[str]]:
        before = {s.lower(): s for s in previous.get(key) or []}
        after = {s.lower(): s for s in current.get(key) or []}
        return [after[k] for k in after if k not in before], [before[k] for k in before if k not in after]

    added_req, removed_req = diff("required_skills")
    added_pref, removed_pref = diff("preferred_skills")
    return {
        "added_required": added_req,
        "removed_required": removed_req,
        "added_preferred": added_pref,
        "removed_preferred": removed_pref,
    }


def create_snapshot(
    db: Session,
    user_id: uuid.UUID,
    *,
    text: str,
    source: JdSource,
    structured: StructuredJD,
    url: str | None = None,
    title: str | None = None,
    company: str | None = None,
    target: JobTarget | None = None,
) -> tuple[JobDescriptionSnapshot, bool]:
    """Store a snapshot; returns ``(snapshot, created)``. An unchanged text on a target is not stored twice."""
    digest = jd_mod.text_sha256(text)
    previous: JobDescriptionSnapshot | None = None
    if target is not None and target.latest_snapshot_id:
        previous = db.get(JobDescriptionSnapshot, target.latest_snapshot_id)
        if previous is not None and previous.text_sha256 == digest:
            return previous, False
    data = structured.model_dump(mode="json")
    snapshot = JobDescriptionSnapshot(
        user_id=user_id,
        job_target_id=target.id if target else None,
        source=source,
        url=(url or None),
        fetched_at=utcnow() if source in (JdSource.URL, JdSource.BOARD) else None,
        title=(title or structured.title or "")[:255] or None,
        company=(company or structured.company or (target.company_name if target else "") or "")[:255] or None,
        raw_text=text,
        structured=data,
        text_sha256=digest,
        changed_from_previous=previous is not None,
        changes=_skill_changes(previous.structured if previous else None, data) if previous else {},
    )
    db.add(snapshot)
    db.flush()
    if target is not None:
        target.latest_snapshot_id = snapshot.id
        target.required_skills = list(structured.required_skills)
        if not target.location and structured.location:
            target.location = structured.location[:255]
        if target.work_mode is None and structured.work_mode is not None:
            target.work_mode = structured.work_mode
        if target.deadline is None and structured.deadline is not None:
            target.deadline = structured.deadline
        db.add(target)
    audit(
        db,
        action="ats.snapshot_created",
        message=f"Job description saved ({source.value.lower()}) for {target_label(target, snapshot)}",
        user_id=user_id,
        actor=Actor.USER,
        meta={
            "snapshot_id": str(snapshot.id),
            "target_id": str(target.id) if target else None,
            "source": source.value,
            "changed": snapshot.changed_from_previous,
        },
    )
    return snapshot, True


def snapshot_from_text(
    db: Session,
    user_id: uuid.UUID,
    *,
    text: str,
    source: JdSource,
    title: str | None = None,
    company: str | None = None,
    url: str | None = None,
    location: str | None = None,
    structured: StructuredJD | None = None,
    use_ai: bool = False,
    target: JobTarget | None = None,
) -> tuple[JobDescriptionSnapshot, bool]:
    clean = jd_mod.require_readable(jd_mod.normalize_jd_text(text))
    built = jd_mod.build_structured(
        clean, title=title, company=company, location=location, use_ai=use_ai, client_structured=structured
    )
    return create_snapshot(
        db, user_id, text=clean, source=source, structured=built, url=url, title=title, company=company, target=target
    )


def snapshot_from_job(db: Session, user_id: uuid.UUID, job: Job, *, target: JobTarget | None = None) -> tuple[JobDescriptionSnapshot, bool]:
    company = job.company.name if getattr(job, "company", None) is not None else None
    structured_seed: StructuredJD | None = None
    text = jd_mod.normalize_jd_text(job.description or "")
    if len(text) < jd_mod.MIN_JD_CHARS:
        raise ValidationFailed(
            "This job has no description to analyse. Paste the job description from the posting.", code="jd_too_short"
        )
    built = jd_mod.structure_jd(text, title=job.title, company=company, location=job.location)
    listed = normalize_skills([str(s) for s in job.required_skills or []])
    if listed:
        # Skills the source listed explicitly are required by definition (they occur in the posting data).
        have = {s.lower() for s in built.required_skills}
        built = built.model_copy(update={"required_skills": built.required_skills + [s for s in listed if s.lower() not in have]})
    structured_seed = built
    return create_snapshot(
        db,
        user_id,
        text=text,
        source=JdSource.JOB,
        structured=structured_seed,
        url=job.canonical_url or job.apply_url,
        title=job.title,
        company=company,
        target=target,
    )


def resolve_snapshot(db: Session, user_id: uuid.UUID, jd: JdInput) -> tuple[JobDescriptionSnapshot, JobTarget | None]:
    given = [v for v in (jd.text, jd.snapshot_id, jd.job_target_id, jd.job_id) if v]
    if len(given) != 1:
        raise ValidationFailed(
            "Give exactly one job description: pasted text, a saved snapshot, a job target or a discovered job.",
            code="jd_required",
        )
    if jd.snapshot_id:
        snapshot = get_snapshot(db, user_id, jd.snapshot_id)
        target = get_target(db, user_id, snapshot.job_target_id) if snapshot.job_target_id else None
        return snapshot, target
    if jd.job_target_id:
        target = get_target(db, user_id, jd.job_target_id)
        if not target.latest_snapshot_id:
            raise ValidationFailed(
                "This job target has no job description yet. Add one (paste, upload or fetch) first.", code="target_has_no_jd"
            )
        return get_snapshot(db, user_id, target.latest_snapshot_id), target
    if jd.job_id:
        job = db.get(Job, jd.job_id)
        if job is None:
            raise NotFoundError("Job not found")
        snapshot, _ = snapshot_from_job(db, user_id, job)
        return snapshot, None
    source = jd.source or JdSource.PASTED
    if source == JdSource.JOB:
        source = JdSource.PASTED
    snapshot, _ = snapshot_from_text(
        db, user_id, text=jd.text or "", source=source, title=jd.title, company=jd.company, url=jd.url, structured=jd.structured
    )
    return snapshot, None


# --------------------------------------------------------------------------- reading


def _models(items: list[Any] | None, model: type) -> list[Any]:
    out = []
    for item in items or []:
        try:
            out.append(model.model_validate(item))
        except Exception:  # noqa: BLE001 - a malformed stored item is skipped, never a 500
            continue
    return out


def analysis_to_read(db: Session, analysis: AtsAnalysis, *, resume: Resume | None = None) -> AnalysisRead:
    resume = resume or db.get(Resume, analysis.resume_id)
    snapshot = db.get(JobDescriptionSnapshot, analysis.snapshot_id) if analysis.snapshot_id else None
    previous = db.get(AtsAnalysis, analysis.previous_analysis_id) if analysis.previous_analysis_id else None
    return AnalysisRead(
        id=analysis.id,
        resume_id=analysis.resume_id,
        resume_name=resume.name if resume else None,
        resume_version=analysis.resume_version,
        is_current=bool(resume and int(resume.current_version or 1) == analysis.resume_version),
        job_target_id=analysis.job_target_id,
        snapshot_id=analysis.snapshot_id,
        previous_analysis_id=analysis.previous_analysis_id,
        previous_score=previous.overall_score if previous else None,
        status=analysis.status,
        progress=analysis.progress,
        error=analysis.error,
        overall_score=analysis.overall_score,
        category_scores=_models(analysis.category_scores, CategoryScore),
        matched_keywords=_models(analysis.matched_keywords, KeywordHit),
        missing_keywords=_models(analysis.missing_keywords, KeywordMiss),
        weak_items=_models(analysis.weak_items, WeakItem),
        parse_risks=_models(analysis.parse_risks, ParseRisk),
        methodology_version=analysis.methodology_version,
        weights={k: float(v) for k, v in (analysis.weights or {}).items()},
        ai_provider=analysis.ai_provider,
        ai_model=analysis.ai_model,
        duration_ms=analysis.duration_ms,
        completed_at=analysis.completed_at,
        created_at=analysis.created_at,
        jd=SnapshotSummary(
            id=snapshot.id, title=snapshot.title, company=snapshot.company, source=snapshot.source, url=snapshot.url,
            created_at=snapshot.created_at,
        )
        if snapshot
        else SnapshotSummary(),
        suggestions=[SuggestionRead.model_validate(s) for s in sorted(analysis.suggestions, key=lambda s: s.ordinal)],
    )


def list_analyses(
    db: Session,
    user_id: uuid.UUID,
    *,
    resume_id: uuid.UUID | None = None,
    job_target_id: uuid.UUID | None = None,
    limit: int = 20,
) -> list[AnalysisListItem]:
    stmt = select(AtsAnalysis).where(AtsAnalysis.user_id == user_id)
    if resume_id:
        stmt = stmt.where(AtsAnalysis.resume_id == resume_id)
    if job_target_id:
        stmt = stmt.where(AtsAnalysis.job_target_id == job_target_id)
    rows = list(db.scalars(stmt.order_by(AtsAnalysis.created_at.desc(), AtsAnalysis.id).limit(max(1, min(limit, 100)))))
    snapshots = {
        s.id: s
        for s in db.scalars(select(JobDescriptionSnapshot).where(JobDescriptionSnapshot.id.in_({r.snapshot_id for r in rows if r.snapshot_id})))
    } if rows else {}
    names = dict(db.execute(select(Resume.id, Resume.name).where(Resume.id.in_({r.resume_id for r in rows}))).all()) if rows else {}
    return [
        AnalysisListItem(
            id=r.id,
            resume_id=r.resume_id,
            resume_name=names.get(r.resume_id),
            resume_version=r.resume_version,
            job_target_id=r.job_target_id,
            status=r.status,
            overall_score=r.overall_score,
            jd_title=snapshots[r.snapshot_id].title if r.snapshot_id in snapshots else None,
            jd_company=snapshots[r.snapshot_id].company if r.snapshot_id in snapshots else None,
            created_at=r.created_at,
        )
        for r in rows
    ]


# --------------------------------------------------------------------------- running


def _require_analysable(resume: Resume) -> dict[str, Any]:
    parsed = resume.parsed_data if isinstance(resume.parsed_data, dict) else {}
    if not parsed or resume.parse_status != ResumeParseStatus.PARSED:
        raise ValidationFailed(
            "This resume has no readable content yet. Fix it in the editor (or re-upload it) before analysing.",
            code="resume_not_parsed",
        )
    return parsed


def run_analysis(
    db: Session,
    user_id: uuid.UUID,
    resume: Resume,
    snapshot: JobDescriptionSnapshot,
    *,
    target: JobTarget | None = None,
    weights: dict[str, float] | None = None,
    previous: AtsAnalysis | None = None,
    schedule_polish: bool = True,
    polish_task: str = llm.TASK_POLISH,
) -> AtsAnalysis:
    """Score ``resume`` (current version) against ``snapshot`` and store the analysis + suggestions.

    ``polish_task`` names the AI task of the background polish (its workflow picks the model):
    ``polish_suggestions`` (ATS analysis) by default, ``tailor_resume`` for a tailoring run."""
    started = time.monotonic()
    parsed = _require_analysable(resume)
    structured = StructuredJD.model_validate(snapshot.structured or {})
    profile = load_profile(db, user_id)
    resolved = resolve_weights(weights)
    raw_text = resume.text_content or ""
    score = score_resume(
        parsed, raw_text, structured, profile_years=profile.years, profile_skills=profile.skills,
        profile_text=profile.text, weights=resolved,
    )
    facts = make_facts(parsed, raw_text, profile.inputs)
    drafts = build_drafts(
        parsed, raw_text, structured, score, facts=facts, profile_skills=profile.skills,
        profile_text=profile.text, profile_years=profile.years,
    )
    # A tailoring run always gets its AI pass when a model answers (it rewrites the summary too);
    # an ATS analysis only when there are bullet suggestions to polish.
    polish = schedule_polish and llm.model_available(polish_task) and (
        polish_task == llm.TASK_TAILOR or any(d.kind == "REPLACE_BULLET" for d in drafts)
    )
    analysis = AtsAnalysis(
        user_id=user_id,
        resume_id=resume.id,
        resume_version=int(resume.current_version or 1),
        job_target_id=target.id if target else snapshot.job_target_id,
        snapshot_id=snapshot.id,
        previous_analysis_id=previous.id if previous else None,
        status=AtsAnalysisStatus.RUNNING if polish else AtsAnalysisStatus.DONE,
        progress=40 if polish else 100,
        overall_score=score.overall,
        category_scores=[c.model_dump(mode="json") for c in score.categories],
        matched_keywords=[k.model_dump(mode="json") for k in score.matched],
        missing_keywords=[k.model_dump(mode="json") for k in score.missing],
        weak_items=[w.model_dump(mode="json") for w in score.weak_items],
        parse_risks=[r.model_dump(mode="json") for r in score.parse_risks],
        methodology_version=METHODOLOGY_VERSION,
        weights=resolved,
        duration_ms=int((time.monotonic() - started) * 1000),
        completed_at=None if polish else utcnow(),
    )
    db.add(analysis)
    db.flush()
    for ordinal, draft in enumerate(drafts, start=1):
        db.add(
            OptimizationSuggestion(
                analysis_id=analysis.id,
                ordinal=ordinal,
                kind=SuggestionKind(draft.kind),
                title=draft.title[:300],
                rationale=draft.rationale,
                target_path=draft.target_path,
                before=draft.before,
                after=draft.after,
                safe=draft.safe,
                requires_confirmation=draft.requires_confirmation,
                confirmation_label=draft.confirmation_label,
                estimated_gain=draft.estimated_gain,
                status=SuggestionStatus.PROPOSED,
                checks=draft.checks,
            )
        )
    db.flush()
    db.refresh(analysis)
    owner = target or (db.get(JobTarget, snapshot.job_target_id) if snapshot.job_target_id else None)
    if owner is not None:
        owner.last_analysis_id = analysis.id
        owner.last_analyzed_at = utcnow()
        db.add(owner)
    audit(
        db,
        action="ats.analysis_created",
        message=f"ATS estimate {score.overall}/100 for {resume.name} (v{analysis.resume_version}) vs {target_label(owner, snapshot)}",
        user_id=user_id,
        actor=Actor.USER,
        meta={
            "analysis_id": str(analysis.id),
            "resume_id": str(resume.id),
            "snapshot_id": str(snapshot.id),
            "target_id": str(owner.id) if owner else None,
            "score": score.overall,
            "previous_analysis_id": str(previous.id) if previous else None,
        },
    )
    if polish:
        start_polish(analysis.id, user_id, task=polish_task)
    logger.info("ATS analysis %s: %d/100, %d suggestions, polish=%s", analysis.id, score.overall, len(drafts), polish)
    return analysis


def create_analysis(db: Session, user_id: uuid.UUID, payload: AnalysisCreate) -> AnalysisRead:
    resume = resumes.get_resume(db, user_id, payload.resume_id)
    _require_analysable(resume)
    snapshot, target = resolve_snapshot(db, user_id, payload.jd)
    analysis = run_analysis(db, user_id, resume, snapshot, target=target, weights=payload.weights)
    return analysis_to_read(db, analysis, resume=resume)


# --------------------------------------------------------------------------- applying


def _check_current(analysis: AtsAnalysis, resume: Resume) -> None:
    if int(resume.current_version or 1) != int(analysis.resume_version):
        raise ConflictError(
            "This resume changed since it was analysed. Run the analysis again to get fresh suggestions.",
            code="stale_resume",
            details={"current_version": int(resume.current_version or 1), "analysed_version": analysis.resume_version},
        )


def _snapshot_of(db: Session, analysis: AtsAnalysis) -> JobDescriptionSnapshot:
    snapshot = db.get(JobDescriptionSnapshot, analysis.snapshot_id) if analysis.snapshot_id else None
    if snapshot is None:
        raise ConflictError("The job description of this analysis was deleted. Analyse again.", code="jd_missing")
    return snapshot


def _clean(text: str, *, single_line: bool) -> str:
    cleaned = text.strip()
    return re.sub(r"\s+", " ", cleaned) if single_line else cleaned


def _validated_text(suggestion: OptimizationSuggestion, text: str | None, *, edited: bool, facts: Any) -> str:
    kind = suggestion.kind
    summary = kind == SuggestionKind.REPLACE_SUMMARY or (kind == SuggestionKind.ADD_KEYWORD_CONTEXT and suggestion.target_path == "summary")
    if text is None or not text.strip():
        if edited:
            raise ValidationFailed("The text cannot be empty.", code="empty_text", details={"id": str(suggestion.id)})
        raise ValidationFailed(
            "This suggestion needs your own words: edit the text, then apply it.",
            code="edit_required",
            details={"id": str(suggestion.id)},
        )
    after = _clean(text, single_line=not summary)
    if _PLACEHOLDER_RE.search(after):
        raise ValidationFailed(
            "Replace the bracketed part with your real result before applying.", code="placeholder_left", details={"id": str(suggestion.id)}
        )
    # Generated text may only use numbers the resume or profile already has. The user's own edit of a
    # bullet may state their result; a summary is held to the resume's numbers (as resumes.apply does).
    if summary or not edited:
        numbers = invented_numbers(after, facts, original=None if summary else suggestion.before)
        if numbers:
            raise ValidationFailed(
                f"The text mentions {', '.join(sorted(numbers))}, which is not on your resume. Use only numbers your resume "
                "already states.",
                code="invented_number",
                details={"id": str(suggestion.id), "numbers": sorted(numbers)},
            )
    return after


def _choose(
    analysis: AtsAnalysis, request_ids: list[uuid.UUID], edits: dict[uuid.UUID, str], facts: Any
) -> tuple[list[tuple[OptimizationSuggestion, str | None, bool]], list[SkippedItem]]:
    by_id = {s.id: s for s in analysis.suggestions}
    chosen: list[tuple[OptimizationSuggestion, str | None, bool]] = []
    skipped: list[SkippedItem] = []
    seen: set[uuid.UUID] = set()
    for sid in request_ids:
        if sid in seen:
            continue
        seen.add(sid)
        suggestion = by_id.get(sid)
        if suggestion is None:
            raise ValidationFailed(
                f"“{sid}” is not one of this analysis's suggestions.", code="unknown_suggestion", details={"id": str(sid)}
            )
        if suggestion.kind == SuggestionKind.MANUAL:
            raise ValidationFailed(
                "This item is advice for you to act on; it cannot be applied automatically.",
                code="not_applicable",
                details={"id": str(sid)},
            )
        if suggestion.status in (SuggestionStatus.APPLIED, SuggestionStatus.EDITED):
            skipped.append(SkippedItem(id=sid, reason="already_applied"))
            continue
        if suggestion.kind in (SuggestionKind.ADD_SKILL, SuggestionKind.REORDER_SECTION):
            chosen.append((suggestion, suggestion.after, False))
            continue
        edited = sid in edits and _clean(edits[sid], single_line=False) != (suggestion.after or "").strip()
        text = edits[sid] if sid in edits else suggestion.after
        chosen.append((suggestion, _validated_text(suggestion, text, edited=edited, facts=facts), edited))
    return chosen, skipped


def _mark_applied(chosen: list[tuple[OptimizationSuggestion, str | None, bool]], applied: list[Any], version: int) -> list[AppliedItem]:
    applied_ids = {s.id for s in applied}
    out: list[AppliedItem] = []
    for suggestion, after, edited in chosen:
        if suggestion.id not in applied_ids:
            continue
        if edited:
            suggestion.checks = {**(suggestion.checks or {}), "original_after": suggestion.after}
            suggestion.after = after
        suggestion.status = SuggestionStatus.EDITED if edited else SuggestionStatus.APPLIED
        suggestion.applied_version = version
        out.append(AppliedItem(id=suggestion.id, kind=suggestion.kind, title=suggestion.title, edited=edited))
    return out


def apply_suggestions(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID, request: ApplyRequest) -> ApplyResult:
    analysis = get_analysis(db, user_id, analysis_id)
    resume = resumes.get_resume(db, user_id, analysis.resume_id)
    _check_current(analysis, resume)
    snapshot = _snapshot_of(db, analysis)
    structured = StructuredJD.model_validate(snapshot.structured or {})
    profile = load_profile(db, user_id)
    parsed = _require_analysable(resume)
    facts = make_facts(parsed, resume.text_content or "", profile.inputs)

    chosen, skipped = _choose(analysis, request.suggestion_ids, request.edits, facts)
    new_parsed, applied, not_applied = apply_to_parsed(parsed, [(s, after) for s, after, _ in chosen], structured)
    skipped += [SkippedItem(id=s.id, reason=reason) for s, reason in not_applied]
    target = db.get(JobTarget, analysis.job_target_id) if analysis.job_target_id else None
    before_version = int(resume.current_version or 1)
    if not applied:
        return ApplyResult(
            resume=resumes.resume_to_read(resume),
            analysis=analysis_to_read(db, analysis, resume=resume),
            previous_analysis_id=analysis.id,
            previous_score=analysis.overall_score,
            applied=[],
            skipped=skipped,
            restorable_version=None,
        )

    any_edited = any(edited for s, _, edited in chosen if s in applied)
    label = target_label(target, snapshot)
    note = f"ATS: applied {len(applied)} suggestion{'s' if len(applied) != 1 else ''} for {label}"
    if any_edited:
        note += " (with your edits)"
    resume = resumes.update_parsed_data(
        db, user_id, resume.id, ParsedResume.model_validate(new_parsed), note=note[:500],
        change_source=ResumeChangeSource.USER if any_edited else ResumeChangeSource.AI,
    )
    db.flush()
    db.refresh(resume)
    applied_items = _mark_applied(chosen, applied, int(resume.current_version))
    rec_mod.invalidate_resume(resume.id)
    audit(
        db,
        action="ats.suggestions_applied",
        message=f"{note} (resume {resume.name} v{resume.current_version})",
        user_id=user_id,
        actor=Actor.USER,
        meta={
            "analysis_id": str(analysis.id),
            "resume_id": str(resume.id),
            "version": resume.current_version,
            "applied": [str(a.id) for a in applied_items],
            "edited": [str(a.id) for a in applied_items if a.edited],
            "skipped": [s.reason for s in skipped],
        },
    )
    fresh = run_analysis(db, user_id, resume, snapshot, target=target, weights=analysis.weights, previous=analysis)
    return ApplyResult(
        resume=resumes.resume_to_read(resume),
        analysis=analysis_to_read(db, fresh, resume=resume),
        previous_analysis_id=analysis.id,
        previous_score=analysis.overall_score,
        applied=applied_items,
        skipped=skipped,
        restorable_version=before_version,
    )


def ignore_suggestions(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID, request: IgnoreRequest) -> AnalysisRead:
    analysis = get_analysis(db, user_id, analysis_id)
    by_id = {s.id: s for s in analysis.suggestions}
    for sid in request.suggestion_ids:
        suggestion = by_id.get(sid)
        if suggestion is None:
            raise ValidationFailed(
                f"“{sid}” is not one of this analysis's suggestions.", code="unknown_suggestion", details={"id": str(sid)}
            )
        if suggestion.status in (SuggestionStatus.APPLIED, SuggestionStatus.EDITED):
            continue
        suggestion.status = SuggestionStatus.IGNORED if request.ignore else SuggestionStatus.PROPOSED
        db.add(suggestion)
    db.flush()
    return analysis_to_read(db, analysis)


def _explanation(suggestion: OptimizationSuggestion) -> Explanation:
    checks = suggestion.checks or {}
    evidence = [str(e) for e in checks.get("evidence") or []]
    if suggestion.kind == SuggestionKind.REPLACE_BULLET and suggestion.before:
        what = f"{suggestion.title}: “{suggestion.before}” → “{suggestion.after}”"
    elif suggestion.kind == SuggestionKind.ADD_SKILL:
        what = f"Added {suggestion.after} to the skills section"
    elif suggestion.kind == SuggestionKind.REORDER_SECTION:
        what = f"{suggestion.title} ({suggestion.after})"
    else:
        what = suggestion.title
    return Explanation(
        suggestion_id=suggestion.id,
        what=what,
        why=suggestion.rationale,
        evidence=evidence,
        source="AI" if checks.get("ai_polished") else "SYSTEM",
    )


def auto_optimize(
    db: Session,
    user_id: uuid.UUID,
    analysis_id: uuid.UUID,
    *,
    mode: str = "new_resume",
    name: str | None = None,
    polish_task: str = llm.TASK_POLISH,
) -> AutoOptimizeResult:
    """Apply every *safe* suggestion (never one that needs confirmation) to a new resume or version."""
    analysis = get_analysis(db, user_id, analysis_id)
    source = resumes.get_resume(db, user_id, analysis.resume_id)
    _check_current(analysis, source)
    snapshot = _snapshot_of(db, analysis)
    structured = StructuredJD.model_validate(snapshot.structured or {})
    parsed = _require_analysable(source)
    target = db.get(JobTarget, analysis.job_target_id) if analysis.job_target_id else None
    safe = [
        s for s in analysis.suggestions
        if s.safe and not s.requires_confirmation and s.kind != SuggestionKind.MANUAL and s.after
        and s.status == SuggestionStatus.PROPOSED
    ]
    new_parsed, applied, not_applied = apply_to_parsed(parsed, [(s, s.after) for s in safe], structured)
    skipped = [SkippedItem(id=s.id, reason=reason) for s, reason in not_applied]
    label = target_label(target, snapshot)
    explanations = [_explanation(s) for s in applied]

    if mode == "new_version":
        if not applied:
            raise ValidationFailed(
                "Nothing is safe to apply automatically. Review the suggestions that need your confirmation.",
                code="nothing_safe",
            )
        resume = resumes.update_parsed_data(
            db, user_id, source.id, ParsedResume.model_validate(new_parsed),
            note=f"ATS auto-optimize for {label}: {len(applied)} change{'s' if len(applied) != 1 else ''}"[:500],
            change_source=ResumeChangeSource.AI,
        )
        db.flush()
        db.refresh(resume)
        applied_items = _mark_applied([(s, s.after, False) for s in applied], applied, int(resume.current_version))
    else:
        company = (target.company_name if target else None) or snapshot.company
        role = (target.role_title if target else None) or snapshot.title
        default_name = " — ".join(p for p in (source.name, " ".join(x for x in (company, role) if x)) if p)
        resume = resumes.create_resume_from_parsed(
            db,
            user_id,
            ParsedResume.model_validate(new_parsed),
            name=(name or default_name)[:255],
            kind=ResumeKind.TAILORED,
            target_role=role or source.target_role,
            template=source.template or "classic",
            source_resume_id=source.id,
            note=f"Tailored for {label}: {len(applied)} safe change{'s' if len(applied) != 1 else ''} (ATS auto-optimize)"[:500],
            change_source=ResumeChangeSource.AI,
        )
        db.flush()
        db.refresh(resume)
        for s in applied:
            s.checks = {**(s.checks or {}), "applied_to_resume_id": str(resume.id)}
        applied_items = [AppliedItem(id=s.id, kind=s.kind, title=s.title) for s in applied]
        if target is not None:
            target.tailored_resume_id = resume.id
            target.tailored_resume_version = int(resume.current_version or 1)
            target.source_resume_id = target.source_resume_id or source.id
            db.add(target)
    rec_mod.invalidate_resume(resume.id)
    audit(
        db,
        action="ats.auto_optimized",
        message=f"Auto-optimized {source.name} for {label} ({mode.replace('_', ' ')}, {len(applied)} changes)",
        user_id=user_id,
        actor=Actor.USER,
        meta={
            "analysis_id": str(analysis.id),
            "source_resume_id": str(source.id),
            "resume_id": str(resume.id),
            "mode": mode,
            "applied": [str(s.id) for s in applied],
            "target_id": str(target.id) if target else None,
        },
    )
    fresh = run_analysis(db, user_id, resume, snapshot, target=target, weights=analysis.weights, previous=analysis, polish_task=polish_task)
    return AutoOptimizeResult(
        mode=mode,  # type: ignore[arg-type]
        resume=resumes.resume_to_read(resume),
        source_resume_id=source.id,
        analysis=analysis_to_read(db, fresh, resume=resume),
        previous_score=analysis.overall_score,
        applied=applied_items,
        skipped=skipped,
        explanations=explanations,
    )


def undo_apply(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID) -> UndoResult:
    """Undo the apply that produced ``analysis_id``: restore the version before it, as a new version."""
    analysis = get_analysis(db, user_id, analysis_id)
    if not analysis.previous_analysis_id:
        raise ValidationFailed("There is nothing to undo for this analysis.", code="nothing_to_undo")
    previous = get_analysis(db, user_id, analysis.previous_analysis_id)
    if previous.resume_id != analysis.resume_id:
        raise ValidationFailed(
            "This analysis is of a tailored copy; delete or archive the copy instead.", code="nothing_to_undo"
        )
    resume = resumes.get_resume(db, user_id, analysis.resume_id)
    _check_current(analysis, resume)
    restore_number = int(previous.resume_version)
    version = db.scalar(
        select(ResumeVersion).where(ResumeVersion.resume_id == resume.id, ResumeVersion.version_number == restore_number)
    )
    if version is None:
        raise NotFoundError(f"Version {restore_number} of this resume was not found")
    resume = resumes.update_parsed_data(
        db, user_id, resume.id, ParsedResume.model_validate(copy.deepcopy(version.parsed_data or {})),
        note=f"ATS: undo (restored version {restore_number})", change_source=ResumeChangeSource.USER,
    )
    db.flush()
    db.refresh(resume)
    for suggestion in previous.suggestions:
        if suggestion.applied_version == analysis.resume_version:
            suggestion.status = SuggestionStatus.PROPOSED
            suggestion.applied_version = None
            original = (suggestion.checks or {}).get("original_after")
            if original is not None:
                suggestion.after = original
    rec_mod.invalidate_resume(resume.id)
    audit(
        db,
        action="ats.suggestions_undone",
        message=f"Undid ATS changes on {resume.name}: restored version {restore_number} as v{resume.current_version}",
        user_id=user_id,
        actor=Actor.USER,
        meta={"analysis_id": str(analysis.id), "resume_id": str(resume.id), "restored_version": restore_number},
    )
    snapshot = _snapshot_of(db, analysis)
    target = db.get(JobTarget, analysis.job_target_id) if analysis.job_target_id else None
    fresh = run_analysis(db, user_id, resume, snapshot, target=target, weights=analysis.weights, previous=analysis)
    return UndoResult(resume=resumes.resume_to_read(resume), analysis=analysis_to_read(db, fresh, resume=resume), restored_version=restore_number)


def is_tailoring_analysis(db: Session, analysis: AtsAnalysis) -> bool:
    """True for the first analysis of a tailored copy (the one its AI tailoring pass runs on)."""
    if not analysis.previous_analysis_id:
        return False
    previous = db.get(AtsAnalysis, analysis.previous_analysis_id)
    resume = db.get(Resume, analysis.resume_id)
    return bool(
        previous is not None and previous.resume_id != analysis.resume_id
        and resume is not None and resume.kind == ResumeKind.TAILORED
    )


def retry_polish(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID, *, task: str | None = None) -> AnalysisRead:
    """Run the model polish again (after a provider error the user fixed).

    ``task`` ``tailor_resume`` re-runs the AI tailoring pass of a tailored copy (its accepted
    rewrites are applied as a new version); omitted, it is inferred from the analysis."""
    analysis = get_analysis(db, user_id, analysis_id)
    if task is None:
        task = llm.TASK_TAILOR if is_tailoring_analysis(db, analysis) else llm.TASK_POLISH
    if not llm.model_available(task):
        raise ValidationFailed(
            "No AI model is configured, so the rule-based suggestions are final. Configure a model in AI Model Settings.",
            code="provider_not_configured",
        )
    if analysis.status == AtsAnalysisStatus.RUNNING and is_polishing(analysis.id):
        return analysis_to_read(db, analysis)
    if task == llm.TASK_TAILOR:
        # The AI tailoring rewrites the version this analysis scored; a copy edited since is not touched.
        _check_current(analysis, resumes.get_resume(db, user_id, analysis.resume_id))
    analysis.status = AtsAnalysisStatus.RUNNING
    analysis.progress = 40
    analysis.error = None
    db.add(analysis)
    db.flush()
    start_polish(analysis.id, user_id, task=task)
    return analysis_to_read(db, analysis)


# --------------------------------------------------------------------------- model polish


_polish_lock = threading.Lock()
_polishing: set[str] = set()

_BULLET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"bullet": {"type": "string"}},
    "required": ["bullet"],
}


def is_polishing(analysis_id: uuid.UUID | str) -> bool:
    with _polish_lock:
        return str(analysis_id) in _polishing


def start_polish(analysis_id: uuid.UUID, user_id: uuid.UUID, *, task: str | None = None) -> threading.Thread | None:
    """Polish in a daemon thread (idempotent: one thread per analysis).

    A per-run model choice of the current request (``ai.choice``) travels into the thread,
    so the polish runs on the model the user picked for this analysis.
    """
    key = str(analysis_id)
    override = llm.current_target_override()
    with _polish_lock:
        if key in _polishing:
            return None
        _polishing.add(key)
    thread = threading.Thread(
        target=_polish_thread, args=(analysis_id, user_id, override, task or llm.TASK_POLISH), name=f"jobpilot-ats-polish-{key[:8]}", daemon=True
    )
    try:
        thread.start()
    except BaseException:
        with _polish_lock:
            _polishing.discard(key)
        raise
    return thread


def _polish_thread(analysis_id: uuid.UUID, user_id: uuid.UUID, override: Any = None, task: str | None = None) -> None:
    from app.core.actor import actor_context

    try:
        with actor_context(user_id), llm.ai_user(user_id, target_override=override):
            deadline = time.monotonic() + POLISH_START_TIMEOUT
            while not _analysis_visible(analysis_id):
                if time.monotonic() > deadline:
                    logger.info("ATS polish %s: analysis never became visible (request rolled back?)", analysis_id)
                    return
                time.sleep(0.2)
            polish_analysis(analysis_id, task=task or llm.TASK_POLISH)
    except Exception:  # noqa: BLE001 - a background thread must never raise into the void
        logger.exception("ATS polish %s crashed", analysis_id)
    finally:
        with _polish_lock:
            _polishing.discard(str(analysis_id))


def _analysis_visible(analysis_id: uuid.UUID) -> bool:
    from app.core.database import session_scope

    with session_scope() as db:
        return db.get(AtsAnalysis, analysis_id) is not None


def _model_bullet(bullet: str, entry: dict[str, Any], structured: StructuredJD, task: str = llm.TASK_POLISH) -> str | None:
    words = resume_apply._content_words(bullet)
    first = words[0] if words else ""
    verb_rule = (
        f'Keep the opening word "{bullet.split()[0]}" exactly as it is; only add a short purpose or result clause.'
        if first and first not in resume_apply._WEAK_FIRST
        else "You may replace the weak opening word with a stronger past-tense verb of the same meaning."
    )
    context = {
        "title": entry.get("title"),
        "company": entry.get("company"),
        "technologies": entry.get("technologies") or [],
        "target_role": structured.title,
    }
    prompt = (
        f"Bullet to rewrite:\n{llm.wrap_untrusted('RESUME BULLET', bullet, max_chars=600)}\n\n"
        f"Role facts you may use:\n{llm.wrap_untrusted('ROLE CONTEXT', str(context), max_chars=800)}\n\n"
        f"{verb_rule}\nReturn JSON: {{\"bullet\": \"<rewritten bullet>\"}}"
    )
    answer = llm.llm_json(
        task, prompt, schema=_BULLET_SCHEMA, system=llm.system_prompt(resume_apply.BULLET_SYSTEM), max_tokens=200
    )
    text = " ".join(str((answer or {}).get("bullet") or "").split()).strip(" -•*")
    return (text.rstrip(" .;,") + ".") if text else None


def polish_analysis(analysis_id: uuid.UUID, *, task: str = llm.TASK_POLISH) -> None:
    """Ask the model for better bullet rewrites; keep only guard-passing ones; mark the analysis DONE.

    Each step is its own transaction so the UI's progress poll sees it move. A tailoring run
    (``task == tailor_resume``) goes to :func:`app.modules.ats.tailoring.tailor_pass` instead,
    which *applies* its guard-passing rewrites to the tailored copy as a new version.
    """
    from app.core.database import session_scope

    if task == llm.TASK_TAILOR:
        from app.modules.ats import tailoring

        tailoring.tailor_pass(analysis_id, task=task)
        return

    started = time.monotonic()
    with session_scope() as db:
        analysis = db.get(AtsAnalysis, analysis_id)
        if analysis is None or analysis.status != AtsAnalysisStatus.RUNNING:
            return
        resume = db.get(Resume, analysis.resume_id)
        snapshot = db.get(JobDescriptionSnapshot, analysis.snapshot_id) if analysis.snapshot_id else None
        stale = resume is None or snapshot is None or int(resume.current_version or 1) != analysis.resume_version
        pending = [
            s.id for s in analysis.suggestions
            if s.kind == SuggestionKind.REPLACE_BULLET and s.status == SuggestionStatus.PROPOSED
            and not (s.checks or {}).get("ai_polished")
        ][:POLISH_MAX_BULLETS]
        user_id = analysis.user_id
    if stale:
        _finish(analysis_id, started, error="The resume changed before the AI could polish these suggestions.", task=task)
        return

    error: str | None = None
    for done, suggestion_id in enumerate(pending, start=1):
        try:
            with session_scope() as db:
                suggestion = db.get(OptimizationSuggestion, suggestion_id)
                analysis = db.get(AtsAnalysis, analysis_id)
                resume = db.get(Resume, analysis.resume_id) if analysis else None
                if suggestion is None or analysis is None or resume is None or suggestion.status != SuggestionStatus.PROPOSED:
                    continue
                snapshot = db.get(JobDescriptionSnapshot, analysis.snapshot_id)
                structured = StructuredJD.model_validate((snapshot.structured if snapshot else None) or {})
                parsed = resume.parsed_data or {}
                facts = make_facts(parsed, resume.text_content or "", rec_mod.load_match_inputs(db, user_id))
                match = re.match(r"^experience\[(\d+)\]\.description$", suggestion.target_path or "")
                experience = parsed.get("experience") if isinstance(parsed.get("experience"), list) else []
                entry = experience[int(match.group(1))] if match and int(match.group(1)) < len(experience) else {}
                bullet = suggestion.before or ""
                candidate = resume_apply.strip_filler(_model_bullet(bullet, entry if isinstance(entry, dict) else {}, structured, task), bullet)
                checks = dict(suggestion.checks or {})
                if candidate and candidate.strip().rstrip(".") != bullet.strip().rstrip("."):
                    problem = resume_apply.bullet_problem(candidate, bullet, facts)
                    if problem is None:
                        checks.update({"ai_polished": True, "method": "model", "rules_after": suggestion.after, "bullet_problem": None})
                        suggestion.after = candidate
                        suggestion.safe = True
                        suggestion.rationale = (
                            "Rewritten by the AI model and checked by JobPilot's rules: every fact of the original is kept "
                            "and no number, tool or claim was added. Review it before applying."
                        )
                    else:
                        checks.update({"ai_rejected": problem})
                checks["ai_attempted"] = True
                suggestion.checks = checks
                analysis.progress = min(95, 40 + int(55 * done / max(1, len(pending))))
        except Exception as exc:  # noqa: BLE001 - keep the deterministic suggestions
            error = _safe_error(exc)
            logger.info("ATS polish %s stopped: %s", analysis_id, error)
            break
    _finish(analysis_id, started, error=error, task=task)


def _safe_error(exc: Exception, *, prefix: str = "AI polish unavailable") -> str:
    message = getattr(exc, "message", None) or str(exc) or type(exc).__name__
    return f"{prefix}: {message}"[:300]


def _finish(analysis_id: uuid.UUID, started: float, *, error: str | None, task: str = llm.TASK_POLISH) -> None:
    from app.core.database import session_scope

    provider, model = llm.model_info(task)
    with session_scope() as db:
        analysis = db.get(AtsAnalysis, analysis_id)
        if analysis is None:
            return
        analysis.status = AtsAnalysisStatus.DONE
        analysis.progress = 100
        analysis.error = error
        analysis.ai_provider = provider
        analysis.ai_model = model
        analysis.duration_ms = int(analysis.duration_ms or 0) + int((time.monotonic() - started) * 1000)
        analysis.completed_at = utcnow()


__all__ = [
    "analysis_to_read",
    "apply_suggestions",
    "auto_optimize",
    "create_analysis",
    "create_snapshot",
    "get_analysis",
    "get_snapshot",
    "get_target",
    "ignore_suggestions",
    "is_tailoring_analysis",
    "list_analyses",
    "load_profile",
    "polish_analysis",
    "resolve_snapshot",
    "retry_polish",
    "run_analysis",
    "snapshot_from_job",
    "snapshot_from_text",
    "start_polish",
    "undo_apply",
]
