"""Resume improvement recommendations — deterministic analysis, optional LLM wording.

Every recommendation is derived from data the system already has: the resume's
``parsed_data``, the skill taxonomy (``ai/skills.py``), the user's target jobs and their
job preferences. The LLM (``ai.tasks.polish_resume_recommendations``) only rewords the
advice and drafts example text; when it is unavailable the deterministic text is shown
as is and ``ai_polished`` is ``False``.

Target jobs
    The user's top ``DEFAULT_TOP_N`` jobs by stored match score (``JobMatch``) plus every
    job they queued or applied to (any application not ``DISCOVERED`` / ``SKIPPED``).

Health score (``overall_score``)
    Start at 100 and subtract a penalty per recommendation, by priority::

        HIGH 12 | MEDIUM 6 | LOW 2

    The penalties of one category are capped so a single kind of problem cannot sink
    the whole score::

        MISSING_SKILL 30 | KEYWORD_GAP 8 | WEAK_SUMMARY 12 | EXPERIENCE_BULLETS 18
        TITLE_ALIGNMENT 12 | SECTION_MISSING 24 | LENGTH_AND_FORMAT 18 | STALE_CONTENT 4

    The result is clamped to 0-100.

Score projection
    The average match score over the target jobs is recomputed with
    :mod:`app.modules.matching.scoring` (imported, never modified) for the current skills
    and for the skills augmented by every HIGH ``MISSING_SKILL`` recommendation. Both
    numbers are recomputed (not read from ``JobMatch``) so the delta compares like with
    like. Only skills move the match score: title and experience scores come from the
    user's preferences and profile, which a resume edit does not change.

Resume text
    Rules read ``parsed_data``. For the current resume the extracted document text
    (``Resume.text_content``) is added for word counts and keyword presence, because the
    parser keeps only structured fields; older versions are judged on parsed fields alone.

Caching
    Results are computed on demand (no table) and cached in process memory for
    ``CACHE_TTL_SECONDS`` under ``(resume_id, resume.updated_at, jobs fingerprint)``. The
    fingerprint covers the target jobs (id, ``updated_at``, company priority) and the
    ``updated_at`` of the user's profile and job preferences.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, noload

from app.models.application import Application
from app.models.company import Company
from app.models.base import utcnow
from app.models.enums import ApplicationStatus, CompanyPriority
from app.models.job import Job, JobMatch
from app.models.profile import JobPreference, UserProfile
from app.models.resume import Resume, ResumeVersion
from app.modules.ai import tasks as ai_tasks
from app.modules.ai.factory import get_llm_provider
from app.modules.ai.skills import SKILL_ALIASES, extract_skills, normalize_skills, skill_category
from app.modules.jobs.normalize import normalize_title
from app.modules.matching import scoring
from app.modules.resumes.schemas import (
    Recommendation,
    RecommendationEvidence,
    ResumeRecommendations,
    ScoreProjection,
    SkillDemand,
    TargetSummary,
    TitleCount,
    VersionScore,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- weights

PRIORITY_PENALTY: dict[str, int] = {"HIGH": 12, "MEDIUM": 6, "LOW": 2}
CATEGORY_PENALTY_CAP: dict[str, int] = {
    "MISSING_SKILL": 30,
    "KEYWORD_GAP": 8,
    "WEAK_SUMMARY": 12,
    "EXPERIENCE_BULLETS": 18,
    "TITLE_ALIGNMENT": 12,
    "SECTION_MISSING": 24,
    "LENGTH_AND_FORMAT": 18,
    "STALE_CONTENT": 4,
}
CATEGORY_ORDER: tuple[str, ...] = tuple(CATEGORY_PENALTY_CAP)
PRIORITY_RANK: dict[str, int] = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# --------------------------------------------------------------------------- thresholds

DEFAULT_TOP_N = 25
CACHE_TTL_SECONDS = 600
CACHE_MAX_ENTRIES = 256
#: Only the first N recommendations (by priority) are sent to the LLM for rewording.
POLISH_MAX_ITEMS = 12

MISSING_SKILL_MIN_SHARE = 0.30
MISSING_SKILL_MEDIUM_SHARE = 0.40
MISSING_SKILL_HIGH_SHARE = 0.50
MISSING_SKILL_MAX = 8

KEYWORD_MIN_SHARE = 0.30
KEYWORD_MIN_JOBS = 2
KEYWORD_MAX_TERMS = 8
KEYWORD_MEDIUM_TERMS = 4
BOILERPLATE_MIN_JOBS = 5
BOILERPLATE_SHINGLE = 4

SUMMARY_MIN_WORDS = 30
MAX_BULLETS = 8
LONG_RESUME_WORDS = 900
LONG_RESUME_MAX_YEARS = 5
SHORT_RESUME_WORDS = 200
JUNIOR_YEARS = 2
STALE_YEARS = 8
#: ``scoring.score_title`` below this means "does not match, even loosely".
TITLE_ALIGNMENT_MIN = 60
TITLE_ALIGNMENT_HIGH = 40

EXCLUDED_APPLICATION_STATUSES = (ApplicationStatus.DISCOVERED, ApplicationStatus.SKIPPED)

_OUTCOME_RE = re.compile(
    r"\d|%|[$₹€£]|\b(?:reduc|increas|improv|cut|sav|grew|grow|boost|decreas|accelerat|doubl|tripl|halv|half|"
    r"faster|slower|lower|higher|fewer|more than|revenue|profit|uptime|latency)\w*",
    re.IGNORECASE,
)
_YEARS_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty)\s*\+?\s*"
    r"(?:years?|yrs?)\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"(19|20)\d{2}")
_BULLET_SPLIT_RE = re.compile(r"\n+|\s+[•▪●◦]\s+")
_BULLET_MARKER_RE = re.compile(r"^\s*(?:[-*•▪●◦–—·]|\d+[.)])\s*")
_TOKEN_RE = re.compile(r"[a-z][a-z0-9+#]*(?:-[a-z0-9]+)*")
_CURRENT_END = {"present", "current", "now", "till date", "today", "ongoing"}
_LEVEL_WORDS = frozenset(
    {"senior", "junior", "lead", "principal", "staff", "associate", "trainee", "intern", "sr", "jr", "ii", "iii", "iv"}
)
_SOFTWARE_TITLE_RE = re.compile(r"\b(engineer|developer|programmer|sde|swe|architect|devops|sre)\b", re.IGNORECASE)

#: Generic English + job-posting boilerplate that is never a useful ATS keyword.
STOP_WORDS: frozenset[str] = frozenset(
    """
    a about above across after again against all also always among an and any apply applicants are around as at
    based basic be because been before being below benefit benefits best better between bonus both build builds
    building built business but by can candidate candidates career careers change closely come comfortable
    company competitive could create creating culture day days daily deep degree deliver delivering delivery
    demonstrated desired detail details develop developing development different do does doing done drive
    during each eager easy effective effectively employee employees employer employment end ensure environment
    equal etc every excellent exciting expect expected experience experienced expertise fast few field first
    flexible focus following for from full fun function functional get getting give global go good great grow
    growing growth hands has have having help helping high highly hire hiring how ideal identify impact
    important in include includes including individual industry information innovative interest interested into
    is it its job jobs join just key know knowledge large latest lead learn learning least level like looking
    make makes making manage many market may meet member members mission modern more most motivated much must
    need needed needs new next nice not now of offer offers office on one only open opportunities opportunity
    or other others our out over own part passion passionate people perks plus position positions practices
    preferred problem problems product products professional proficiency proficient proven provide quality
    qualifications qualification quickly range real related relevant remote hybrid onsite required requirement
    requirements responsibilities responsible results right role roles salary see self set should similar
    skill skills small so solid solve solving some someone stack startup strong structured success successful
    such support take talent task tasks team teams than that the their them then there these they thing
    things this those through time to tools top track understanding unique up us use used using value values
    variety various very want way ways we well what when where which while who why will willing with within
    without work working works world would write writing year years yrs you your
    engineer engineers engineering developer developers location locations week weeks month months annum
    compensation engagement inr lpa ctc usd per pay paid month
    """.split()
)


# --------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class TargetJob:
    """A target job, detached from the ORM so the rules stay pure and testable."""

    id: str
    title: str
    company: str = ""
    description: str = ""
    location: str | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    required_skills: tuple[str, ...] = ()
    preferred_skills: tuple[str, ...] = ()
    experience_min: float | None = None
    experience_max: float | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    priority: str = CompanyPriority.P2.value
    updated_at: str = ""

    @classmethod
    def from_job(
        cls,
        job: Job,
        priority: CompanyPriority | str | None = None,
        *,
        company_name: str = "",
    ) -> "TargetJob":
        return cls(
            id=str(job.id),
            title=job.title or "",
            company=company_name or "",
            description=job.description or "",
            location=job.location,
            work_mode=_enum_value(job.work_mode),
            employment_type=_enum_value(job.employment_type),
            required_skills=tuple(str(s) for s in (job.required_skills or [])),
            preferred_skills=tuple(str(s) for s in (job.preferred_skills or [])),
            experience_min=job.experience_min,
            experience_max=job.experience_max,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            priority=_enum_value(priority) or CompanyPriority.P2.value,
            updated_at=job.updated_at.isoformat() if getattr(job, "updated_at", None) else "",
        )


@dataclass
class MatchInputs:
    """Everything the scorer needs besides the resume (mirrors ``matching.service``).

    ``base_skills`` are the profile's skills + technologies; the resume's skills are
    added per analysis, exactly as ``matching.service.build_candidate_facts`` does.
    """

    base_skills: list[str] = field(default_factory=list)
    profile_years: float | None = None
    desired_titles: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list)
    work_modes: list[str] = field(default_factory=list)
    employment_types: list[str] = field(default_factory=list)
    preferred_technologies: list[str] = field(default_factory=list)
    excluded_keywords: list[str] = field(default_factory=list)
    min_salary: int | None = None
    desired_salary: int | None = None
    marker: str = ""  # profile/preference updated_at, part of the cache fingerprint


@dataclass
class ResumeView:
    """Pre-digested ``parsed_data``: every rule reads from here."""

    parsed: dict[str, Any]
    summary: str
    skills: list[str]
    experience: list[dict[str, Any]]
    education: list[dict[str, Any]]
    projects: list[dict[str, Any]]
    links: dict[str, Any]
    email: str | None
    phone: str | None
    years: float | None
    text: str
    text_lower: str
    experience_text: str
    text_skills: set[str]
    word_count: int


@dataclass
class TargetContext:
    jobs: list[TargetJob]
    demand: dict[str, list[str]]  # job id -> canonical skills it requires
    skill_counts: Counter
    top_titles: list[TitleCount]
    target_title: str | None
    desired_titles: list[str]
    is_software: bool

    @property
    def size(self) -> int:
        return len(self.jobs)

    def top_skill_names(self, limit: int = 10) -> list[str]:
        return [skill for skill, _ in self.skill_counts.most_common(limit)]


@dataclass
class Analysis:
    overall_score: int
    recommendations: list[Recommendation]
    target_summary: TargetSummary
    projection: ScoreProjection
    resume_payload: dict[str, Any]


# --------------------------------------------------------------------------- small helpers


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _str_list(value: Any) -> list[str]:
    return [str(v) for v in _as_list(value) if v not in (None, "")]


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def slugify(value: str) -> str:
    text = value.lower().replace("++", "pp").replace("#", "sharp")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "item"


def _years_from(value: Any) -> int | None:
    match = _YEAR_RE.search(str(value or ""))
    return int(match.group(0)) if match else None


def _is_current(value: Any) -> bool:
    return str(value or "").strip().lower() in _CURRENT_END


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def split_bullets(description: str | None) -> list[str]:
    """Bullet lines of an experience description (markers stripped, blanks dropped)."""
    if not description or not str(description).strip():
        return []
    bullets = []
    for line in _BULLET_SPLIT_RE.split(str(description)):
        cleaned = _BULLET_MARKER_RE.sub("", line).strip()
        if cleaned:
            bullets.append(cleaned)
    return bullets


def has_outcome(bullet: str) -> bool:
    """A number, a %, a currency or an outcome verb ("reduced", "increased", ...)."""
    return bool(_OUTCOME_RE.search(bullet or ""))


def _mentions(text_lower: str, text_skills: set[str], skill: str) -> bool:
    if skill.lower() in text_skills:
        return True
    return bool(re.search(rf"(?<![a-z0-9+#]){re.escape(skill.lower())}(?![a-z0-9+#])", text_lower))


def _core_title(title: str | None) -> str:
    return " ".join(t for t in normalize_title(title).split() if t not in _LEVEL_WORDS and not t.isdigit())


def _title_mentioned(title: str, text: str) -> bool:
    """Does ``text`` name ``title`` (all core words) or a role from the same family?"""
    core = _core_title(title)
    if not core:
        return False
    text_norm = f" {normalize_title(text)} "
    if all(f" {word} " in text_norm for word in core.split()):
        return True
    for family in scoring.TITLE_FAMILIES:
        if any(member == core or f" {member} " in f" {core} " for member in family):
            if any(f" {member} " in text_norm for member in family):
                return True
    return False



_ALIAS_WORDS: frozenset[str] = frozenset(
    word
    for canonical, aliases in SKILL_ALIASES.items()
    for phrase in [canonical, *aliases]
    for word in re.findall(r"[a-z0-9+#]+", phrase.lower())
)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _token_variants(token: str) -> set[str]:
    variants = {token}
    if token.endswith("s") and len(token) > 3:
        variants.add(token[:-1])
    else:
        variants.add(token + "s")
    return variants


# --------------------------------------------------------------------------- resume view


def build_view(
    parsed: dict[str, Any] | None,
    *,
    profile_years: float | None = None,
    raw_text: str | None = None,
) -> ResumeView:
    """Digest ``parsed_data``.

    ``raw_text`` (the extracted document text, passed only when it belongs to exactly
    this parsed data) refines the word count and keyword presence: the parser keeps
    structured fields only, so parsed text alone undercounts a real resume.
    """
    parsed = parsed if isinstance(parsed, dict) else {}
    experience = [e for e in _as_list(parsed.get("experience")) if isinstance(e, dict)]
    education = [e for e in _as_list(parsed.get("education")) if isinstance(e, dict)]
    projects = [p for p in _as_list(parsed.get("projects")) if isinstance(p, dict)]
    certifications = [c for c in _as_list(parsed.get("certifications")) if isinstance(c, dict)]
    links = parsed.get("links") if isinstance(parsed.get("links"), dict) else {}
    summary = _text(parsed.get("summary"))
    skills = normalize_skills(_str_list(parsed.get("skills")))

    experience_parts: list[str] = []
    for entry in experience:
        experience_parts += [_text(entry.get("title")), _text(entry.get("company")), _text(entry.get("description"))]
        experience_parts += _str_list(entry.get("technologies"))
    for project in projects:
        experience_parts += [_text(project.get("name")), _text(project.get("description"))]
        experience_parts += _str_list(project.get("technologies"))
    experience_text = "\n".join(p for p in experience_parts if p)

    other_parts = [summary, ", ".join(skills)]
    for entry in education:
        other_parts += [_text(entry.get("degree")), _text(entry.get("field")), _text(entry.get("institution"))]
    for cert in certifications:
        other_parts += [_text(cert.get("name")), _text(cert.get("issuer"))]
    text = "\n".join(p for p in [*other_parts, experience_text] if p)
    word_count = len(text.split())
    raw = (raw_text or "").strip()
    if raw:
        word_count = len(raw.split())
        text = f"{text}\n{raw}"

    years = _float_or_none(parsed.get("total_experience_years"))
    if years is None:
        years = profile_years
    return ResumeView(
        parsed=parsed,
        summary=summary,
        skills=skills,
        experience=experience,
        education=education,
        projects=projects,
        links=links or {},
        email=_text(parsed.get("email")) or None,
        phone=_text(parsed.get("phone")) or None,
        years=years,
        text=text,
        text_lower=text.lower(),
        experience_text=experience_text,
        text_skills={s.lower() for s in extract_skills(text)},
        word_count=word_count,
    )


def most_recent_entry(experience: list[dict[str, Any]]) -> tuple[int, dict[str, Any]] | None:
    """The current role (end = Present) or the entry with the latest end year; else the first."""
    if not experience:
        return None
    for index, entry in enumerate(experience):
        if _is_current(entry.get("end")):
            return index, entry
    dated = [(i, e, _years_from(e.get("end")) or _years_from(e.get("start"))) for i, e in enumerate(experience)]
    dated = [d for d in dated if d[2] is not None]
    if dated:
        index, entry, _ = max(dated, key=lambda d: (d[2], -d[0]))
        return index, entry
    return 0, experience[0]


# --------------------------------------------------------------------------- targets


def job_demanded_skills(job: TargetJob) -> list[str]:
    """Required skills, or skills named in the description when none are listed."""
    required = normalize_skills(list(job.required_skills))
    if required:
        return required
    return extract_skills(job.description)


def _is_software_title(title: str | None) -> bool:
    if not title:
        return False
    if _SOFTWARE_TITLE_RE.search(title):
        return True
    core = _core_title(title)
    return any(member == core or f" {member} " in f" {core} " for family in scoring.TITLE_FAMILIES for member in family)


def build_target_context(jobs: list[TargetJob], desired_titles: list[str]) -> TargetContext:
    demand = {job.id: job_demanded_skills(job) for job in jobs}
    skill_counts: Counter = Counter()
    for skills in demand.values():
        skill_counts.update(skills)

    title_counts: Counter = Counter()
    for job in jobs:
        core = _core_title(job.title)
        if core:
            title_counts[core] += 1
    top_titles = [TitleCount(title=core.title(), count=count) for core, count in title_counts.most_common(3)]

    target_title = top_titles[0].title if top_titles else (desired_titles[0] if desired_titles else None)
    titles_for_kind = [job.title for job in jobs] or list(desired_titles)
    software = [t for t in titles_for_kind if _is_software_title(t)]
    is_software = bool(titles_for_kind) and len(software) / len(titles_for_kind) >= 0.5
    return TargetContext(
        jobs=jobs,
        demand=demand,
        skill_counts=skill_counts,
        top_titles=top_titles,
        target_title=target_title,
        desired_titles=list(desired_titles),
        is_software=is_software,
    )


def target_summary(ctx: TargetContext) -> TargetSummary:
    size = ctx.size or 1
    return TargetSummary(
        jobs_analysed=ctx.size,
        top_titles=ctx.top_titles,
        top_skills=[
            SkillDemand(skill=skill, count=count, share=round(count / size, 2))
            for skill, count in ctx.skill_counts.most_common(8)
        ],
    )


# --------------------------------------------------------------------------- match scoring


def candidate_skills(inputs: MatchInputs, view: ResumeView) -> list[str]:
    return normalize_skills(list(inputs.base_skills) + list(view.skills))


def candidate_years(inputs: MatchInputs, view: ResumeView) -> float | None:
    if inputs.profile_years is not None:
        return inputs.profile_years
    return _float_or_none(view.parsed.get("total_experience_years"))


def match_score(job: TargetJob, inputs: MatchInputs, skills: list[str], years: float | None) -> int:
    """The score ``matching.service.analyze_job`` would store, without touching the DB."""
    skill_score, _, _ = scoring.score_skills(list(job.required_skills), list(job.preferred_skills), skills)
    title_score = scoring.score_title(job.title, inputs.desired_titles)
    experience_score, _ = scoring.score_experience(job.experience_min, job.experience_max, years)
    location_score, _ = scoring.score_location(job.location, job.work_mode, inputs.preferred_locations, inputs.work_modes)
    salary_score, _ = scoring.score_salary(job.salary_min, job.salary_max, inputs.min_salary, inputs.desired_salary)
    preference_score, _ = scoring.score_preferences(
        work_mode=job.work_mode,
        employment_type=job.employment_type,
        job_skills=list(job.required_skills) + list(job.preferred_skills),
        preferred_work_modes=inputs.work_modes,
        preferred_employment_types=inputs.employment_types,
        preferred_technologies=inputs.preferred_technologies,
        excluded_keywords=inputs.excluded_keywords,
        text=f"{job.title}\n{job.description}",
    )
    result = scoring.combine(
        skills=skill_score,
        title=title_score,
        experience=experience_score,
        location=location_score,
        salary=salary_score,
        preference=preference_score,
        priority=job.priority,
    )
    return int(result["score"])


def match_scores(jobs: list[TargetJob], inputs: MatchInputs, skills: list[str], years: float | None) -> list[int]:
    return [match_score(job, inputs, skills, years) for job in jobs]


def _average(values: list[int]) -> float:
    return round(sum(values) / len(values), 1) if values else 0.0


# --------------------------------------------------------------------------- rules


def _rec(
    rec_id: str,
    category: str,
    priority: str,
    title: str,
    detail: str,
    evidence: Iterable[RecommendationEvidence] = (),
    **extra: Any,
) -> Recommendation:
    return Recommendation(
        id=rec_id,
        category=category,  # type: ignore[arg-type]
        priority=priority,  # type: ignore[arg-type]
        title=title,
        detail=detail,
        evidence=list(evidence),
        **extra,
    )


def _entry_label(entry: dict[str, Any], index: int) -> str:
    return " at ".join(p for p in (_text(entry.get("title")), _text(entry.get("company"))) if p) or f"Entry {index + 1}"


def _job_evidence(ctx: TargetContext, skill_key: str, limit: int = 5) -> list[RecommendationEvidence]:
    out: list[RecommendationEvidence] = []
    for job in ctx.jobs:
        if skill_key in {s.lower() for s in ctx.demand.get(job.id, [])}:
            label = f"{job.title} at {job.company}" if job.company else job.title
            out.append(RecommendationEvidence(label=label, job_id=job.id))
            if len(out) >= limit:
                break
    return out


def rule_missing_skills(view: ResumeView, ctx: TargetContext, inputs: MatchInputs) -> list[Recommendation]:
    """MISSING_SKILL — required by >= 30 % of target jobs and absent from the skills section."""
    if not ctx.size:
        return []
    listed = {s.lower() for s in view.skills}
    profile_skills = {s.lower() for s in normalize_skills(list(inputs.base_skills))}
    experience_skills = normalize_skills(
        extract_skills(view.experience_text)
        + [t for e in view.experience for t in _str_list(e.get("technologies"))]
        + [t for p in view.projects for t in _str_list(p.get("technologies"))]
    )
    recs: list[Recommendation] = []
    for skill, count in ctx.skill_counts.most_common():
        share = count / ctx.size
        if share < MISSING_SKILL_MIN_SHARE or len(recs) >= MISSING_SKILL_MAX:
            break
        key = skill.lower()
        if key in listed:
            continue
        if share >= MISSING_SKILL_HIGH_SHARE:
            priority = "HIGH"
        elif share >= MISSING_SKILL_MEDIUM_SHARE:
            priority = "MEDIUM"
        else:
            priority = "LOW"
        demand = f"{skill} is required by {count} of {ctx.size} target jobs ({round(share * 100)}%)"
        evidence = _job_evidence(ctx, key)
        if _mentions(view.text_lower, view.text_skills, skill):
            action, title = "list", f"List {skill} in your skills section"
            detail = (
                f"{demand}. Your resume already mentions it in your experience or projects, but not in the skills "
                "section that matching and ATS filters read first."
            )
        elif key in profile_skills:
            action, title = "list", f"Put {skill} on your resume"
            detail = f"{demand}. Your profile lists {skill}, but your resume does not mention it anywhere."
        else:
            category = skill_category(skill)
            related = [
                s for s in experience_skills
                if category != "other" and skill_category(s) == category and s.lower() != key
            ]
            if related:
                action, title = "add", f"Add {skill} if you have used it"
                detail = (
                    f"{demand}. Your experience shows related {category} skills ({', '.join(related[:3])}). If you "
                    f"have worked with {skill}, add it to your skills and to the bullet where you used it; if not, "
                    "it is the closest gap to close."
                )
                evidence.append(RecommendationEvidence(label=f"Related: {', '.join(related[:3])}", field="experience"))
            else:
                action, title = "learn", f"Learn {skill}"
                detail = (
                    f"{demand}, and nothing on your resume mentions it or a related skill. Consider learning it (a "
                    "small project counts) before adding it to your resume."
                )
        recs.append(
            _rec(
                f"missing-skill-{slugify(skill)}",
                "MISSING_SKILL",
                priority,
                title,
                detail,
                evidence,
                action=action,
                skills=[skill],
            )
        )
    return recs


def _line_tokens(description: str) -> list[list[str]]:
    """Tokens per line: phrases never span a line break (a heading is not a phrase)."""
    return [_TOKEN_RE.findall(line) for line in description.lower().splitlines()]


def _shingles(tokens: list[str]) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + BOILERPLATE_SHINGLE]) for i in range(len(tokens) - BOILERPLATE_SHINGLE + 1)}


def boilerplate_shingles(jobs: list[TargetJob]) -> set[tuple[str, ...]]:
    """Word 4-grams shared by at least half of the posts (templates, EEO text, perks).

    Phrases repeated across that many different posts say nothing about what *these*
    jobs want, so the words inside them are not ATS keywords. Shingles rather than whole
    lines, so a template line that only differs by a team or company name still counts.
    """
    if len(jobs) < BOILERPLATE_MIN_JOBS:
        return set()
    counts: Counter = Counter()
    for job in jobs:
        counts.update(set().union(*(_shingles(line) for line in _line_tokens(job.description))))
    threshold = max(BOILERPLATE_MIN_JOBS, len(jobs) / 2)
    return {shingle for shingle, count in counts.items() if count >= threshold}


def distinctive_tokens(job: TargetJob, boilerplate: set[tuple[str, ...]]) -> set[str]:
    """Title words plus description words not covered by a boilerplate shingle."""
    found = _tokens(job.title)
    for tokens in _line_tokens(job.description):
        covered = [False] * len(tokens)
        for i in range(len(tokens) - BOILERPLATE_SHINGLE + 1):
            if tuple(tokens[i : i + BOILERPLATE_SHINGLE]) in boilerplate:
                covered[i : i + BOILERPLATE_SHINGLE] = [True] * BOILERPLATE_SHINGLE
        found |= {token for token, hit in zip(tokens, covered) if not hit}
    return found


def rule_keyword_gap(view: ResumeView, ctx: TargetContext) -> list[Recommendation]:
    """KEYWORD_GAP — frequent non-skill terms of the target posts missing from the resume."""
    if not ctx.size:
        return []
    noise = set(STOP_WORDS) | _ALIAS_WORDS | _LEVEL_WORDS
    for job in ctx.jobs:
        noise |= _tokens(job.company) | _tokens(job.location or "")
    resume_tokens = _tokens(view.text)
    boilerplate = boilerplate_shingles(ctx.jobs)
    doc_freq: Counter = Counter()
    for job in ctx.jobs:
        doc_freq.update(t for t in distinctive_tokens(job, boilerplate) if len(t) >= 3 and t not in noise)
    threshold = max(KEYWORD_MIN_JOBS, KEYWORD_MIN_SHARE * ctx.size)
    terms: list[tuple[str, int]] = []
    for term, count in sorted(doc_freq.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < threshold:
            break
        if _token_variants(term) & resume_tokens:
            continue
        if any(term in _token_variants(kept) for kept, _ in terms):
            continue
        terms.append((term, count))
        if len(terms) >= KEYWORD_MAX_TERMS:
            break
    if not terms:
        return []
    words = ", ".join(term for term, _ in terms)
    return [
        _rec(
            "keyword-gap",
            "KEYWORD_GAP",
            "MEDIUM" if len(terms) >= KEYWORD_MEDIUM_TERMS else "LOW",
            "Use the language of your target job posts",
            f"These terms appear in many of your target job posts but nowhere on your resume: {words}. Use them "
            "where they truthfully describe your work; ATS filters match on exact words.",
            [RecommendationEvidence(label=f"{term}: {count} of {ctx.size} jobs") for term, count in terms],
        )
    ]


def summary_skills(view: ResumeView, ctx: TargetContext) -> list[str]:
    """Up to three of the candidate's own skills, the ones target jobs ask for first."""
    listed = {s.lower(): s for s in view.skills}
    wanted = [listed[s.lower()] for s in ctx.top_skill_names(20) if s.lower() in listed]
    return list(dict.fromkeys([*wanted, *view.skills]))[:3]


