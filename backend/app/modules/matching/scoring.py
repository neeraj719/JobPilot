"""Deterministic match scoring (``docs/CONTRACTS.md`` §10).

Every function here is **pure** — no database, no LLM, no clock — so the score a user
sees can always be explained and unit tested. The LLM only ever writes the prose
explanation on top of these numbers.

Weights::

    skills 0.40 | title 0.15 | experience 0.20 | location 0.10 | salary 0.10 | preferences 0.05

A component whose inputs are unknown (typically salary) is dropped and its weight is
redistributed proportionally over the remaining components. Company priority adds at
most +5 (P1) / +2 (P2) on top, and ``AVOID`` forces the score to 0.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from rapidfuzz import fuzz

from app.models.enums import CompanyPriority, WorkMode
from app.modules.ai.skills import normalize_skills, skills_overlap
from app.modules.jobs.normalize import is_remote_location, normalize_location, normalize_title

logger = logging.getLogger(__name__)

WEIGHTS: dict[str, float] = {
    "skills": 0.40,
    "title": 0.15,
    "experience": 0.20,
    "location": 0.10,
    "salary": 0.10,
    "preference": 0.05,
}

#: Extra points a company priority may add. ``AVOID`` is handled separately (score 0).
PRIORITY_BONUS: dict[CompanyPriority, int] = {
    CompanyPriority.P1: 5,
    CompanyPriority.P2: 2,
    CompanyPriority.P3: 0,
    CompanyPriority.AVOID: 0,
}

AVOID_EXPLANATION = "Company is on your avoid list"

#: Weight of required vs preferred skills inside the skill score.
REQUIRED_SKILL_WEIGHT = 0.75
PREFERRED_SKILL_WEIGHT = 0.25

#: Score used when a component has no signal at all.
NEUTRAL_SCORE = 60

# Experience labels
STRONG, GOOD, UNDER, OVER, UNKNOWN = "STRONG", "GOOD", "UNDER", "OVER", "UNKNOWN"
# Location labels
MATCH, REMOTE_OK, MISMATCH = "MATCH", "REMOTE_OK", "MISMATCH"
# Salary labels
ABOVE, WITHIN, BELOW = "ABOVE", "WITHIN", "BELOW"


# --------------------------------------------------------------------------- skills


def score_skills(
    required: list[str] | None,
    preferred: list[str] | None,
    candidate_skills: list[str] | None,
) -> tuple[int, list[str], list[str]]:
    """Return ``(score 0-100, matched skills, missing required skills)``.

    Required skills carry 75% of the skill score, preferred skills 25%. When the job
    lists only preferred skills they carry the whole score; when it lists none at all
    the score is neutral (we cannot penalise a vague posting).
    """
    required_norm = normalize_skills(list(required or []))
    preferred_norm = normalize_skills(list(preferred or []))
    candidate_norm = normalize_skills(list(candidate_skills or []))

    req_matched, req_missing = skills_overlap(required_norm, candidate_norm)
    pref_matched, pref_missing = skills_overlap(preferred_norm, candidate_norm)

    if not required_norm and not preferred_norm:
        return NEUTRAL_SCORE, [], []

    req_ratio = len(req_matched) / len(required_norm) if required_norm else None
    pref_ratio = len(pref_matched) / len(preferred_norm) if preferred_norm else None

    if req_ratio is not None and pref_ratio is not None:
        raw = REQUIRED_SKILL_WEIGHT * req_ratio + PREFERRED_SKILL_WEIGHT * pref_ratio
    elif req_ratio is not None:
        raw = req_ratio
    else:
        raw = pref_ratio or 0.0

    matched = req_matched + [s for s in pref_matched if s not in req_matched]
    missing = req_missing if required_norm else pref_missing
    return int(round(raw * 100)), matched, missing


# --------------------------------------------------------------------------- title

#: Roles that mean the same thing for matching purposes.
TITLE_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset(
        {
            "software engineer",
            "software development engineer",
            "software developer",
            "application developer",
            "member of technical staff",
            "programmer analyst",
            "software engineer in test",
        }
    ),
    frozenset({"full stack developer", "full stack engineer", "mern developer", "mean developer"}),
    frozenset({"backend engineer", "backend developer", "server side engineer", "api developer", "node js developer", "python developer", "java developer"}),
    frozenset({"frontend engineer", "frontend developer", "ui developer", "react developer", "web developer", "javascript developer"}),
    frozenset({"data engineer", "big data engineer", "etl developer", "analytics engineer"}),
    frozenset({"devops engineer", "site reliability engineer", "platform engineer", "cloud engineer", "infrastructure engineer"}),
    frozenset({"mobile engineer", "android developer", "ios developer", "react native developer", "flutter developer"}),
    frozenset({"machine learning engineer", "ml engineer", "ai engineer", "data scientist"}),
)

_LEVEL_TOKENS: frozenset[str] = frozenset({"senior", "junior", "lead", "principal", "staff", "associate", "trainee", "intern", "1", "2", "3", "4", "5", "i", "ii", "iii"})

#: Score floor when two titles belong to the same family.
FAMILY_FLOOR_SCORE = 85


def _strip_levels(normalized: str) -> str:
    return " ".join(t for t in normalized.split() if t not in _LEVEL_TOKENS).strip()


def _families(normalized: str) -> set[int]:
    base = _strip_levels(normalized)
    if not base:
        return set()
    found: set[int] = set()
    for index, family in enumerate(TITLE_FAMILIES):
        for member in family:
            if member == base or re.search(rf"(?<![a-z]){re.escape(member)}(?![a-z])", base):
                found.add(index)
                break
    return found


def score_title(job_title: str | None, desired_titles: list[str] | None) -> int:
    """Best fuzzy match of the job title against the user's desired titles (0-100)."""
    if not desired_titles:
        return NEUTRAL_SCORE
    job_norm = normalize_title(job_title)
    if not job_norm:
        return NEUTRAL_SCORE
    job_families = _families(job_norm)
    best = 0
    for wanted in desired_titles:
        wanted_norm = normalize_title(wanted)
        if not wanted_norm:
            continue
        score = int(round(fuzz.token_set_ratio(job_norm, wanted_norm)))
        if job_families and job_families & _families(wanted_norm):
            score = max(score, FAMILY_FLOOR_SCORE)
        best = max(best, score)
    return max(0, min(100, best))


