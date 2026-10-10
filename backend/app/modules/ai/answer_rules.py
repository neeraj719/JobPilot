"""Rules shared by the deterministic answer engine (CONTRACTS.md §11 canonical keys).

Kept out of ``providers/mock.py`` so the field mapper, the review UI and the tests can
reuse exactly the same vocabulary:

* :func:`infer_question_key` — free-text question -> canonical key (or ``custom:<slug>``)
* :func:`is_sensitive_key`   — keys that must never be answered by AI inference
* :func:`match_option`       — map a known fact onto one of a SELECT/RADIO's options
* :func:`free_text_intent`   — which composed-answer template (if any) a question wants
"""
from __future__ import annotations

import re
from typing import Any

from app.modules.ai.skills import SKILL_ALIASES, extract_skills

# Canonical keys, as listed in CONTRACTS.md §11.
CANONICAL_KEYS: tuple[str, ...] = (
    "first_name",
    "last_name",
    "full_name",
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
    "website",
    "current_designation",
    "current_company",
    "years_of_experience",
    "current_salary",
    "expected_salary",
    "desired_salary",
    "min_salary",
    "notice_period_days",
    "notice_period_text",
    "willing_to_relocate",
    "requires_sponsorship",
    "work_authorization",
    "skills",
    "technologies",
    "summary",
    "headline",
    "education",
    "highest_degree",
    "university",
    "resume_file",
    "cover_letter",
)

# Facts that may only ever come from the stored profile — never inferred or composed.
SENSITIVE_KEYS: frozenset[str] = frozenset({"work_authorization", "requires_sponsorship"})

_SENSITIVE_CUSTOM_PATTERNS = (
    "legal",
    "gender",
    "sex",
    "ethnic",
    "race",
    "disability",
    "veteran",
    "demographic",
    "orientation",
    "religion",
    "caste",
    "marital",
    "criminal",
    "background_check",
)

# Keys whose value normally comes from the job preferences rather than the profile.
PREFERENCE_KEYS: frozenset[str] = frozenset(
    {"expected_salary", "desired_salary", "min_salary", "notice_period_days", "notice_period_text", "willing_to_relocate"}
)

# When the primary key is missing, try these in order before giving up.
KEY_FALLBACKS: dict[str, tuple[str, ...]] = {
    "expected_salary": ("desired_salary",),
    "desired_salary": ("expected_salary",),
    "notice_period_days": ("notice_period_text",),
    "notice_period_text": ("notice_period_days",),
    "full_name": ("first_name",),
    "portfolio_url": ("website",),
    "website": ("portfolio_url",),
    "city": ("address",),
}

# (regex, canonical key). Order matters: the first match wins.
_KEY_RULES: tuple[tuple[str, str], ...] = (
    (r"cover\s*letter", "cover_letter"),
    (r"\b(resume|cv|curriculum vitae)\b|upload your (resume|cv)", "resume_file"),
    (r"current\s*(ctc|salary|compensation|package)|present\s*(ctc|salary)|salary\s*\(current\)", "current_salary"),
    (
        r"expected\s*(ctc|salary|compensation|package)|salary\s*expectation|expected\s*pay|"
        r"desired\s*(salary|compensation)|compensation\s*expectation",
        "expected_salary",
    ),
    (r"(minimum|least|lowest)\s*(salary|ctc|compensation)", "min_salary"),
    (r"notice\s*period|when can you (start|join)|joining\s*time|availability to start|earliest start", "notice_period_days"),
    (r"relocat", "willing_to_relocate"),
    (r"sponsor", "requires_sponsorship"),
    (
        r"authori[sz]ed to work|work authori|work permit|legally (authori|entitled|allowed)|right to work|"
        r"require a visa|need a visa|work visa|eligible to work",
        "work_authorization",
    ),
    (r"linkedin", "linkedin_url"),
    (r"github", "github_url"),
    (r"portfolio|personal (web)?site|your website|blog url", "portfolio_url"),
    (r"total\s*(years|experience)|years of (professional |total |overall )?experience|overall experience|experience \(years\)", "years_of_experience"),
    (r"\bfirst name\b|\bgiven name\b", "first_name"),
    (r"\blast name\b|\bsurname\b|\bfamily name\b", "last_name"),
    (r"\b(full|complete) name\b|^name$|your name", "full_name"),
    (r"e-?mail", "email"),
    (r"phone|mobile|contact number|whats\s*app|cell", "phone"),
    (r"current\s*(company|employer|organi[sz]ation)|present\s*(company|employer)", "current_company"),
    (r"current\s*(designation|role|title|position)|job title|your (designation|title)", "current_designation"),
    (r"postal|pin\s*code|\bzip\b", "postal_code"),
    (r"\bstate\b|\bprovince\b", "state"),
    (r"\bcountry\b", "country"),
    (r"\bcity\b|current location|where are you (based|located)|\blocation\b", "city"),
    (r"address", "address"),
    (r"highest (degree|qualification)|highest level of education", "highest_degree"),
    (r"university|college|institution|alma mater", "university"),
    (r"\beducation\b|\bdegree\b|graduation", "education"),
    (r"\bskills?\b|technolog(y|ies) you", "skills"),
    (r"headline", "headline"),
    (r"(profile\s*)?summary|about (your)?self|tell us about you", "summary"),
)