def _format_years(years: float) -> str:
    return str(int(years)) if float(years).is_integer() else str(years)


def rule_weak_summary(view: ResumeView, ctx: TargetContext) -> list[Recommendation]:
    """WEAK_SUMMARY — missing, under 30 words, or lacking title / years / top three skills."""
    if not view.summary:
        return [
            _rec(
                "weak-summary",
                "WEAK_SUMMARY",
                "HIGH",
                "Add a professional summary",
                "Your resume has no summary. Open with two or three lines naming the role you are targeting, your "
                "years of experience and your strongest relevant skills.",
                [RecommendationEvidence(label="summary", field="summary")],
                skills=summary_skills(view, ctx),
            )
        ]
    issues: list[str] = []
    word_count = len(view.summary.split())
    short = word_count < SUMMARY_MIN_WORDS
    if short:
        issues.append(f"it is only {word_count} words")
    titles = [t for t in [ctx.target_title, *ctx.desired_titles] if t]
    if titles and not any(_title_mentioned(t, view.summary) for t in titles):
        issues.append(f"it does not name the role you are targeting ({titles[0]})")
    if view.years and not _YEARS_RE.search(view.summary):
        issues.append(f"it does not state your {_format_years(view.years)} years of experience")
    top = summary_skills(view, ctx)
    summary_lower = view.summary.lower()
    summary_skill_set = {s.lower() for s in extract_skills(view.summary)}
    absent = [s for s in top if not _mentions(summary_lower, summary_skill_set, s)]
    if absent:
        issues.append(f"it does not mention {', '.join(absent)}")
    if not issues:
        return []
    return [
        _rec(
            "weak-summary",
            "WEAK_SUMMARY",
            "MEDIUM" if short or len(issues) >= 2 else "LOW",
            "Sharpen your summary",
            "Your summary could work harder: " + "; ".join(issues) + ".",
            [RecommendationEvidence(label=view.summary[:160], field="summary")],
            skills=top,
        )
    ]