# --------------------------------------------------------------------------- experience


def score_experience(
    job_min: float | None,
    job_max: float | None,
    candidate_years: float | None,
) -> tuple[int, str]:
    """Return ``(score, label)`` with label in STRONG / GOOD / UNDER / OVER / UNKNOWN."""
    if candidate_years is None or (job_min is None and job_max is None):
        return NEUTRAL_SCORE, UNKNOWN
    low = float(job_min) if job_min is not None else 0.0
    high = float(job_max) if job_max is not None else low + 3.0
    if high < low:
        low, high = high, low
    years = float(candidate_years)

    if low <= years <= high:
        return 100, STRONG
    if years < low:
        gap = low - years
        if gap <= 1:
            return 75, GOOD
        return max(10, int(round(40 - (gap - 1) * 10))), UNDER
    over = years - high
    if over <= 2:
        return 80, GOOD
    return 60, OVER


# --------------------------------------------------------------------------- location


def score_location(
    job_location: str | None,
    work_mode: WorkMode | str | None,
    preferred_locations: list[str] | None,
    work_modes: list[WorkMode] | list[str] | None,
) -> tuple[int, str]:
    """Return ``(score, label)`` with label in MATCH / REMOTE_OK / MISMATCH / UNKNOWN."""
    preferred_locations = list(preferred_locations or [])
    mode_values = {str(m.value if isinstance(m, WorkMode) else m).upper() for m in (work_modes or [])}
    if not preferred_locations and not mode_values:
        return NEUTRAL_SCORE, UNKNOWN

    job_mode = str(work_mode.value if isinstance(work_mode, WorkMode) else (work_mode or "")).upper()
    job_is_remote = job_mode == WorkMode.REMOTE.value or is_remote_location(job_location)
    job_norm = normalize_location(job_location)
    preferred_norm = {normalize_location(loc) for loc in preferred_locations}
    preferred_norm.discard(None)
    wants_remote = "remote" in preferred_norm or WorkMode.REMOTE.value in mode_values

    if job_is_remote:
        return (100, REMOTE_OK) if wants_remote else (70, REMOTE_OK)
    if job_norm and job_norm in preferred_norm:
        return 100, MATCH
    if not job_norm:
        return NEUTRAL_SCORE, UNKNOWN
    if not preferred_norm:
        # Only work modes were configured; a non-remote job is neither here nor there.
        return NEUTRAL_SCORE, UNKNOWN
    return 20, MISMATCH


# --------------------------------------------------------------------------- salary


def score_salary(
    job_min: int | None,
    job_max: int | None,
    min_salary: int | None,
    desired_salary: int | None,
) -> tuple[int | None, str]:
    """Return ``(score | None, label)`` with label in ABOVE / WITHIN / BELOW / UNKNOWN.

    ``None`` means "cannot be judged" — :func:`combine` then redistributes the weight.
    """
    if job_min is None and job_max is None:
        return None, UNKNOWN
    if min_salary is None and desired_salary is None:
        return None, UNKNOWN
    top = job_max if job_max is not None else job_min
    desired = desired_salary if desired_salary is not None else min_salary
    floor = min_salary if min_salary is not None else desired_salary
    if top is None or desired is None or floor is None:
        return None, UNKNOWN
    if top >= desired:
        return 100, ABOVE
    if top >= floor:
        return 75, WITHIN
    return 20, BELOW