_DEMOGRAPHIC_RE = re.compile(
    r"\b(gender|sex|race|ethnic\w*|disabilit\w*|veteran|sexual orientation|religion|caste|marital status)\b",
    re.IGNORECASE,
)

# Free-text intents -> canonical key.
_FREE_TEXT_RULES: tuple[tuple[str, str, str], ...] = (
    (r"cover\s*letter", "cover_letter", "cover_letter"),
    (
        r"why (do|would) you (want|like) to (work|join)|why (are you interested|this (company|role|position|job))|"
        r"why (us|our company|join us)|what (interests|excites) you about",
        "why_us",
        "custom:why_us",
    ),
    (
        r"describe (a|your|one)? ?(recent |challenging |favourite |favorite )?(project|system|feature)|"
        r"tell (us|me) about (a|your) (project|system)|proudest (project|work)|walk (us|me) through a project",
        "project",
        "custom:describe_project",
    ),
    (r"strength|what are you (good|best) at|superpower", "strengths", "custom:strengths"),
    (r"motivat|what drives you|career (goal|aspiration)|where do you see yourself", "motivation", "custom:motivation"),
)

_YES_WORDS = {"yes", "y", "true", "1", "yeah", "yep"}
_NO_WORDS = {"no", "n", "false", "0", "nope"}

# Minimal country inference for work-authorization questions (code -> spellings/cities).
COUNTRY_HINTS: dict[str, tuple[str, ...]] = {
    "IN": (
        "india",
        "bharat",
        "bangalore",
        "bengaluru",
        "hyderabad",
        "pune",
        "chennai",
        "mumbai",
        "delhi",
        "ncr",
        "gurgaon",
        "gurugram",
        "noida",
        "kolkata",
        "ahmedabad",
        "jaipur",
        "kochi",
        "indore",
        "chandigarh",
        "coimbatore",
        "trivandrum",
    ),
    "US": ("united states", "usa", "u.s.", "us ", "america", "new york", "san francisco", "seattle", "austin", "boston"),
    "GB": ("united kingdom", "uk", "england", "london", "manchester", "edinburgh"),
    "CA": ("canada", "toronto", "vancouver", "montreal"),
    "DE": ("germany", "berlin", "munich", "hamburg"),
    "SG": ("singapore",),
    "AE": ("united arab emirates", "uae", "dubai", "abu dhabi"),
    "AU": ("australia", "sydney", "melbourne"),
    "NL": ("netherlands", "amsterdam"),
    "IE": ("ireland", "dublin"),
}

COUNTRY_NAMES: dict[str, str] = {
    "IN": "India",
    "US": "the United States",
    "GB": "the United Kingdom",
    "CA": "Canada",
    "DE": "Germany",
    "SG": "Singapore",
    "AE": "the United Arab Emirates",
    "AU": "Australia",
    "NL": "the Netherlands",
    "IE": "Ireland",
}


