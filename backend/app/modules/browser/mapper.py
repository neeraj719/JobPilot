"""Map detected form fields onto the canonical profile keys of CONTRACTS.md section 11.

The rules are an **ordered** table: the first rule that matches wins, so specific rules
(``current ctc``) must precede generic ones (``salary``). Each rule is tried against the
field subjects in quality order (name, id, label, placeholder, section), which also sets
the confidence.

Nothing here invents an answer - the mapper only says *which profile fact a question is
asking for*. Sensitive keys (work authorization, sponsorship, demographics) are flagged
so the answer engine refuses to let the AI guess them.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dc_field

from app.models.enums import FieldType
from app.modules.browser.schemas import DetectedField, MappedField, Mapping

logger = logging.getLogger(__name__)

# Words that look like a skill in "<x> experience" but are not one.
GENERIC_EXPERIENCE_WORDS = {
    "", "total", "overall", "work", "working", "professional", "relevant", "industry",
    "software", "development", "job", "your", "the", "years", "year", "yrs", "full",
    "it", "current", "previous", "past", "prior", "team", "general", "employment",
}

_SLUG_STOPWORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "can", "describe", "did", "do",
    "does", "for", "from", "have", "how", "if", "in", "is", "it", "of", "on", "or",
    "please", "provide", "tell", "that", "the", "their", "them", "this", "to", "us",
    "was", "were", "what", "when", "which", "will", "with", "would", "you", "your",
    "yours", "yourself", "much", "many", "give", "share", "about", "into", "us",
}

_SUBJECT_CONFIDENCE: dict[str, float] = {
    "name": 0.95,
    "id": 0.9,
    "label": 0.9,
    "placeholder": 0.7,
    "section": 0.5,
}


@dataclass(frozen=True)
class MapRule:
    canonical_key: str
    patterns: tuple[str, ...]
    is_sensitive: bool = False
    field_types: tuple[FieldType, ...] = ()
    #: rules whose canonical key is derived from a regex group (skill_years, demographics)
    dynamic: str | None = None
    compiled: tuple[re.Pattern[str], ...] = dc_field(default=(), compare=False)

    def build(self) -> "MapRule":
        object.__setattr__(self, "compiled", tuple(re.compile(p, re.I) for p in self.patterns))
        return self


def _rule(key: str, *patterns: str, sensitive: bool = False, types: tuple[FieldType, ...] = (), dynamic: str | None = None) -> MapRule:
    return MapRule(key, patterns, sensitive, types, dynamic).build()


# --------------------------------------------------------------------------- the table
# ORDER MATTERS - the first matching rule wins.
RULES: list[MapRule] = [
    # ---- per-skill experience: "Years of experience with React", name="react_experience"
    _rule(
        "skill_years",
        r"(?:years|yrs)[^a-z0-9]{0,12}(?:of\s+)?(?:experience|exp)\s*(?:with|in|using|on)\s+(?P<skill>[a-z0-9.+#][a-z0-9.+#\s/-]*)",
        r"how\s+(?:many|much)\s+(?:years|yrs)?[^a-z0-9]*(?:of\s+)?(?:experience|exp)?[^a-z0-9]*(?:do you have\s*)?(?:with|in|using)\s+(?P<skill>[a-z0-9.+#][a-z0-9.+#\s/-]*)",
        r"(?P<skill>[a-z0-9.+#][a-z0-9.+#\s]*?)\s+(?:experience|exp)\s*(?:\(|in\s+)?\s*(?:years|yrs)",
        r"^(?P<skill>[a-z0-9.+#]+)[_\s-]+(?:experience|exp|years|yrs)$",
        r"^(?:years|yrs)[_\s-]+(?:of[_\s-]+)?(?:experience[_\s-]+)?(?:with[_\s-]+|in[_\s-]+)?(?P<skill>[a-z0-9.+#]+)$",
        r"experience\s+(?:with|in|using)\s+(?P<skill>[a-z0-9.+#][a-z0-9.+#\s/-]*)",
        dynamic="skill_years",
    ),
    # ---- identity
    _rule("first_name", r"^first[\s_-]*name", r"\bfirst\s*name\b", r"\bgiven\s*name\b", r"^fname$"),
    _rule("last_name", r"^last[\s_-]*name", r"\blast\s*name\b", r"\bsurname\b", r"\bfamily\s*name\b", r"^lname$"),
    _rule("full_name", r"^(?:full[\s_-]*)?name\b", r"\bfull\s*name\b", r"\byour\s*name\b", r"\bcandidate\s*name\b", r"\blegal\s*name\b", r"\bapplicant\s*name\b"),
    _rule("email", r"e-?mail"),
    _rule("phone", r"\bmobile\b", r"\bphone\b", r"contact\s*(?:number|no\.?)\b", r"\bcell\b", r"whats\s*app", r"^tel$"),
    # ---- compensation (specific before generic)
    _rule("current_salary", r"current[\s_-]*(?:ctc|salary|compensation|package|pay)", r"present[\s_-]*(?:ctc|salary)", r"^current_ctc$", r"existing\s*ctc"),
    _rule("expected_salary", r"expected[\s_-]*(?:ctc|salary|compensation|package)", r"salary[\s_-]*expectation", r"^expected_ctc$", r"compensation\s*expectation"),
    _rule("desired_salary", r"desired\s*(?:ctc|salary|compensation)"),
    _rule("min_salary", r"minimum\s*(?:ctc|salary|compensation)", r"salary\s*minimum", r"\bmin(?:imum)?\s*expected\b"),
    # ---- notice period: a select/number asks for days, free text keeps the wording
    _rule("notice_period_days", r"notice[\s_-]*period", r"^notice_period$", types=(FieldType.SELECT, FieldType.NUMBER, FieldType.RADIO)),
    _rule("notice_period_text", r"notice[\s_-]*period", r"^notice_period$"),
    # ---- experience
    _rule(
        "years_of_experience",
        r"total\s*(?:years?\s*(?:of\s*)?)?(?:work\s*)?experience",
        r"years?\s*of\s*(?:professional\s*|work\s*|total\s*)?experience",
        r"overall\s*experience",
        r"experience\s*\(?\s*(?:in\s*)?years?\s*\)?",
        r"^total_experience$",
        r"^experience_years$",
        r"how\s+many\s+years",
    ),
    # ---- links
    _rule("linkedin_url", r"linked\s*-?\s*in"),
    _rule("github_url", r"git\s*-?\s*hub"),
    # a company/employer site is the only "website" that is not the candidate's portfolio
    # (section 12 maps plain "portfolio|website" to portfolio_url)
    _rule("website", r"(?:company|employer|organi[sz]ation)\s*(?:web)?\s*site", r"^company_website$"),
    _rule("portfolio_url", r"portfolio", r"personal\s*(?:web)?\s*site", r"\bwebsite\b", r"\bweb\s*site\b", r"\bblog\b", r"dribbble", r"behance"),
    # ---- documents
    _rule("resume_file", r"\bresum[eé]\b", r"\bcv\b", r"curriculum\s*vitae", r"upload\s*(?:your\s*)?(?:file|document)", r"attach\s*(?:your\s*)?(?:file|document)"),
    _rule("cover_letter", r"cover[\s_-]*letter", r"covering[\s_-]*letter", r"letter\s*of\s*motivation"),
    # ---- eligibility / legal (sensitive: never AI-guessed)
    _rule(
        "work_authorization",
        r"authori[sz]ed\s*to\s*work",
        r"work[\s_-]*authori[sz]ation",
        r"work\s*permit",
        r"legally\s*(?:authori[sz]ed|entitled|eligible)",
        r"right\s*to\s*work",
        r"eligible\s*to\s*work",
        r"visa\s*status",
        r"^work_authorization$",
        sensitive=True,
    ),
    _rule("requires_sponsorship", r"sponsorship", r"sponsor\s*(?:your|a)?\s*visa", r"require\s*(?:visa\s*)?sponsor", sensitive=True),
    _rule("willing_to_relocate", r"relocat"),
    # ---- demographics (sensitive -> REQUIRES_USER)
    _rule(
        "custom:demographic",
        r"\bgender\b", r"\brace\b", r"ethnic", r"\bveteran\b", r"disabilit", r"pronouns?",
        r"sexual\s*orientation", r"hispanic|latino", r"\bcaste\b",
        sensitive=True,
        dynamic="demographic",
    ),
    # ---- consent / declarations
    _rule(
        "custom:consent",
        r"\bconsent\b", r"\bi\s*agree\b", r"\bagree\s*to\b", r"terms\s*(?:and|&)?\s*conditions",
        r"privacy\s*policy", r"acknowledge", r"certify", r"\bdeclaration\b",
        types=(FieldType.CHECKBOX,),
    ),
    # ---- scheduling
    _rule(
        "custom:start_date",
        r"start[\s_-]*date", r"joining[\s_-]*date", r"date[\s_-]*of[\s_-]*joining", r"availability",
        r"available\s*to\s*(?:start|join)", r"when\s*can\s*you\s*(?:start|join)", r"notice.*join",
    ),
    # ---- motivation
    _rule(
        "custom:why_us",
        r"why\s*(?:do|would)\s*you\s*want\s*to\s*(?:work|join)",
        r"why\s*(?:this|our)\s*(?:company|role|team|position)",
        r"why[\s_-]*us\b",
        r"why\s*are\s*you\s*interested",
        r"\bmotivation\b",
        r"^why_company$",
        r"why\s*should\s*we\s*hire",
    ),
    # ---- current employment
    _rule("current_designation", r"current\s*(?:job\s*)?(?:title|designation|role|position)", r"present\s*designation", r"\bjob\s*title\b", r"\bdesignation\b"),
    _rule("current_company", r"current\s*(?:company|employer|organi[sz]ation)", r"present\s*(?:company|employer)", r"\bemployer\b"),
    # ---- location
    _rule("city", r"\bcity\b", r"current[\s_-]*location", r"\blocation\b", r"preferred\s*location", r"based\s*(?:in|out\s*of)", r"^city$"),
    _rule("state", r"\bstate\b", r"\bprovince\b", r"\bregion\b"),
    _rule("country", r"\bcountry\b"),
    _rule("postal_code", r"postal[\s_-]*code", r"\bzip\b", r"pin[\s_-]*code", r"\bpincode\b"),
    _rule("address", r"\baddress\b", r"\bstreet\b"),
    # ---- profile content
    _rule("skills", r"\bskills?\b", r"key\s*skills", r"technical\s*skills", r"core\s*competenc"),
    _rule("technologies", r"technolog", r"tech\s*stack", r"\btools\b", r"frameworks?"),
    _rule("summary", r"\bsummary\b", r"about\s*(?:you|yourself)", r"tell\s*us\s*about\s*yourself", r"\bbio\b"),
    _rule("headline", r"\bheadline\b", r"\btagline\b"),
    _rule("highest_degree", r"highest\s*(?:qualification|degree|education)", r"\bdegree\b", r"\bqualification\b"),
    _rule("university", r"\buniversity\b", r"\bcollege\b", r"\binstitution\b", r"\bschool\b", r"\balma\s*mater\b"),
    _rule("education", r"\beducation\b"),
]

# Matched demographic wording -> the slug used in the canonical key, so
# "Disability Status" and "disabled?" both become custom:demographic_disability.
_DEMOGRAPHIC_CANON: dict[str, str] = {
    "gender": "gender",
    "race": "race",
    "ethnic": "ethnicity",
    "ethnicity": "ethnicity",
    "hispanic": "ethnicity",
    "latino": "ethnicity",
    "veteran": "veteran",
    "disabilit": "disability",
    "pronoun": "pronouns",
    "pronouns": "pronouns",
    "sexual orientation": "orientation",
    "caste": "caste",
}

# Canonical keys the answer engine must never let the LLM invent (contract section 11).
SENSITIVE_KEYS = {"work_authorization", "requires_sponsorship"}
_SENSITIVE_CUSTOM_RE = re.compile(r"legal|gender|ethnic|race|disabilit|veteran|pronoun|caste|orientation", re.I)


def slugify(text: str, *, max_length: int = 40) -> str:
    """Stable, readable slug for custom question keys."""
    words = [w for w in re.split(r"[^a-z0-9+#]+", (text or "").lower()) if w]
    meaningful = [w for w in words if w not in _SLUG_STOPWORDS] or words
    slug = "_".join(meaningful)[:max_length].strip("_")
    return slug or "question"


def is_sensitive_key(key: str | None) -> bool:
    if not key:
        return False
    if key in SENSITIVE_KEYS:
        return True
    return key.startswith("custom:") and bool(_SENSITIVE_CUSTOM_RE.search(key))


class FieldMapper:
    """Rules-based mapping of a :class:`DetectedField` onto a canonical key."""

    def __init__(self, rules: list[MapRule] | None = None) -> None:
        self.rules = rules if rules is not None else RULES

    # -- public API --------------------------------------------------------

    def map(self, field: DetectedField) -> Mapping:
        subjects = self._subjects(field)
        if not subjects:
            return Mapping(canonical_key=None, confidence=0.0, reason="field has no label, name or placeholder to map")
        # Subject-major: the best evidence (name, then id, then label...) decides which
        # rule wins, so a stray section heading can never outrank the field's own label.
        for source, text in subjects:
            for rule in self.rules:
                if rule.field_types and field.field_type not in rule.field_types:
                    continue
                for pattern in rule.compiled:
                    match = pattern.search(text)
                    if not match:
                        continue
                    resolved = self._resolve(rule, match, field)
                    if resolved is None:
                        continue  # dynamic rule rejected this match (e.g. "total_experience")
                    key, sensitive = resolved
                    confidence = _SUBJECT_CONFIDENCE.get(source, 0.6)
                    if rule.dynamic:
                        confidence = min(confidence, 0.85)
                    return Mapping(
                        canonical_key=key,
                        confidence=round(confidence, 2),
                        reason=f'matched "{pattern.pattern}" on {source}="{text}"',
                        is_sensitive=sensitive or is_sensitive_key(key),
                    )
        key = f"custom:{slugify(field.label or field.name or field.placeholder or '')}"
        return Mapping(
            canonical_key=key,
            confidence=0.3,
            reason="no rule matched - treated as a custom question",
            is_sensitive=is_sensitive_key(key),
        )

    def map_form(self, detected) -> list[MappedField]:  # noqa: ANN001 - DetectedForm
        return [MappedField(field=f, mapping=self.map(f)) for f in detected.fields]

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _subjects(field: DetectedField) -> list[tuple[str, str]]:
        raw = [
            ("name", field.name),
            ("id", field.id),
            ("label", field.label),
            ("placeholder", field.placeholder),
            ("section", field.section),
        ]
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for source, value in raw:
            text = re.sub(r"\s+", " ", (value or "").strip()).strip()
            if not text or text.lower() in seen:
                continue
            seen.add(text.lower())
            out.append((source, text))
        return out

    @staticmethod
    def _resolve(rule: MapRule, match: re.Match[str], field: DetectedField) -> tuple[str, bool] | None:
        if rule.dynamic == "skill_years":
            from app.modules.ai.skills import normalize_skill

            raw_skill = re.sub(r"[\s_-]+", " ", (match.groupdict().get("skill") or "")).strip(" ?.:-")
            if raw_skill.lower() in GENERIC_EXPERIENCE_WORDS or len(raw_skill) < 2:
                return None
            skill = normalize_skill(raw_skill)
            if not skill or skill.lower() in GENERIC_EXPERIENCE_WORDS:
                return None
            return f"skill_years:{skill.lower()}", False
        if rule.dynamic == "demographic":
            token = re.sub(r"\s+", " ", match.group(0).strip().lower())
            canon = _DEMOGRAPHIC_CANON.get(token) or next(
                (v for k, v in _DEMOGRAPHIC_CANON.items() if token.startswith(k) or k.startswith(token)),
                slugify(token, max_length=24),
            )
            return f"custom:demographic_{canon}", True
        return rule.canonical_key, rule.is_sensitive


#: Shared instance - the rules are stateless.
default_mapper = FieldMapper()


def map_field(field: DetectedField) -> Mapping:
    return default_mapper.map(field)


def map_form(detected) -> list[MappedField]:  # noqa: ANN001 - DetectedForm
    """Map every field of a detected form; keeps field + mapping together."""
    return default_mapper.map_form(detected)