def rule_experience_bullets(view: ResumeView) -> list[Recommendation]:
    """EXPERIENCE_BULLETS — no bullets, bullets without an outcome, or more than 8 bullets."""
    recs: list[Recommendation] = []
    seen: set[str] = set()
    current = most_recent_entry(view.experience)
    for index, entry in enumerate(view.experience):
        where = _entry_label(entry, index)
        bullets = split_bullets(entry.get("description"))
        issues: list[str] = []
        rank = 3  # 0 HIGH, 1 MEDIUM, 2 LOW
        evidence = [RecommendationEvidence(label=where, field=f"experience[{index}]")]
        if not bullets:
            issues.append("has no bullet points: add three to five describing what you built and what changed")
            rank = 0 if current is not None and current[0] == index else 1
        else:
            weak = [b for b in bullets if not has_outcome(b)]
            if weak:
                issues.append(
                    f"has {len(weak)} of {len(bullets)} bullets with no number or outcome: say what changed "
                    "(time saved, users served, % improved, cost cut)"
                )
                rank = min(rank, 1 if len(weak) * 2 >= len(bullets) else 2)
                evidence += [RecommendationEvidence(label=b, field=f"experience[{index}].bullet") for b in weak[:3]]
            if len(bullets) > MAX_BULLETS:
                issues.append(f"has {len(bullets)} bullets: keep the strongest five to eight")
                rank = min(rank, 2)
        if not issues:
            continue
        slug = slugify(_text(entry.get("company")) or _text(entry.get("title")) or str(index + 1))
        rec_id, n = f"experience-bullets-{slug}", 2
        while rec_id in seen:
            rec_id, n = f"experience-bullets-{slug}-{n}", n + 1
        seen.add(rec_id)
        recs.append(
            _rec(
                rec_id,
                "EXPERIENCE_BULLETS",
                ("HIGH", "MEDIUM", "LOW")[rank],
                f"Strengthen the bullets for {where}",
                f"{where} " + "; it ".join(issues) + ".",
                evidence,
            )
        )
    return recs