def slugify(text: str, *, max_length: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return slug[:max_length] or "question"


def free_text_intent(question: str) -> tuple[str, str] | None:
    """Return ``(intent, canonical_key)`` when the question wants a composed answer."""
    text = (question or "").lower()
    for pattern, intent, key in _FREE_TEXT_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return intent, key
    return None


def _skill_years_key(question: str) -> str | None:
    """``"Years of experience with React?"`` -> ``skill_years:react``.

    Only technologies the shared taxonomy recognises qualify, so generic
    "total years of experience" questions fall through to ``years_of_experience``.

    Lowercase, like ``browser.mapper`` and ``CandidateContext.flat``: the two spellings
    used to produce two ``ApplicationAnswer`` rows for the same question, so a question
    the user had already answered reappeared on the review screen.
    """
    text = (question or "").lower()
    if not re.search(r"\b(years?|yrs?)\b", text):
        return None
    if re.search(r"\btotal\b|\boverall\b|professional experience|experience \(years\)", text):
        return None
    for canonical in extract_skills(text):
        if canonical in SKILL_ALIASES:
            return f"skill_years:{canonical.lower()}"
    return None


def infer_question_key(question: str, field_type: str | None = None) -> str:
    """Map a form question onto a canonical key from CONTRACTS.md §11."""
    text = re.sub(r"\s+", " ", (question or "").strip())
    lowered = text.lower()
    if not lowered:
        return "custom:question"

    if _DEMOGRAPHIC_RE.search(lowered):
        return f"custom:demographic_{slugify(text, max_length=40)}"

    skill_key = _skill_years_key(lowered)
    if skill_key:
        return skill_key

    intent = free_text_intent(lowered)
    if intent:
        return intent[1]

    for pattern, key in _KEY_RULES:
        if re.search(pattern, lowered, re.IGNORECASE):
            if key == "resume_file" and (field_type or "").upper() not in {"FILE", "", "UNKNOWN"}:
                continue
            return key

    if (field_type or "").upper() == "FILE":
        return "resume_file"
    return f"custom:{slugify(text)}"


def is_sensitive_key(key: str) -> bool:
    if key in SENSITIVE_KEYS:
        return True
    if key.startswith("custom:"):
        slug = key.split(":", 1)[1]
        return any(token in slug for token in _SENSITIVE_CUSTOM_PATTERNS)
    return False


def is_sensitive_question(question: str, key: str | None = None) -> bool:
    if key and is_sensitive_key(key):
        return True
    lowered = (question or "").lower()
    if _DEMOGRAPHIC_RE.search(lowered):
        return True
    return bool(re.search(r"sponsor|authori[sz]ed to work|work permit|right to work|visa", lowered))


def answer_source_for_key(key: str) -> str:
    """PROFILE / PREFERENCE / RESUME, as an ``AnswerSource`` value."""
    if key == "resume_file":
        return "RESUME"
    if key in PREFERENCE_KEYS:
        return "PREFERENCE"
    return "PROFILE"


def infer_country(*texts: str | None) -> str | None:
    """Best-effort ISO-3166 alpha-2 code from a location/question string."""
    for text in texts:
        if not text:
            continue
        lowered = f" {text.lower()} "
        for code, hints in COUNTRY_HINTS.items():
            for hint in hints:
                if hint in lowered:
                    return code
    return None


def country_display(code: str | None) -> str:
    if not code:
        return "this country"
    return COUNTRY_NAMES.get(code.upper(), code.upper())


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _YES_WORDS:
            return True
        if lowered in _NO_WORDS:
            return False
    return None


def lookup_authorization(work_authorization: Any, country_code: str | None) -> bool | None:
    """Read ``{"IN": true}`` style profile facts for a specific country."""
    if not isinstance(work_authorization, dict) or not country_code:
        return None
    code = country_code.upper()
    for raw_key, raw_value in work_authorization.items():
        key = str(raw_key).strip()
        if key.upper() == code or key.lower() == (COUNTRY_NAMES.get(code, "").lower().replace("the ", "")):
            return as_bool(raw_value)
        # allow full country names as keys ("India": true)
        hints = COUNTRY_HINTS.get(code, ())
        if key.lower() in hints:
            return as_bool(raw_value)
    return None


def _candidate_strings(value: Any) -> list[str]:
    """Plausible textual renderings of a fact, best first."""
    flag = as_bool(value) if not isinstance(value, (int, float)) or isinstance(value, bool) else None
    if flag is not None:
        return ["Yes", "yes", "true"] if flag else ["No", "no", "false"]
    if isinstance(value, (int, float)):
        number = int(value) if float(value).is_integer() else value
        out = [f"{number} days", f"{number}", f"{number} Days"]
        if number == 0:
            out.insert(0, "Immediate")
        return out
    text = str(value).strip()
    return [text] if text else []


def match_option(value: Any, options: list[str], *, threshold: int = 65) -> str | None:
    """Map a known fact onto the closest of ``options`` (``None`` when nothing fits)."""
    if value is None or not options:
        return None
    cleaned = [str(o) for o in options if str(o).strip()]
    if not cleaned:
        return None

    flag = as_bool(value)
    if flag is not None and not isinstance(value, (int, float)):
        for option in cleaned:
            head = option.strip().lower()
            if flag and (head.startswith("yes") or head in _YES_WORDS):
                return option
            if not flag and (head.startswith("no") or head in _NO_WORDS):
                return option

    candidates = _candidate_strings(value)
    lowered_options = {o.strip().lower(): o for o in cleaned}
    for candidate in candidates:
        exact = lowered_options.get(candidate.strip().lower())
        if exact:
            return exact

    # numeric facts: prefer the option carrying the same number
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        target = float(value)
        for option in cleaned:
            numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", option)]
            if numbers and abs(numbers[0] - target) < 0.001:
                return option
        if target == 0:
            for option in cleaned:
                if "immediate" in option.lower():
                    return option

    try:
        from rapidfuzz import fuzz, process
    except ImportError:  # pragma: no cover - rapidfuzz is a hard dependency
        return None

    best: tuple[str, float] | None = None
    for candidate in candidates:
        result = process.extractOne(candidate, cleaned, scorer=fuzz.token_set_ratio)
        if result and (best is None or result[1] > best[1]):
            best = (result[0], result[1])
    if best and best[1] >= threshold:
        return best[0]
    return None


__all__ = [
    "CANONICAL_KEYS",
    "KEY_FALLBACKS",
    "PREFERENCE_KEYS",
    "SENSITIVE_KEYS",
    "answer_source_for_key",
    "as_bool",
    "country_display",
    "free_text_intent",
    "infer_country",
    "infer_question_key",
    "is_sensitive_key",
    "is_sensitive_question",
    "lookup_authorization",
    "match_option",
    "slugify",
]
