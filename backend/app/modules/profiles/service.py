"""Profile, job-preference and candidate-context services (contract §3, §11).

The ``CandidateContext`` built here is the single source of truth every downstream
consumer (matching, answer engine, field mapper, browser autofill) reads facts from.
A key is present in ``flat`` **only** when a real value exists, so a missing key always
means "ask the user" rather than "let the AI invent something".
"""
from __future__ import annotations

import difflib
import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import JSON as SAJSON, select
from sqlalchemy.orm import Session

from app.models.enums import FieldType, JobSourceType
from app.models.profile import APPLIES_TO_ALL, JobPreference, StandingAnswer, UserProfile
from app.models.user import User
from app.modules.ai.skills import normalize_skill, normalize_skills
from app.modules.profiles.schemas import (
    CandidateContext,
    JobPreferenceRead,
    JobPreferenceUpdate,
    ProfileRead,
    ProfileUpdate,
)

logger = logging.getLogger(__name__)

# Weighted fields used for the profile completeness meter. ``source`` says where the
# value lives: the profile row or the job preference row.
COMPLETENESS_FIELDS: tuple[tuple[str, str, float], ...] = (
    ("full_name", "profile", 1.5),
    ("email", "profile", 1.5),
    ("phone", "profile", 1.5),
    ("city", "profile", 1.0),
    ("country", "profile", 1.0),
    ("linkedin_url", "profile", 1.0),
    ("current_designation", "profile", 1.0),
    ("years_of_experience", "profile", 1.5),
    ("skills", "profile", 2.0),
    ("education", "profile", 1.0),
    ("summary", "profile", 1.0),
    ("work_authorization", "profile", 1.5),
    ("requires_sponsorship", "profile", 1.0),
    ("notice_period_days", "preference", 1.0),
    ("desired_salary", "preference", 1.0),
)

_MONTHS: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_PRESENT_WORDS = {"present", "current", "currently", "now", "till date", "to date", "ongoing", "date"}


# --------------------------------------------------------------------------- small helpers


def _has_value(value: Any) -> bool:
    """A value 'exists' when it is not None and not an empty string/list/dict."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def _parse_date_fragment(value: Any, *, allow_present: bool = False) -> date | None:
    """Parse the loose date strings resumes use ("2021-03", "Mar 2021", "Present")."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = re.sub(r"\s+", " ", str(value).strip().lower())
    if not text:
        return None
    if text in _PRESENT_WORDS:
        return date.today() if allow_present else None
    m = re.match(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?$", text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
    m = re.match(r"^(\d{1,2})[/-](\d{4})$", text)
    if m:
        return _safe_date(int(m.group(2)), int(m.group(1)), 1)
    m = re.match(r"^(\d{4})/(\d{1,2})$", text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), 1)
    m = re.match(r"^([a-z]{3,9})[ \-/,]+(\d{4})$", text)
    if m and m.group(1) in _MONTHS:
        return _safe_date(int(m.group(2)), _MONTHS[m.group(1)], 1)
    m = re.match(r"^(\d{4})$", text)
    if m:
        return _safe_date(int(m.group(1)), 1, 1)
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, min(max(month, 1), 12), min(max(day, 1), 28))
    except ValueError:  # pragma: no cover - defensive
        return None


def split_full_name(full_name: str | None) -> tuple[str | None, str | None]:
    parts = [p for p in re.split(r"\s+", (full_name or "").strip()) if p]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


# --------------------------------------------------------------------------- rows


def get_or_create_profile(db: Session, user_id: uuid.UUID) -> UserProfile:
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == user_id)).first()
    if profile is None:
        user = db.get(User, user_id)
        profile = UserProfile(
            user_id=user_id,
            full_name=user.full_name if user else None,
            email=user.email if user else None,
        )
        db.add(profile)
        db.flush()
        logger.info("Created empty profile for user %s", user_id)
    return profile


def get_or_create_job_preference(db: Session, user_id: uuid.UUID) -> JobPreference:
    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == user_id)).first()
    if preference is None:
        preference = JobPreference(user_id=user_id, currency="INR", min_match_score=75, only_posted_within_hours=24)
        db.add(preference)
        db.flush()
        logger.info("Created default job preference for user %s", user_id)
    return preference