def rule_title_alignment(view: ResumeView, ctx: TargetContext) -> list[Recommendation]:
    """TITLE_ALIGNMENT — the most recent title matches no desired / common target title."""
    found = most_recent_entry(view.experience)
    targets = list(dict.fromkeys(t for t in [*ctx.desired_titles, ctx.target_title] if t))
    if found is None or not targets:
        return []
    index, entry = found
    recent = _text(entry.get("title"))
    if not recent:
        return []
    score = scoring.score_title(recent, targets)
    if score >= TITLE_ALIGNMENT_MIN:
        return []
    return [
        _rec(
            "title-alignment",
            "TITLE_ALIGNMENT",
            "HIGH" if score < TITLE_ALIGNMENT_HIGH else "MEDIUM",
            "Connect your current title to the roles you target",
            f'Your most recent title, "{recent}", does not match the roles you are targeting '
            f"({', '.join(targets[:3])}). Keep your real title, but make the link explicit: name the target role in "
            "your summary and lead with the work closest to it.",
            [
                RecommendationEvidence(label=recent, field=f"experience[{index}].title"),
                *[RecommendationEvidence(label=f"Target: {t}") for t in targets[:3]],
            ],
        )
    ]


def rule_section_missing(view: ResumeView, ctx: TargetContext) -> list[Recommendation]:
    """SECTION_MISSING — skills, education, links for software roles, projects for juniors."""
    recs: list[Recommendation] = []
    if not view.skills:
        recs.append(
            _rec(
                "section-missing-skills",
                "SECTION_MISSING",
                "HIGH",
                "Add a skills section",
                "Your resume has no skills section. Matching and ATS filters read it first; list the tools and "
                "languages you have actually used.",
                [RecommendationEvidence(label="skills", field="skills")],
            )
        )
    if not view.education:
        recs.append(
            _rec(
                "section-missing-education",
                "SECTION_MISSING",
                "MEDIUM",
                "Add an education section",
                "Your resume has no education section. Many screening filters expect one; add your degree or "
                "relevant training exactly as it appears on your records.",
                [RecommendationEvidence(label="education", field="education")],
            )
        )
    if ctx.is_software:
        missing = [name for name, key in (("GitHub", "github"), ("LinkedIn", "linkedin")) if not view.links.get(key)]
        if missing:
            recs.append(
                _rec(
                    "section-missing-links",
                    "SECTION_MISSING",
                    "MEDIUM" if len(missing) == 2 else "LOW",
                    f"Add your {' and '.join(missing)} link{'s' if len(missing) == 2 else ''}",
                    f"Your target jobs are software roles and your resume has no {' or '.join(missing)} link. "
                    "Reviewers use them to check your work.",
                    [RecommendationEvidence(label=name, field="links") for name in missing],
                )
            )
    junior = view.years < JUNIOR_YEARS if view.years is not None else not view.experience
    if junior and not view.projects:
        recs.append(
            _rec(
                "section-missing-projects",
                "SECTION_MISSING",
                "MEDIUM",
                "Add a projects section",
                "With under two years of experience, projects are your best evidence. Add the ones you have built, "
                "with the stack you used and what they do.",
                [RecommendationEvidence(label="projects", field="projects")],
            )
        )
    return recs