# --------------------------------------------------------------------------- preferences


def score_preferences(
    *,
    work_mode: WorkMode | str | None,
    employment_type: Any | None,
    job_skills: list[str] | None,
    preferred_work_modes: list[Any] | None,
    preferred_employment_types: list[Any] | None,
    preferred_technologies: list[str] | None,
    excluded_keywords: list[str] | None = None,
    text: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Soft "does this fit how I want to work" score (the 0.05 component).

    Rewards a matching work mode / employment type and overlap with the technologies the
    user explicitly wants to work with; penalises excluded keywords appearing in the post.
    """
    parts: list[float] = []
    details: dict[str, Any] = {}

    mode_values = {str(getattr(m, "value", m)).upper() for m in (preferred_work_modes or [])}
    if mode_values:
        job_mode = str(getattr(work_mode, "value", work_mode) or "").upper()
        hit = bool(job_mode) and job_mode in mode_values
        details["work_mode"] = hit
        parts.append(100.0 if hit else 30.0)

    type_values = {str(getattr(t, "value", t)).upper() for t in (preferred_employment_types or [])}
    if type_values:
        job_type = str(getattr(employment_type, "value", employment_type) or "").upper()
        hit = bool(job_type) and job_type in type_values
        details["employment_type"] = hit
        parts.append(100.0 if hit else 30.0)

    wanted_tech = normalize_skills(list(preferred_technologies or []))
    if wanted_tech:
        matched, _ = skills_overlap(wanted_tech, list(job_skills or []))
        ratio = len(matched) / len(wanted_tech)
        details["technologies_matched"] = matched
        parts.append(min(100.0, 40.0 + 60.0 * ratio))

    score = sum(parts) / len(parts) if parts else float(NEUTRAL_SCORE)

    blocked = [
        kw
        for kw in (excluded_keywords or [])
        if kw and kw.strip() and kw.strip().lower() in (text or "").lower()
    ]
    if blocked:
        details["excluded_keywords"] = blocked
        score = min(score, 10.0)
    return int(round(score)), details


# --------------------------------------------------------------------------- combine


def combine(
    *,
    skills: int,
    title: int,
    experience: int,
    location: int,
    salary: int | None = None,
    preference: int | None = None,
    priority: CompanyPriority | str | None = CompanyPriority.P2,
) -> dict[str, Any]:
    """Weighted total of every component.

    Components passed as ``None`` are dropped and their weight is redistributed over the
    remaining ones. Company priority adds ``PRIORITY_BONUS`` on top; ``AVOID`` yields 0.

    Returns a dict with ``score``, ``base_score``, ``parts``, ``weights``,
    ``priority`` and ``priority_adjustment`` so the result can be explained verbatim.
    """
    resolved_priority = _coerce_priority(priority)
    parts: dict[str, int | None] = {
        "skills": _clamp(skills),
        "title": _clamp(title),
        "experience": _clamp(experience),
        "location": _clamp(location),
        "salary": _clamp(salary) if salary is not None else None,
        "preference": _clamp(preference) if preference is not None else None,
    }

    active = {k: v for k, v in parts.items() if v is not None}
    active_weight = sum(WEIGHTS[k] for k in active) or 1.0
    weights = {k: WEIGHTS[k] / active_weight for k in active}
    base = sum(weights[k] * active[k] for k in active)

    bonus = PRIORITY_BONUS.get(resolved_priority, 0)
    score = int(round(min(100.0, max(0.0, base + bonus))))
    if resolved_priority == CompanyPriority.AVOID:
        score, bonus = 0, 0

    return {
        "score": score,
        "base_score": round(base, 2),
        "parts": parts,
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "redistributed": sorted(k for k, v in parts.items() if v is None),
        "priority": resolved_priority.value,
        "priority_adjustment": bonus,
    }


def _clamp(value: int | float | None) -> int | None:
    if value is None:
        return None
    return int(max(0, min(100, round(float(value)))))


def _coerce_priority(priority: CompanyPriority | str | None) -> CompanyPriority:
    if isinstance(priority, CompanyPriority):
        return priority
    if not priority:
        return CompanyPriority.P2
    try:
        return CompanyPriority(str(priority).upper())
    except ValueError:
        logger.warning("Unknown company priority %r; defaulting to P2", priority)
        return CompanyPriority.P2