# --------------------------------------------------------------------------- completeness


def compute_completeness(profile: UserProfile, preference: JobPreference | None = None) -> tuple[int, list[str]]:
    """Return ``(percentage, missing_fields)`` over the weighted field list."""
    earned = 0.0
    total = 0.0
    missing: list[str] = []
    for field, source, weight in COMPLETENESS_FIELDS:
        total += weight
        holder: Any = profile if source == "profile" else preference
        value = getattr(holder, field, None) if holder is not None else None
        if _has_value(value):
            earned += weight
        else:
            missing.append(field)
    percentage = int(round(100 * earned / total)) if total else 0
    return percentage, missing


def to_profile_read(profile: UserProfile, preference: JobPreference | None = None) -> ProfileRead:
    completeness, missing = compute_completeness(profile, preference)
    read = ProfileRead.model_validate(profile)
    read.completeness = completeness
    read.missing_fields = missing
    return read


def to_preference_read(preference: JobPreference) -> JobPreferenceRead:
    return JobPreferenceRead.model_validate(preference)


# --------------------------------------------------------------------------- updates


def _json_column_defaults(model: Any) -> dict[str, type]:
    """``{column: list | dict}`` for every NOT NULL JSON column of ``model``.

    ``ProfileUpdate.skills`` is ``list[Any] | None``, so ``{"skills": null}`` is a valid
    body - but SQLAlchemy stores Python ``None`` as the JSON literal ``null`` (the NOT
    NULL constraint never fires) and ``ProfileRead.model_validate`` then raises, turning
    the whole request into a 500 *and* rolling back the other fields the user edited.
    Worse, a ``null`` that ever reaches the column makes ``GET /profile`` and
    ``build_candidate_context`` fail for ever. So ``null`` means "empty", not "no value".
    """
    out: dict[str, type] = {}
    for column in model.__table__.columns:
        if not isinstance(column.type, SAJSON) or column.nullable:
            continue
        default = column.default
        empty = default.arg(None) if default is not None and default.is_callable else []
        out[column.key] = type(empty)
    return out


_PROFILE_JSON_DEFAULTS = _json_column_defaults(UserProfile)
_PREFERENCE_JSON_DEFAULTS = _json_column_defaults(JobPreference)


def update_profile(db: Session, user_id: uuid.UUID, payload: ProfileUpdate) -> UserProfile:
    profile = get_or_create_profile(db, user_id)
    data = payload.model_dump(exclude_unset=True, mode="json")
    for field, value in data.items():
        if value is None and field in _PROFILE_JSON_DEFAULTS:
            value = _PROFILE_JSON_DEFAULTS[field]()
        if hasattr(profile, field):
            setattr(profile, field, value)

    # full_name <-> first/last derivation (contract §3)
    if "full_name" in data and _has_value(profile.full_name):
        first, last = split_full_name(profile.full_name)
        if not _has_value(profile.first_name):
            profile.first_name = first
        if not _has_value(profile.last_name):
            profile.last_name = last
    if ("first_name" in data or "last_name" in data) and not _has_value(profile.full_name):
        joined = " ".join(p for p in [_clean_str(profile.first_name), _clean_str(profile.last_name)] if p)
        profile.full_name = joined or None

    db.flush()
    logger.info("Profile updated for user %s (%d fields)", user_id, len(data))
    return profile


def update_job_preference(db: Session, user_id: uuid.UUID, payload: JobPreferenceUpdate) -> JobPreference:
    preference = get_or_create_job_preference(db, user_id)
    data = payload.model_dump(exclude_unset=True, mode="json")
    for field, value in data.items():
        if field == "currency" and value is None:
            continue
        if field in {"min_match_score"} and value is None:
            continue
        if value is None and field in _PREFERENCE_JSON_DEFAULTS:
            value = _PREFERENCE_JSON_DEFAULTS[field]()
        if hasattr(preference, field):
            setattr(preference, field, value)
    db.flush()
    logger.info("Job preferences updated for user %s (%d fields)", user_id, len(data))
    return preference