def rule_length_and_format(view: ResumeView) -> list[Recommendation]:
    """LENGTH_AND_FORMAT — length vs experience, contact details, dates on entries."""
    recs: list[Recommendation] = []
    if view.word_count > LONG_RESUME_WORDS and view.years is not None and view.years < LONG_RESUME_MAX_YEARS:
        recs.append(
            _rec(
                "format-too-long",
                "LENGTH_AND_FORMAT",
                "MEDIUM",
                "Trim your resume to one page",
                f"Your resume has about {view.word_count} words. With under five years of experience, aim for one "
                "page: cut older or less relevant bullets first.",
                [RecommendationEvidence(label=f"{view.word_count} words")],
            )
        )
    if view.word_count < SHORT_RESUME_WORDS:
        recs.append(
            _rec(
                "format-too-short",
                "LENGTH_AND_FORMAT",
                "MEDIUM",
                "Give reviewers more to go on",
                f"Your resume has only about {view.word_count} words. Describe what you built in each role and "
                "project, and the result.",
                [RecommendationEvidence(label=f"{view.word_count} words")],
            )
        )
    missing_contact = [name for name, value in (("email", view.email), ("phone number", view.phone)) if not value]
    if missing_contact:
        recs.append(
            _rec(
                "format-contact-details",
                "LENGTH_AND_FORMAT",
                "HIGH" if not view.email else "MEDIUM",
                "Add your contact details",
                f"Your resume has no {' or '.join(missing_contact)}. Recruiters cannot reach you without it.",
                [
                    RecommendationEvidence(label=name, field="email" if name == "email" else "phone")
                    for name in missing_contact
                ],
            )
        )
    undated = [
        (index, entry)
        for index, entry in enumerate(view.experience)
        if not _text(entry.get("start")) or not _text(entry.get("end"))
    ]
    if undated:
        recs.append(
            _rec(
                "format-missing-dates",
                "LENGTH_AND_FORMAT",
                "MEDIUM",
                "Add dates to every role",
                "Some experience entries have no start or end date. Reviewers and ATS parsers use them to work out "
                "your experience; add the month and year for each.",
                [RecommendationEvidence(label=_entry_label(e, i), field=f"experience[{i}]") for i, e in undated],
            )
        )
    return recs


