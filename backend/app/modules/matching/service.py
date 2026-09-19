"""Matching service — score a job against a user and persist a :class:`JobMatch`.

The numbers come from :mod:`app.modules.matching.scoring` (pure, testable). The prose
explanation comes from the AI layer when it is available and from a local template
otherwise; the AI never changes the score and never invents a fact.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.models.base import utcnow
from app.models.enums import Actor, ApplicationStatus, CompanyPriority
from app.models.job import Job, JobMatch
from app.models.profile import JobPreference, UserProfile
from app.models.resume import Resume
from app.modules.ai.skills import normalize_skills
from app.modules.matching import scoring

logger = logging.getLogger(__name__)

DEFAULT_MIN_MATCH_SCORE = 75
HIGH_MATCH_SCORE = 85

__all__ = [
    "analyze_job",
    "analyze_jobs",
    "analyze_all",
    "build_summary",
    "CandidateFacts",
    "HIGH_MATCH_SCORE",
]


# --------------------------------------------------------------------------- candidate facts


@dataclass
class CandidateFacts:
    """The flattened candidate signal the scorer needs.

    Built from ``profiles.service.build_candidate_context`` when that module exists and
    from the ORM rows directly otherwise, so matching never blocks on another module.
    """

    skills: list[str] = field(default_factory=list)
    desired_titles: list[str] = field(default_factory=list)
    years_of_experience: float | None = None
    preferred_locations: list[str] = field(default_factory=list)
    work_modes: list[str] = field(default_factory=list)
    employment_types: list[str] = field(default_factory=list)
    preferred_technologies: list[str] = field(default_factory=list)
    excluded_keywords: list[str] = field(default_factory=list)
    min_salary: int | None = None
    desired_salary: int | None = None
    min_match_score: int = DEFAULT_MIN_MATCH_SCORE
    resume_id: uuid.UUID | None = None
    context: Any = None  # profiles.schemas.CandidateContext when available


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value if v not in (None, "")]


def _resume_skills(resume: Resume | None) -> list[str]:
    if resume is None:
        return []
    parsed = resume.parsed_data or {}
    if not isinstance(parsed, dict):
        return []
    return _as_list(parsed.get("skills"))


def _default_resume(db: Session, user_id: uuid.UUID) -> Resume | None:
    stmt = (
        select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(Resume.is_default.desc(), Resume.created_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def _resume_years(resume: Resume | None) -> float | None:
    if resume is None or not isinstance(resume.parsed_data, dict):
        return None
    value = resume.parsed_data.get("total_experience_years")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def build_candidate_facts(db: Session, user_id: uuid.UUID, resume: Resume | None = None) -> CandidateFacts:
    """Collect everything the scorer needs about a candidate."""
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == user_id)).first()
    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == user_id)).first()
    if resume is None:
        resume = _default_resume(db, user_id)

    skills = normalize_skills(
        _as_list(getattr(profile, "skills", None))
        + _as_list(getattr(profile, "technologies", None))
        + _resume_skills(resume)
    )
    facts = CandidateFacts(
        skills=skills,
        desired_titles=_as_list(getattr(preference, "desired_titles", None)),
        years_of_experience=getattr(profile, "years_of_experience", None) if profile else None,
        preferred_locations=_as_list(getattr(preference, "preferred_locations", None)),
        work_modes=_as_list(getattr(preference, "work_modes", None)),
        employment_types=_as_list(getattr(preference, "employment_types", None)),
        preferred_technologies=_as_list(getattr(preference, "preferred_technologies", None)),
        excluded_keywords=_as_list(getattr(preference, "excluded_keywords", None)),
        min_salary=getattr(preference, "min_salary", None) if preference else None,
        desired_salary=getattr(preference, "desired_salary", None) if preference else None,
        min_match_score=int(getattr(preference, "min_match_score", DEFAULT_MIN_MATCH_SCORE) or DEFAULT_MIN_MATCH_SCORE),
        resume_id=resume.id if resume is not None else None,
    )
    if facts.years_of_experience is None:
        facts.years_of_experience = _resume_years(resume)
    facts.context = _build_candidate_context(db, user_id, facts.resume_id)
    return facts


def _build_candidate_context(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID | None) -> Any:
    """Optional richer context from the profiles module (used for the AI explanation)."""
    try:
        from app.modules.profiles.service import build_candidate_context
    except Exception as exc:  # module not implemented yet
        logger.debug("profiles.service.build_candidate_context unavailable: %s", exc)
        return None
    try:
        return build_candidate_context(db, user_id, resume_id)
    except Exception as exc:  # pragma: no cover - defensive, never fail a match on this
        logger.warning("build_candidate_context failed: %s", exc)
        return None


# --------------------------------------------------------------------------- explanation


def _fallback_explanation(job: Job, result: dict[str, Any], missing: list[str], labels: dict[str, str]) -> str:
    company = getattr(job.company, "name", None) or "this company"
    score = result["score"]
    parts = result["parts"]
    bits = [f"{score}% match for {job.title} at {company}."]
    if parts.get("skills") is not None:
        if missing:
            bits.append(f"Skills {parts['skills']}% — missing {', '.join(missing[:5])}.")
        else:
            bits.append(f"Skills {parts['skills']}% — you cover every listed requirement.")
    experience_text = {
        scoring.STRONG: "Your experience sits right inside the requested range.",
        scoring.GOOD: "Your experience is close to what they ask for.",
        scoring.UNDER: "You are below the requested experience range.",
        scoring.OVER: "You are more experienced than this role asks for.",
        scoring.UNKNOWN: "Experience requirements are unclear.",
    }.get(labels.get("experience", scoring.UNKNOWN))
    if experience_text:
        bits.append(experience_text)
    location_text = {
        scoring.MATCH: f"{job.location} is one of your preferred locations.",
        scoring.REMOTE_OK: "The role is remote friendly.",
        scoring.MISMATCH: f"{job.location} is outside your preferred locations.",
        scoring.UNKNOWN: "Location preference is not set.",
    }.get(labels.get("location", scoring.UNKNOWN))
    if location_text:
        bits.append(location_text)
    salary_text = {
        scoring.ABOVE: "The advertised salary is at or above what you are targeting.",
        scoring.WITHIN: "The advertised salary is inside your acceptable range.",
        scoring.BELOW: "The advertised salary is below your minimum.",
        scoring.UNKNOWN: "No salary information to compare.",
    }.get(labels.get("salary", scoring.UNKNOWN))
    if salary_text:
        bits.append(salary_text)
    return " ".join(bits)


def build_explanation_payload(
    result: dict[str, Any],
    *,
    skill_score: int,
    title_score: int,
    experience_score: int,
    location_score: int,
    salary_score: int | None,
    skill_match: dict[str, Any],
    labels: dict[str, str],
    priority: CompanyPriority,
) -> dict[str, Any]:
    """Flat ``scores`` dict for ``ai.tasks.explain_match`` (it reads named keys)."""
    return {
        "match_score": result["score"],
        "skill_score": skill_score,
        "title_score": title_score,
        "experience_score": experience_score,
        "location_score": location_score,
        "salary_score": salary_score,
        "company_priority": priority.value,
        "skill_match": skill_match,
        "missing_skills": skill_match.get("missing", []),
        "experience_match": labels.get("experience"),
        "location_match": labels.get("location"),
        "salary_match": labels.get("salary"),
        "weights": result["weights"],
        "parts": result["parts"],
        "priority_adjustment": result["priority_adjustment"],
    }


def _ai_explanation(job: Job, facts: CandidateFacts, result: dict[str, Any]) -> tuple[str | None, str | None]:
    """``(explanation, model_used)`` from the AI layer, or ``(None, None)``."""
    if facts.context is None:
        return None, None
    try:
        from app.modules.ai.schemas import JobContext
        from app.modules.ai.tasks import explain_match
    except Exception as exc:
        logger.debug("ai.tasks.explain_match unavailable: %s", exc)
        return None, None
    try:
        job_context = JobContext.from_job(job)
        text = explain_match(job_context, facts.context, result)
    except Exception as exc:  # pragma: no cover - never fail a match on the LLM
        logger.warning("explain_match failed: %s", exc)
        return None, None
    if not text:
        return None, None
    model = None
    try:
        from app.modules.ai.factory import get_llm_provider

        provider = get_llm_provider()
        model = getattr(provider, "model", None) or getattr(provider, "name", None)
    except Exception:  # pragma: no cover - the explanation matters, the label does not
        model = None
    return str(text), model


# --------------------------------------------------------------------------- priority


def _company_priority(db: Session, user_id: uuid.UUID, job: Job) -> CompanyPriority:
    from app.modules.jobs.service import get_company_priority

    return get_company_priority(db, user_id, job.company)


# --------------------------------------------------------------------------- analysis


def analyze_job(
    db: Session,
    user_id: uuid.UUID,
    job: Job,
    resume: Resume | None = None,
    *,
    facts: CandidateFacts | None = None,
    priority: CompanyPriority | None = None,
    write_audit: bool = True,
) -> JobMatch:
    """Score ``job`` for ``user_id`` and upsert the :class:`JobMatch` row.

    ``facts`` / ``priority`` are accepted so :func:`analyze_jobs` can compute them once.
    """
    if facts is None:
        facts = build_candidate_facts(db, user_id, resume)
    if priority is None:
        priority = _company_priority(db, user_id, job)

    job_skills = list(job.required_skills or []) + list(job.preferred_skills or [])
    skill_score, matched, missing = scoring.score_skills(
        list(job.required_skills or []), list(job.preferred_skills or []), facts.skills
    )
    title_score = scoring.score_title(job.title, facts.desired_titles)
    experience_score, experience_label = scoring.score_experience(
        job.experience_min, job.experience_max, facts.years_of_experience
    )
    location_score, location_label = scoring.score_location(
        job.location, job.work_mode, facts.preferred_locations, facts.work_modes
    )
    salary_score, salary_label = scoring.score_salary(
        job.salary_min, job.salary_max, facts.min_salary, facts.desired_salary
    )
    preference_score, preference_details = scoring.score_preferences(
        work_mode=job.work_mode,
        employment_type=job.employment_type,
        job_skills=job_skills,
        preferred_work_modes=facts.work_modes,
        preferred_employment_types=facts.employment_types,
        preferred_technologies=facts.preferred_technologies,
        excluded_keywords=facts.excluded_keywords,
        text=f"{job.title}\n{job.description}",
    )
    result = scoring.combine(
        skills=skill_score,
        title=title_score,
        experience=experience_score,
        location=location_score,
        salary=salary_score,
        preference=preference_score,
        priority=priority,
    )
    labels = {"experience": experience_label, "location": location_label, "salary": salary_label}
    skill_match = {
        "matched": matched,
        "missing": missing,
        "total": len(normalize_skills(list(job.required_skills or []))),
    }

    if priority == CompanyPriority.AVOID:
        explanation, model_used = scoring.AVOID_EXPLANATION, None
    else:
        explanation, model_used = _ai_explanation(
            job,
            facts,
            build_explanation_payload(
                result,
                skill_score=skill_score,
                title_score=title_score,
                experience_score=experience_score,
                location_score=location_score,
                salary_score=salary_score,
                skill_match=skill_match,
                labels=labels,
                priority=priority,
            ),
        )
        if not explanation:
            explanation = _fallback_explanation(job, result, missing, labels)

    match = db.scalars(
        select(JobMatch).where(JobMatch.job_id == job.id, JobMatch.user_id == user_id)
    ).first()
    created = match is None
    if match is None:
        match = JobMatch(job_id=job.id, user_id=user_id)
        db.add(match)

    match.resume_id = facts.resume_id
    match.match_score = result["score"]
    match.skill_score = skill_score
    match.experience_score = experience_score
    match.location_score = location_score
    match.salary_score = salary_score
    match.title_score = title_score
    match.company_priority = priority
    match.skill_match = skill_match
    match.experience_match = experience_label
    match.location_match = location_label
    match.salary_match = salary_label
    match.missing_skills = missing
    match.explanation = explanation
    match.details = {**result, "preferences": preference_details}
    match.analyzed_at = utcnow()
    match.model_used = model_used
    db.flush()

    if write_audit:
        audit(
            db,
            action="job.analyzed",
            message=f"{getattr(job.company, 'name', 'Unknown')} - {job.title}: {result['score']}% match",
            user_id=user_id,
            actor=Actor.SYSTEM,
            meta={"job_id": str(job.id), "score": result["score"], "created": created},
        )
    return match


def analyze_jobs(
    db: Session,
    user_id: uuid.UUID,
    jobs: list[Job],
    resume: Resume | None = None,
) -> list[JobMatch]:
    """Analyze many jobs, computing the candidate context and priorities once."""
    if not jobs:
        return []
    facts = build_candidate_facts(db, user_id, resume)
    matches: list[JobMatch] = []
    for job in jobs:
        try:
            matches.append(analyze_job(db, user_id, job, resume, facts=facts))
        except Exception as exc:  # pragma: no cover - one bad job must not abort a run
            logger.exception("Could not analyze job %s: %s", getattr(job, "id", None), exc)
    logger.info("Analyzed %d/%d jobs for user %s", len(matches), len(jobs), user_id)
    return matches


def analyze_all(
    db: Session,
    user_id: uuid.UUID,
    *,
    resume: Resume | None = None,
    only_unanalyzed: bool = False,
    limit: int = 500,
) -> dict[str, Any]:
    """Re-analyze every active job for the user. Returns aggregate counts."""
    stmt = select(Job).where(Job.is_active.is_(True))
    if only_unanalyzed:
        analyzed_ids = select(JobMatch.job_id).where(JobMatch.user_id == user_id)
        stmt = stmt.where(Job.id.not_in(analyzed_ids))
    stmt = stmt.order_by(Job.posted_at.desc().nulls_last()).limit(limit)
    jobs = list(db.scalars(stmt).unique())
    facts = build_candidate_facts(db, user_id, resume)
    matches = [analyze_job(db, user_id, job, resume, facts=facts) for job in jobs]
    scores = [m.match_score for m in matches]
    return {
        "analyzed": len(matches),
        "high_match": sum(1 for s in scores if s >= HIGH_MATCH_SCORE),
        "matched_at_or_above_min": sum(1 for s in scores if s >= facts.min_match_score),
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "skipped": 0,
    }


def build_summary(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    """Counts for ``GET /matching/summary``."""
    from app.models.application import Application

    facts_min = db.scalars(select(JobPreference.min_match_score).where(JobPreference.user_id == user_id)).first()
    min_score = int(facts_min or DEFAULT_MIN_MATCH_SCORE)

    total_jobs = db.scalar(select(func.count(Job.id)).where(Job.is_active.is_(True))) or 0
    analyzed = db.scalar(select(func.count(JobMatch.id)).where(JobMatch.user_id == user_id)) or 0
    at_or_above = (
        db.scalar(
            select(func.count(JobMatch.id)).where(JobMatch.user_id == user_id, JobMatch.match_score >= min_score)
        )
        or 0
    )
    high = (
        db.scalar(
            select(func.count(JobMatch.id)).where(JobMatch.user_id == user_id, JobMatch.match_score >= HIGH_MATCH_SCORE)
        )
        or 0
    )
    queued = (
        db.scalar(
            select(func.count(Application.id)).where(
                Application.user_id == user_id, Application.status == ApplicationStatus.QUEUED
            )
        )
        or 0
    )
    return {
        "total_jobs": int(total_jobs),
        "analyzed": int(analyzed),
        "matched_at_or_above_min": int(at_or_above),
        "high_match": int(high),
        "queued": int(queued),
        "min_match_score": min_score,
    }