# --------------------------------------------------------------------------- resume access


def _load_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID | None) -> Any | None:
    """Fetch the resume through the resumes module, tolerating it not existing yet."""
    try:
        from app.modules.resumes import service as resumes_service  # noqa: PLC0415 (lazy on purpose)
    except Exception as exc:  # pragma: no cover - module not implemented yet
        logger.debug("resumes module unavailable (%s); candidate context will have no resume", exc)
        return None
    try:
        if resume_id is not None:
            getter = getattr(resumes_service, "get_resume", None)
            return getter(db, user_id, resume_id) if getter else None
        getter = getattr(resumes_service, "get_default_resume", None)
        return getter(db, user_id) if getter else None
    except Exception as exc:
        logger.warning("Could not load resume for user %s: %s", user_id, exc)
        return None


def _resume_view(resume: Any) -> Any:
    """Serialise a Resume ORM row to ``ResumeRead`` when available, else a plain dict."""
    if resume is None:
        return None
    try:
        from app.modules.resumes.schemas import ResumeRead  # noqa: PLC0415

        return ResumeRead.model_validate(resume)
    except Exception:
        return {
            "id": str(getattr(resume, "id", "")) or None,
            "name": getattr(resume, "name", None),
            "target_role": getattr(resume, "target_role", None),
            "is_default": getattr(resume, "is_default", None),
            "parsed_data": getattr(resume, "parsed_data", {}) or {},
        }


def _parsed_data(resume: Any) -> dict[str, Any]:
    if resume is None:
        return {}
    data = resume.get("parsed_data") if isinstance(resume, dict) else getattr(resume, "parsed_data", None)
    return data if isinstance(data, dict) else {}


def _resume_file_path(resume: Any) -> str | None:
    """Absolute path of the resume file, but only when it really exists on disk."""
    if resume is None:
        return None
    raw = resume.get("file_path") if isinstance(resume, dict) else getattr(resume, "file_path", None)
    if not raw:
        return None
    try:
        path = Path(str(raw)).expanduser().resolve()
    except (OSError, ValueError):  # pragma: no cover - defensive
        return None
    return str(path) if path.is_file() else None


# --------------------------------------------------------------------------- skill years