def rule_stale_content(view: ResumeView, ctx: TargetContext, today: date) -> list[Recommendation]:
    """STALE_CONTENT — roles / skills older than 8 years that no target job asks for."""
    wanted = {s.lower() for skills in ctx.demand.values() for s in skills}
    for job in ctx.jobs:
        wanted |= {s.lower() for s in normalize_skills(list(job.preferred_skills))}

    def entry_skills(entry: dict[str, Any]) -> set[str]:
        raw = _str_list(entry.get("technologies")) + extract_skills(_text(entry.get("description")))
        return {s.lower() for s in normalize_skills(raw)}

    stale: list[tuple[int, dict[str, Any]]] = []
    recent_skills: set[str] = set()
    for index, entry in enumerate(view.experience):
        end_year = today.year if _is_current(entry.get("end")) else _years_from(entry.get("end"))
        if end_year is not None and today.year - end_year > STALE_YEARS:
            if not entry_skills(entry) & wanted:
                stale.append((index, entry))
        else:
            recent_skills |= entry_skills(entry)
    if not stale:
        return []
    for project in view.projects:
        recent_skills |= {s.lower() for s in normalize_skills(_str_list(project.get("technologies")))}
    recent_skills |= {s.lower() for s in extract_skills(view.summary)}
    old_skills = set().union(*(entry_skills(e) for _, e in stale))
    stale_skill_names = [s for s in view.skills if s.lower() in old_skills and s.lower() not in recent_skills | wanted]

    evidence = [
        RecommendationEvidence(label=f"{_entry_label(e, i)} (ended {_text(e.get('end'))})", field=f"experience[{i}]")
        for i, e in stale
    ]
    plural = len(stale) > 1
    detail = (
        f"{len(stale)} role{'s' if plural else ''} ended more than {STALE_YEARS} years ago and use{'' if plural else 's'} "
        "nothing your target jobs ask for. Shorten them to one line each to make room for recent work."
    )
    if stale_skill_names:
        detail += f" Skills only used there ({', '.join(stale_skill_names[:5])}) can move to the end of your skills list."
        evidence.append(RecommendationEvidence(label=", ".join(stale_skill_names[:5]), field="skills"))
    return [
        _rec("stale-content", "STALE_CONTENT", "LOW", "Condense older roles", detail, evidence, skills=stale_skill_names[:5])
    ]