def skill_years_from_profile(skill_experience: dict[str, Any] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for raw_key, raw_value in (skill_experience or {}).items():
        canonical = normalize_skill(str(raw_key))
        years = _coerce_float(raw_value)
        if canonical and years is not None and years > 0:
            out[canonical.lower()] = round(years, 1)
    return out


def skill_years_from_resume(parsed_data: dict[str, Any] | None) -> dict[str, float]:
    """Years per technology derived from resume experience entries.

    A technology only counts when the entry actually lists it **and** the entry has
    parsable start/end dates - never guessed.
    """
    totals: dict[str, float] = {}
    for entry in (parsed_data or {}).get("experience") or []:
        if not isinstance(entry, dict):
            continue
        technologies = entry.get("technologies") or []
        if not isinstance(technologies, (list, tuple)) or not technologies:
            continue
        start = _parse_date_fragment(entry.get("start"))
        end = _parse_date_fragment(entry.get("end"), allow_present=True)
        if start is None or end is None:
            continue
        years = (end - start).days / 365.25
        if years <= 0:
            continue
        for tech in technologies:
            canonical = normalize_skill(str(tech))
            if not canonical:
                continue
            totals[canonical.lower()] = totals.get(canonical.lower(), 0.0) + years
    return {key: round(value, 1) for key, value in totals.items()}


def _most_recent_education(entries: list[Any]) -> dict[str, Any] | None:
    """Pick the education entry that ended (or started) most recently."""
    dated: list[tuple[date, dict[str, Any]]] = []
    undated: list[dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        when = _parse_date_fragment(entry.get("end"), allow_present=True) or _parse_date_fragment(entry.get("start"))
        if when is not None:
            dated.append((when, entry))
        else:
            undated.append(entry)
    if dated:
        return max(dated, key=lambda item: item[0])[1]
    return undated[-1] if undated else None


# --------------------------------------------------------------------------- candidate context


def build_candidate_context(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID | None = None) -> CandidateContext:
    """Build the flattened candidate view used by every downstream consumer."""
    profile = get_or_create_profile(db, user_id)
    preference = get_or_create_job_preference(db, user_id)
    user = db.get(User, user_id)
    resume = _load_resume(db, user_id, resume_id)
    parsed = _parsed_data(resume)
    resume_path = _resume_file_path(resume)

    flat: dict[str, Any] = {}

    def put(key: str, value: Any) -> None:
        if _has_value(value):
            flat[key] = value

    # -- identity ------------------------------------------------------------------
    full_name = _clean_str(profile.full_name) or _clean_str(user.full_name if user else None)
    first_name = _clean_str(profile.first_name)
    last_name = _clean_str(profile.last_name)
    if not first_name or not last_name:
        derived_first, derived_last = split_full_name(full_name)
        first_name = first_name or derived_first
        last_name = last_name or derived_last
    put("full_name", full_name)
    put("first_name", first_name)
    put("last_name", last_name)
    put("email", _clean_str(profile.email) or _clean_str(user.email if user else None))
    put("phone", _clean_str(profile.phone))
    put("address", _clean_str(profile.address))
    put("city", _clean_str(profile.city))
    put("state", _clean_str(profile.state))
    put("country", _clean_str(profile.country))
    put("postal_code", _clean_str(profile.postal_code))
    put("linkedin_url", _clean_str(profile.linkedin_url))
    put("github_url", _clean_str(profile.github_url))
    put("portfolio_url", _clean_str(profile.portfolio_url))
    put("website", _clean_str(profile.portfolio_url))

    # -- professional --------------------------------------------------------------
    put("headline", _clean_str(profile.headline))
    put("summary", _clean_str(profile.summary) or _clean_str(parsed.get("summary")))
    put("current_designation", _clean_str(profile.current_designation))
    put("current_company", _clean_str(profile.current_company))
    years = profile.years_of_experience
    if years is None:
        years = _coerce_float(parsed.get("total_experience_years"))
    put("years_of_experience", years)
    put("current_salary", profile.current_salary)

    # -- preferences / compensation ------------------------------------------------
    put("currency", _clean_str(preference.currency))
    put("min_salary", preference.min_salary)
    put("desired_salary", preference.desired_salary)
    put("expected_salary", preference.desired_salary if preference.desired_salary is not None else preference.min_salary)
    if preference.notice_period_days is not None:
        flat["notice_period_days"] = preference.notice_period_days
        flat["notice_period_text"] = "Immediate" if preference.notice_period_days == 0 else f"{preference.notice_period_days} days"
    put("preferred_locations", list(preference.preferred_locations or []))
    put("work_modes", list(preference.work_modes or []))
    put("desired_titles", list(preference.desired_titles or []))
    put("employment_types", list(preference.employment_types or []))
    put("preferred_technologies", normalize_skills([str(t) for t in (preference.preferred_technologies or [])]))

    # -- eligibility facts (never inferred) ----------------------------------------
    put("work_authorization", dict(profile.work_authorization or {}))
    if profile.requires_sponsorship is not None:
        flat["requires_sponsorship"] = profile.requires_sponsorship
    if profile.willing_to_relocate is not None:
        flat["willing_to_relocate"] = profile.willing_to_relocate

    # -- skills --------------------------------------------------------------------
    raw_skills: list[str] = [str(s) for s in (profile.skills or [])]
    raw_skills += [str(t) for t in (profile.technologies or [])]
    raw_skills += [str(s) for s in (parsed.get("skills") or []) if isinstance(s, (str, int, float))]
    put("skills", normalize_skills(raw_skills))
    put("technologies", normalize_skills([str(t) for t in (profile.technologies or [])]))

    # -- education -----------------------------------------------------------------
    education = list(profile.education or []) or list(parsed.get("education") or [])
    put("education", education)
    recent = _most_recent_education(education)
    if recent:
        put("highest_degree", _clean_str(recent.get("degree")))
        put("university", _clean_str(recent.get("institution") or recent.get("university")))

    # -- resume --------------------------------------------------------------------
    put("resume_file", resume_path)

    # -- skill_years:<skill> -------------------------------------------------------
    years_by_skill = skill_years_from_resume(parsed)
    years_by_skill.update(skill_years_from_profile(profile.skill_experience))
    for skill, value in years_by_skill.items():
        flat[f"skill_years:{skill}"] = value

    # -- free-form canonical answers the user curated ------------------------------
    for key, value in (profile.canonical_answers or {}).items():
        canonical_key = str(key).strip()
        if canonical_key and canonical_key not in flat and _has_value(value):
            flat[canonical_key] = value

    context = CandidateContext(
        profile=to_profile_read(profile, preference),
        preferences=to_preference_read(preference),
        resume=_resume_view(resume),
        resume_path=resume_path,
        flat=flat,
    )
    logger.debug("Built candidate context for user %s with %d flat keys", user_id, len(flat))
    return context


def candidate_context_to_prompt_dict(ctx: CandidateContext, *, max_chars: int = 2000) -> dict[str, Any]:
    """Compact, JSON-able candidate summary for LLM prompts (~2k chars max)."""
    flat = ctx.flat
    location = ", ".join(p for p in [flat.get("city"), flat.get("state"), flat.get("country")] if p)
    skill_years = {k.split(":", 1)[1]: v for k, v in flat.items() if k.startswith("skill_years:")}

    def build(summary_chars: int, skills_n: int, skill_years_n: int, titles_n: int, locations_n: int) -> dict[str, Any]:
        summary = flat.get("summary")
        data: dict[str, Any] = {
            "full_name": flat.get("full_name"),
            "headline": flat.get("headline"),
            "current_designation": flat.get("current_designation"),
            "current_company": flat.get("current_company"),
            "years_of_experience": flat.get("years_of_experience"),
            "location": location or None,
            "skills": list(flat.get("skills") or [])[:skills_n] or None,
            "skill_years": dict(list(skill_years.items())[:skill_years_n]) or None,
            "highest_degree": flat.get("highest_degree"),
            "university": flat.get("university"),
            "currency": flat.get("currency"),
            "current_salary": flat.get("current_salary"),
            "expected_salary": flat.get("expected_salary"),
            "notice_period": flat.get("notice_period_text"),
            "work_authorization": flat.get("work_authorization"),
            "requires_sponsorship": flat.get("requires_sponsorship"),
            "willing_to_relocate": flat.get("willing_to_relocate"),
            "desired_titles": list(flat.get("desired_titles") or [])[:titles_n] or None,
            "preferred_locations": list(flat.get("preferred_locations") or [])[:locations_n] or None,
            "work_modes": list(flat.get("work_modes") or []) or None,
            "summary": (summary[:summary_chars].rstrip() if isinstance(summary, str) else None),
            "has_resume": ctx.resume is not None,
        }
        return {k: v for k, v in data.items() if v is not None}

    shrink_steps = [(400, 20, 8, 5, 5), (240, 14, 5, 3, 3), (160, 10, 3, 2, 2), (0, 6, 0, 0, 0)]
    payload = build(*shrink_steps[0])
    for step in shrink_steps[1:]:
        if len(json.dumps(payload, default=str)) <= max_chars:
            break
        payload = build(*step)
    return payload


# --------------------------------------------------------------------------- standing answers
#
# Answers the user gave once and the answer engine reuses (``applications/answers.py``
# reads them right after anything typed on the application itself). The rules that
# decide whether a stored answer may stand in for a live question live here, next to
# the storage, so the API, the capture from the Approval Center and the engine agree.

#: Stands for the employer's name inside a stored ``question_text``.
COMPANY_PLACEHOLDER = "{company}"

#: Consent and legal declarations reuse a standing answer only when the live wording is
#: at least this similar (normalised ``difflib`` ratio) to the wording the user answered.
WORDING_MATCH_THRESHOLD = 0.9

_DEMOGRAPHIC_KEY_RE = re.compile(
    r"demographic|gender|(?:^|_)sex(?:_|$)|ethnic|race|disabilit|veteran|orientation|religion|caste|marital|pronoun",
    re.IGNORECASE,
)
_DEMOGRAPHIC_TEXT_RE = re.compile(
    r"\b(gender|sex|race|ethnic\w*|disabilit\w*|veteran|sexual orientation|religion|caste|marital status|pronouns?)\b",
    re.IGNORECASE,
)
#: Keys that are a declaration by the candidate: the exact wording matters.
_DECLARATION_KEYS = frozenset({"custom:consent", "work_authorization", "requires_sponsorship"})
_DECLARATION_SLUG_RE = re.compile(r"consent|legal|declar|certif|agree|terms|privacy|acknowledg|attest|criminal", re.IGNORECASE)


def is_demographic_question(question_key: str | None, question_text: str | None = None) -> bool:
    """Gender, ethnicity, disability, veteran status...: never answered from a standing answer."""
    key = (question_key or "").strip()
    if key.startswith("custom:") and _DEMOGRAPHIC_KEY_RE.search(key.split(":", 1)[1]):
        return True
    return bool(question_text and _DEMOGRAPHIC_TEXT_RE.search(question_text))


def requires_wording_match(question_key: str | None) -> bool:
    """Consent and legal declarations: reused only when the wording matches what was answered."""
    key = (question_key or "").strip()
    if key in _DECLARATION_KEYS:
        return True
    return key.startswith("custom:") and bool(_DECLARATION_SLUG_RE.search(key.split(":", 1)[1]))


def template_question_text(text: str | None, company_name: str | None) -> str:
    """Replace the employer's name with ``{company}`` so the wording matches at the next one."""
    value = re.sub(r"\s+", " ", (text or "").strip())
    value = re.sub(r"\s*\*\s*$", "", value)  # the "required" asterisk is not wording
    name = (company_name or "").strip()
    if len(name) >= 2:
        value = re.sub(re.escape(name), COMPANY_PLACEHOLDER, value, flags=re.IGNORECASE)
    return value


def normalize_question_text(text: str | None) -> str:
    """Lower case, punctuation and the required-asterisk dropped, whitespace collapsed."""
    value = (text or "").lower().replace(COMPANY_PLACEHOLDER, " companyplaceholder ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def wording_similarity(stored_text: str | None, live_text: str | None, company_name: str | None = None) -> float:
    """``0..1`` similarity of a stored wording and the live one, employer name factored out."""
    left = normalize_question_text(template_question_text(stored_text, company_name))
    right = normalize_question_text(template_question_text(live_text, company_name))
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def standing_answer_applies(row: StandingAnswer, source: JobSourceType | str | None, *, now: datetime | None = None) -> bool:
    """Active, not expired, and meant for this job source."""
    if not row.is_active or row.deleted_at is not None:
        return False
    expires = _aware(row.expires_at)
    if expires is not None and expires <= (now or datetime.now(timezone.utc)):
        return False
    scope = row.applies_to
    if scope in (None, APPLIES_TO_ALL) or (isinstance(scope, list) and APPLIES_TO_ALL in scope):
        return True
    if source is None:
        return False  # restricted to named sources, and this job has none
    wanted = str(getattr(source, "value", source)).upper()
    return isinstance(scope, list) and wanted in {str(s).upper() for s in scope}


def find_standing_answer(
    rows: list[StandingAnswer],
    *,
    question_key: str,
    question_text: str | None,
    source: JobSourceType | str | None,
    company_name: str | None = None,
    now: datetime | None = None,
) -> StandingAnswer | None:
    """The standing answer that may answer this live question, or ``None``.

    * demographic questions never use one;
    * the key must match and the row must apply to this source and not be expired;
    * consent and legal declarations additionally need the wording to match
      (:data:`WORDING_MATCH_THRESHOLD`) - a consent box with different wording still pauses.
    """
    if is_demographic_question(question_key, question_text):
        return None
    for row in rows:
        if row.question_key != question_key or not standing_answer_applies(row, source, now=now):
            continue
        if requires_wording_match(question_key):
            score = wording_similarity(row.question_text, question_text, company_name)
            if score < WORDING_MATCH_THRESHOLD:
                logger.info(
                    "Standing answer for %s not reused: wording similarity %.2f < %.2f",
                    question_key, score, WORDING_MATCH_THRESHOLD,
                )
                continue
        return row
    return None


def list_standing_answers(db: Session, user_id: uuid.UUID) -> list[StandingAnswer]:
    """Every standing answer the user has (active or switched off), by question."""
    return list(
        db.scalars(
            select(StandingAnswer).where(StandingAnswer.user_id == user_id).order_by(StandingAnswer.question_key)
        ).all()
    )


def active_standing_answers(db: Session, user_id: uuid.UUID, *, now: datetime | None = None) -> list[StandingAnswer]:
    """The ones the answer engine may use right now (the source scope is checked per question)."""
    moment = now or datetime.now(timezone.utc)
    rows = db.scalars(
        select(StandingAnswer).where(StandingAnswer.user_id == user_id, StandingAnswer.is_active.is_(True))
    ).all()
    return [row for row in rows if _aware(row.expires_at) is None or _aware(row.expires_at) > moment]


def upsert_standing_answer(
    db: Session,
    user_id: uuid.UUID,
    *,
    question_key: str,
    question_text: str,
    answer: str,
    field_type: FieldType | str = FieldType.TEXT,
    applies_to: Any = APPLIES_TO_ALL,
    expires_at: datetime | None = None,
    is_active: bool = True,
    company_name: str | None = None,
) -> StandingAnswer:
    """Create the standing answer for ``question_key``, or replace the existing one.

    ``company_name`` (the employer of the application it was captured from) is replaced by
    ``{company}`` in the stored wording. Demographic questions and file uploads are refused.
    """
    from app.core.exceptions import ValidationFailed  # noqa: PLC0415

    key = (question_key or "").strip()
    text = template_question_text(question_text, company_name) or key
    value = (answer or "").strip()
    if not key or not value:
        raise ValidationFailed("A standing answer needs a question and an answer", code="standing_answer_incomplete")
    try:
        resolved_type = FieldType(str(getattr(field_type, "value", field_type) or FieldType.TEXT.value).upper())
    except ValueError:
        resolved_type = FieldType.TEXT
    if is_demographic_question(key, text):
        raise ValidationFailed(
            "Demographic questions are always answered by you, on each application",
            code="standing_answer_not_allowed",
            details={"question_key": key},
        )
    if resolved_type is FieldType.FILE:
        raise ValidationFailed(
            "File attachments come from your resume; they cannot be a standing answer",
            code="standing_answer_not_allowed",
            details={"question_key": key},
        )
    scope: Any = APPLIES_TO_ALL
    if isinstance(applies_to, (list, tuple)):
        sources = [str(getattr(s, "value", s)).strip().upper() for s in applies_to]
        sources = [s for s in sources if s]
        scope = APPLIES_TO_ALL if not sources or APPLIES_TO_ALL in sources else list(dict.fromkeys(sources))

    row = db.scalars(
        select(StandingAnswer).where(StandingAnswer.user_id == user_id, StandingAnswer.question_key == key)
    ).first()
    if row is None:
        row = StandingAnswer(user_id=user_id, question_key=key)
        db.add(row)
    row.question_text = text
    row.field_type = resolved_type
    row.answer = value
    row.applies_to = scope
    row.expires_at = expires_at
    row.is_active = bool(is_active)
    db.flush()
    logger.info("Standing answer saved for user %s: %s", user_id, key)
    return row


def delete_standing_answer(db: Session, user_id: uuid.UUID, standing_answer_id: uuid.UUID) -> None:
    """Tombstone one of the user's standing answers (404 for anyone else's)."""
    from app.core.exceptions import NotFoundError  # noqa: PLC0415
    from app.core.soft_delete import soft_delete  # noqa: PLC0415

    row = db.scalars(
        select(StandingAnswer).where(StandingAnswer.id == standing_answer_id, StandingAnswer.user_id == user_id)
    ).first()
    if row is None:
        raise NotFoundError("Standing answer not found")
    soft_delete(row)
    db.flush()