# --------------------------------------------------------------------------- scoring & analysis


def overall_score(recommendations: list[Recommendation]) -> int:
    """100 minus capped per-category penalties, clamped to 0-100 (weights at the top)."""
    per_category: Counter = Counter()
    for rec in recommendations:
        per_category[rec.category] += PRIORITY_PENALTY[rec.priority]
    penalty = sum(min(total, CATEGORY_PENALTY_CAP.get(category, total)) for category, total in per_category.items())
    return max(0, min(100, 100 - penalty))


def _sort_key(rec: Recommendation) -> tuple:
    return (PRIORITY_RANK[rec.priority], -rec.estimated_score_gain, CATEGORY_ORDER.index(rec.category), rec.id)


def resume_payload(view: ResumeView, ctx: TargetContext) -> dict[str, Any]:
    """The resume facts the LLM may use; nothing else about the candidate reaches the prompt."""
    found = most_recent_entry(view.experience)
    recent_title = (_text(found[1].get("title")) or None) if found else None
    return {
        "summary": view.summary or None,
        "recent_title": recent_title,
        "total_experience_years": view.years,
        "skills": view.skills[:30],
        "summary_skills": summary_skills(view, ctx),
        "target_title": ctx.target_title,
        "experience": [
            {
                "title": _text(e.get("title")) or None,
                "company": _text(e.get("company")) or None,
                "start": _text(e.get("start")) or None,
                "end": _text(e.get("end")) or None,
                "bullets": split_bullets(e.get("description"))[:MAX_BULLETS],
            }
            for e in view.experience[:4]
        ],
        "projects": [_text(p.get("name")) for p in view.projects if _text(p.get("name"))][:5],
    }


def analyze_resume(
    parsed: dict[str, Any] | None,
    targets: list[TargetJob],
    inputs: MatchInputs,
    *,
    today: date | None = None,
    with_gains: bool = True,
    raw_text: str | None = None,
) -> Analysis:
    """Run every rule over one ``parsed_data`` — pure: no DB, no LLM."""
    today = today or utcnow().date()
    view = build_view(parsed, profile_years=inputs.profile_years, raw_text=raw_text)
    ctx = build_target_context(targets, inputs.desired_titles)

    recs: list[Recommendation] = [
        *rule_missing_skills(view, ctx, inputs),
        *rule_keyword_gap(view, ctx),
        *rule_weak_summary(view, ctx),
        *rule_experience_bullets(view),
        *rule_title_alignment(view, ctx),
        *rule_section_missing(view, ctx),
        *rule_length_and_format(view),
        *rule_stale_content(view, ctx, today),
    ]

    skills = candidate_skills(inputs, view)
    years = candidate_years(inputs, view)
    current_scores = match_scores(targets, inputs, skills, years)
    current = _average(current_scores)

    if with_gains and targets:
        for rec in recs:
            if rec.category == "MISSING_SKILL" and rec.skills:
                gained = _average(match_scores(targets, inputs, normalize_skills(skills + rec.skills), years))
                rec.estimated_score_gain = round(max(0.0, gained - current), 1)

    added = list(
        dict.fromkeys(s for r in recs if r.category == "MISSING_SKILL" and r.priority == "HIGH" for s in r.skills)
    )
    if targets and added:
        projected_scores = match_scores(targets, inputs, normalize_skills(skills + added), years)
        projected = _average(projected_scores)
        improved = sum(1 for before, after in zip(current_scores, projected_scores) if after > before)
    else:
        projected, improved = current, 0

    recs.sort(key=_sort_key)
    return Analysis(
        overall_score=overall_score(recs),
        recommendations=recs,
        target_summary=target_summary(ctx),
        projection=ScoreProjection(
            current_average=current,
            projected_average=projected,
            delta=round(projected - current, 1),
            added_skills=added,
            jobs_improved=improved,
        ),
        resume_payload=resume_payload(view, ctx),
    )


# --------------------------------------------------------------------------- LLM polish


def polish(analysis: Analysis) -> tuple[list[Recommendation], bool, str | None]:
    """Reword the top recommendations with the LLM; any failure keeps the deterministic text.

    Returns ``(recommendations, ai_polished, provider_name)``.
    """
    recs = analysis.recommendations
    if not recs:
        return recs, False, None
    provider_name: str | None = None
    try:
        provider_name = getattr(get_llm_provider(), "name", None)
        result = ai_tasks.polish_resume_recommendations(analysis.resume_payload, recs[:POLISH_MAX_ITEMS])
    except Exception as exc:  # noqa: BLE001 - the deterministic text is always a valid answer
        logger.warning("Resume recommendation polish failed (%s); showing the deterministic text", exc)
        return recs, False, provider_name
    if not result.items:
        return recs, False, provider_name
    by_id = {item.id: item for item in result.items}
    polished: list[Recommendation] = []
    for rec in recs:
        item = by_id.get(rec.id)
        if item is None:
            polished.append(rec)
            continue
        polished.append(
            rec.model_copy(
                update={"detail": item.detail or rec.detail, "suggested_text": item.suggested_text or rec.suggested_text}
            )
        )
    return polished, True, provider_name


# --------------------------------------------------------------------------- DB inputs


def load_target_jobs(db: Session, user_id: uuid.UUID, *, top_n: int = DEFAULT_TOP_N) -> list[TargetJob]:
    """Top-N jobs by stored match score plus every job the user queued or applied to.

    The company priority is the one already resolved for that user: ``JobMatch`` first
    (it is what the stored score used), then ``Application.priority``, else P2. Only the
    company *name* is read, so no full ``Company`` row is loaded.
    """
    ranked = db.execute(
        select(JobMatch.job_id, JobMatch.company_priority)
        .join(Job, Job.id == JobMatch.job_id)
        .where(JobMatch.user_id == user_id, Job.is_active.is_(True))
        .order_by(JobMatch.match_score.desc(), JobMatch.analyzed_at.desc(), JobMatch.job_id)
        .limit(max(0, int(top_n)))
    ).all()
    applied = db.execute(
        select(Application.job_id, Application.priority)
        .where(Application.user_id == user_id, Application.status.not_in(EXCLUDED_APPLICATION_STATUSES))
        .order_by(Application.job_id)
    ).all()
    priorities: dict[uuid.UUID, Any] = {}
    for job_id, priority in [*applied, *ranked]:  # the match's priority wins
        if priority is not None:
            priorities[job_id] = priority
    ordered_ids = list(dict.fromkeys([row[0] for row in ranked] + [row[0] for row in applied]))
    if not ordered_ids:
        return []
    jobs = {
        job.id: job
        for job in db.scalars(select(Job).options(noload(Job.company)).where(Job.id.in_(ordered_ids)))
    }
    company_ids = {job.company_id for job in jobs.values()}
    names = dict(db.execute(select(Company.id, Company.name).where(Company.id.in_(company_ids))).all())
    return [
        TargetJob.from_job(jobs[job_id], priorities.get(job_id), company_name=names.get(jobs[job_id].company_id, ""))
        for job_id in ordered_ids
        if job_id in jobs
    ]


def load_match_inputs(db: Session, user_id: uuid.UUID) -> MatchInputs:
    """Profile + preferences, read the way ``matching.service.build_candidate_facts`` reads them."""
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == user_id)).first()
    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == user_id)).first()
    marker = "|".join(
        row.updated_at.isoformat() if row is not None and getattr(row, "updated_at", None) else "-"
        for row in (profile, preference)
    )
    return MatchInputs(
        base_skills=normalize_skills(
            _str_list(getattr(profile, "skills", None)) + _str_list(getattr(profile, "technologies", None))
        ),
        profile_years=_float_or_none(getattr(profile, "years_of_experience", None)),
        desired_titles=_str_list(getattr(preference, "desired_titles", None)),
        preferred_locations=_str_list(getattr(preference, "preferred_locations", None)),
        work_modes=_str_list(getattr(preference, "work_modes", None)),
        employment_types=_str_list(getattr(preference, "employment_types", None)),
        preferred_technologies=_str_list(getattr(preference, "preferred_technologies", None)),
        excluded_keywords=_str_list(getattr(preference, "excluded_keywords", None)),
        min_salary=getattr(preference, "min_salary", None),
        desired_salary=getattr(preference, "desired_salary", None),
        marker=marker,
    )


# --------------------------------------------------------------------------- cache

CacheKey = tuple[str, str, str]
_CACHE: dict[CacheKey, tuple[float, ResumeRecommendations]] = {}
_CACHE_LOCK = threading.Lock()
#: Monotonic clock; tests replace it to move time forward.
_clock = time.monotonic


def jobs_fingerprint(targets: list[TargetJob], inputs: MatchInputs) -> str:
    digest = hashlib.sha256()
    for job in sorted(targets, key=lambda j: j.id):
        digest.update(f"{job.id}:{job.updated_at}:{job.priority};".encode())
    digest.update(f"inputs:{inputs.marker}".encode())
    return digest.hexdigest()[:24]


def cache_key(resume: Resume, fingerprint: str) -> CacheKey:
    updated = resume.updated_at.isoformat() if getattr(resume, "updated_at", None) else ""
    return (str(resume.id), updated, fingerprint)


def cache_get(key: CacheKey) -> ResumeRecommendations | None:
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is None:
            return None
        expires_at, value = hit
        if expires_at <= _clock():
            _CACHE.pop(key, None)
            return None
        return value


def cache_put(key: CacheKey, value: ResumeRecommendations) -> None:
    with _CACHE_LOCK:
        now = _clock()
        for expired in [k for k, (expires_at, _) in _CACHE.items() if expires_at <= now]:
            _CACHE.pop(expired, None)
        while len(_CACHE) >= CACHE_MAX_ENTRIES:
            _CACHE.pop(min(_CACHE, key=lambda k: _CACHE[k][0]))
        _CACHE[key] = (now + CACHE_TTL_SECONDS, value)


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


# --------------------------------------------------------------------------- public API


def version_history(
    db: Session,
    resume: Resume,
    targets: list[TargetJob],
    inputs: MatchInputs,
    *,
    today: date | None = None,
) -> list[VersionScore]:
    """Overall score and average match score every stored version would get today."""
    versions = db.scalars(
        select(ResumeVersion).where(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number)
    )
    history: list[VersionScore] = []
    current_parsed = resume.parsed_data or {}
    for version in versions:
        parsed = version.parsed_data or {}
        # The extracted text belongs to the current parsed data only; older versions
        # are judged on their parsed fields alone.
        raw_text = resume.text_content if parsed == current_parsed else None
        analysis = analyze_resume(parsed, targets, inputs, today=today, with_gains=False, raw_text=raw_text)
        history.append(
            VersionScore(
                version_number=version.version_number,
                created_at=version.created_at,
                note=version.note,
                overall_score=analysis.overall_score,
                average_match_score=analysis.projection.current_average,
                is_current=version.version_number == resume.current_version,
            )
        )
    return history


def build_recommendations(
    db: Session,
    user_id: uuid.UUID,
    resume: Resume,
    *,
    refresh: bool = False,
    top_n: int = DEFAULT_TOP_N,
    today: date | None = None,
) -> ResumeRecommendations:
    """Recommendations for ``resume`` (ownership already checked by the caller)."""
    targets = load_target_jobs(db, user_id, top_n=top_n)
    inputs = load_match_inputs(db, user_id)
    key = cache_key(resume, jobs_fingerprint(targets, inputs))
    if not refresh:
        cached = cache_get(key)
        if cached is not None:
            return cached.model_copy(update={"cached": True})

    analysis = analyze_resume(resume.parsed_data or {}, targets, inputs, today=today, raw_text=resume.text_content)
    recs, polished, provider = polish(analysis)
    result = ResumeRecommendations(
        resume_id=resume.id,
        resume_version=int(resume.current_version or 1),
        generated_at=utcnow(),
        overall_score=analysis.overall_score,
        target_summary=analysis.target_summary,
        recommendations=recs,
        score_projection=analysis.projection,
        version_history=version_history(db, resume, targets, inputs, today=today),
        ai_polished=polished,
        ai_provider=provider,
        cached=False,
    )
    cache_put(key, result)
    return result


def build_version_history(
    db: Session,
    user_id: uuid.UUID,
    resume: Resume,
    *,
    top_n: int = DEFAULT_TOP_N,
    today: date | None = None,
) -> list[VersionScore]:
    """Only the history; served from a warm recommendations cache, never calls the LLM."""
    targets = load_target_jobs(db, user_id, top_n=top_n)
    inputs = load_match_inputs(db, user_id)
    cached = cache_get(cache_key(resume, jobs_fingerprint(targets, inputs)))
    if cached is not None:
        return cached.version_history
    return version_history(db, resume, targets, inputs, today=today)


__all__ = [
    "CATEGORY_PENALTY_CAP",
    "PRIORITY_PENALTY",
    "Analysis",
    "MatchInputs",
    "TargetJob",
    "analyze_resume",
    "build_recommendations",
    "build_version_history",
    "cache_key",
    "clear_cache",
    "has_outcome",
    "jobs_fingerprint",
    "match_score",
    "overall_score",
    "polish",
    "split_bullets",
]
