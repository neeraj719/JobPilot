"""Job-description intake: normalise the text and extract what the job asks for.

Deterministic first, model second:

1. :func:`structure_jd` reads the text line by line. Section headings ("Requirements",
   "Nice to have", "What you'll do", "About us", "Benefits"...) set the context; cues inside a
   line ("must", "required", "5+ years" vs "a plus", "bonus", "preferred", "familiarity with")
   override it. Skills come from the shared taxonomy (``ai.skills`` aliases), years from
   regexes, the title from the first heading-like line that names a role.
2. :func:`polish_structured` (optional, ``use_ai``) lets the configured model *re-classify*
   the result. Its answer is validated by :func:`validate_against_text`: a skill, keyword or
   title survives only when it occurs in the JD text. The model can move a skill between
   required and preferred, or name a tool the taxonomy does not know - it cannot add anything
   the posting does not say.

Skills in "About us" / "Benefits" sections are ignored; skills in responsibilities or general
text count as required unless a line cue says they are optional.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from typing import Any, Iterable

from app.core.exceptions import ValidationFailed
from app.models.ats import JD_TEXT_MAX_CHARS
from app.modules.ai.skills import SKILL_ALIASES, extract_skills, normalize_skill, normalize_skills
from app.modules.ats import llm
from app.modules.ats.schemas import StructuredJD
from app.modules.resumes.extraction import ExtractionError, extract_text, normalize_text
from app.modules.resumes.recommendations import STOP_WORDS

logger = logging.getLogger(__name__)

#: Upload size cap for a JD document (PDF/DOCX/TXT).
MAX_JD_UPLOAD_BYTES = 5 * 1024 * 1024
#: A JD shorter than this (after cleanup) cannot be analysed meaningfully.
MIN_JD_CHARS = 120
MAX_LIST_ITEMS = 15
MAX_KEYWORDS = 10
#: JD text sent to the model for re-classification.
POLISH_MAX_CHARS = 6000

_TOKEN_RE = re.compile(r"[a-z][a-z0-9+#]*(?:-[a-z0-9]+)*")
_BULLET_RE = re.compile(r"^\s*(?:[-*•▪●◦–—·]|\d+[.)])\s*")
_MD_RE = re.compile(r"^\s*#{1,6}\s*|\*\*|__")

_SECTIONS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pattern, re.IGNORECASE))
    for kind, pattern in (
        (
            "preferred",
            r"\b(preferred|nice[\s-]to[\s-]haves?|bonus(?: points)?|good[\s-]to[\s-]have|desir(?:ed|able)|pluses|"
            r"extra credit|it'?s a plus|would be (?:great|nice)|optional)\b",
        ),
        (
            "required",
            r"\b(requirements?|required|must[\s-]haves?|qualifications?|what you(?:'ll| will)? (?:need|bring)|"
            r"what we(?:'re| are) looking for|who you are|about you|you have|you bring|your (?:profile|background|skills|experience)|"
            r"skills|experience|key skills|technical skills|minimum|basic qualifications|essential)\b",
        ),
        (
            "responsibilities",
            r"\b(responsibilities|what you(?:'ll| will) (?:do|work on|be doing)|the role|your role|role overview|"
            r"day[\s-]to[\s-]day|in this role|duties|job description|about the (?:role|job|position|opportunity)|"
            r"the opportunity|you will|key accountabilities|your impact|what you'?ll own)\b",
        ),
        ("general", r"\b(tech(?:nology)? stack|our stack|technologies|tools we use|the team)\b"),
        (
            "other",
            r"\b(about (?:us|the company|[a-z0-9&.' -]{2,40})|benefits|perks|what we offer|why (?:join|work)|compensation|"
            r"salary|pay range|equal (?:opportunity|employment)|eeo|diversity|our (?:values|culture|mission|story)|how to apply|"
            r"life at|privacy|accommodations?|disclaimer)\b",
        ),
    )
)

_PREFERRED_CUE = re.compile(
    r"\b(nice[\s-]to[\s-]have|is a plus|a plus|bonus|preferred|preferably|ideally|good[\s-]to[\s-]have|desirable|"
    r"familiarity with|exposure to|would be (?:great|nice|a plus)|not required|optional|is an advantage|advantageous)\b",
    re.IGNORECASE,
)
_REQUIRED_CUE = re.compile(
    r"\b(must|required|requires|need to|needs to|you have|strong|proficien\w*|expert\w*|solid|deep|minimum|at least|"
    r"essential|mandatory|\d+\s*\+?\s*(?:years?|yrs?))\b",
    re.IGNORECASE,
)

_ROLE_WORDS = re.compile(
    r"\b(engineer|developer|manager|designer|scientist|analyst|architect|lead|intern|sde|swe|consultant|specialist|"
    r"administrator|devops|sre|programmer|researcher|head of|director|tester|qa)\b",
    re.IGNORECASE,
)
_TITLE_PREFIX = re.compile(r"^(?:job\s+title|position|role|title)\s*[:\-–]\s*", re.IGNORECASE)

_YEARS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE),
    re.compile(r"\b(?:at least|minimum(?: of)?|min\.?|over|more than)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s*\+\s*(?:years?|yrs?)\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s*(?:years?|yrs?)['’]?\s+(?:of\s+)?(?:[a-z/+#.-]+\s+){0,4}experience\b", re.IGNORECASE),
)

_SENIORITY: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (level, re.compile(pattern, re.IGNORECASE))
    for level, pattern in (
        ("intern", r"\b(intern|internship|trainee)\b"),
        ("principal", r"\bprincipal\b"),
        ("staff", r"\bstaff\b"),
        ("lead", r"\b(lead|tech lead|team lead)\b"),
        ("senior", r"\b(senior|sr\.?)\b"),
        ("junior", r"\b(junior|jr\.?|entry[\s-]level|graduate|fresher)\b"),
        ("mid", r"\b(mid[\s-]level|intermediate)\b"),
    )
)

_EDUCATION_RE = re.compile(
    r"\b(bachelor'?s?|master'?s?|ph\.?d|doctorate|b\.?\s?tech|m\.?\s?tech|b\.?e\b|b\.?sc?|m\.?sc?|mba|degree|diploma)\b",
    re.IGNORECASE,
)
_EQUIVALENT_RE = re.compile(r"\b(or equivalent|equivalent (?:practical )?experience|or related experience)\b", re.IGNORECASE)

_ALIAS_WORDS: frozenset[str] = frozenset(
    word
    for canonical, aliases in SKILL_ALIASES.items()
    for phrase in [canonical, *aliases]
    for word in re.findall(r"[a-z0-9+#]+", phrase.lower())
)
_LEVEL_WORDS = frozenset(
    {"senior", "junior", "lead", "principal", "staff", "associate", "trainee", "intern", "sr", "jr", "ii", "iii", "iv"}
)
#: Words that are never useful as a single-JD keyword, on top of ``recommendations.STOP_WORDS``.
_JD_STOP_WORDS = frozenset(
    """ability abilities across collaborate collaborating collaboration collaborative communicate communication
    communicator including ensure ensuring implement implementing maintain maintaining develop own owning drive help
    plus excellent understanding familiarity exposure proven record background environment paced starter written
    verbal oral english candidate company teammates colleagues stakeholders cross functional ideally preferably bonus
    equivalent degree bachelor master related field closely closely-with level levels hiring ideal hands-on
    responsibilities requirements qualifications preferred required minimum must nice have want wanted seeking
    looking join joining role position work works using use used new great good strong deep solid within across
    across about into also well able makes make made opportunity opportunities based office remote hybrid
    feature features customer customers product products platform end-to-end team's daily things
    """.split()
)


# --------------------------------------------------------------------------- text helpers


def normalize_jd_text(text: str | None) -> str:
    """Plain, capped JD text: typographic characters folded, blank runs collapsed."""
    cleaned = normalize_text(str(text or ""))
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned[:JD_TEXT_MAX_CHARS]


def text_sha256(text: str) -> str:
    """Hash of the JD text with whitespace and case folded, so a reformatted copy is "unchanged"."""
    folded = " ".join((text or "").lower().split())
    return hashlib.sha256(folded.encode("utf-8")).hexdigest()


def require_readable(text: str) -> str:
    if len(text) < MIN_JD_CHARS:
        raise ValidationFailed(
            "This job description is too short to analyse. Paste the full posting text (requirements and responsibilities).",
            code="jd_too_short",
            details={"chars": len(text), "min_chars": MIN_JD_CHARS},
        )
    return text


def extract_upload_text(filename: str, content: bytes) -> str:
    """Text of an uploaded JD document (PDF, DOCX or TXT)."""
    if len(content) > MAX_JD_UPLOAD_BYTES:
        raise ValidationFailed("The file is larger than 5 MB.", code="file_too_large")
    ext = (filename.rsplit(".", 1)[-1] if "." in (filename or "") else "").lower()
    if ext in ("txt", "md", "text"):
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return normalize_jd_text(content.decode(encoding))
            except UnicodeDecodeError:
                continue
        raise ValidationFailed("The text file could not be decoded.", code="jd_unreadable")
    if ext not in ("pdf", "docx"):
        raise ValidationFailed("Upload a PDF, DOCX or TXT file.", code="unsupported_file_type", details={"extension": ext})
    try:
        return normalize_jd_text(extract_text(content, ext))
    except ExtractionError as exc:
        raise ValidationFailed(f"{exc} Paste the job description text instead.", code="jd_unreadable") from exc


def _strip_line(line: str) -> str:
    return _MD_RE.sub("", line).strip().strip("*_").strip()


def _is_heading(line: str) -> bool:
    text = _strip_line(line)
    if not text or _BULLET_RE.match(line) or len(text) > 80:
        return False
    words = text.rstrip(":").split()
    if not words or len(words) > 8:
        return False
    if text.endswith(":") or line.lstrip().startswith("#"):
        return True
    if text.endswith((".", ",", ";")):
        return False
    # "What you'll do", "Nice to have": short, names a section, and is not itself a requirement.
    if len(words) <= 5 and _section_of(text) is not None and not extract_skills(text):
        return True
    letters = [w for w in words if w[:1].isalpha()]
    if not letters:
        return False
    capitalised = sum(1 for w in letters if w[:1].isupper() or w.lower() in {"and", "of", "to", "the", "a", "for", "you", "we", "with", "in"})
    return text.isupper() or capitalised == len(letters)


def _section_of(heading: str) -> str | None:
    text = _strip_line(heading).rstrip(":").strip()
    for kind, pattern in _SECTIONS:
        if pattern.search(text):
            return kind
    return None


def _contains(text_lower: str, phrase: str) -> bool:
    needle = " ".join(phrase.lower().split())
    if not needle:
        return False
    return bool(re.search(rf"(?<![a-z0-9+#]){re.escape(needle)}(?![a-z0-9+#])", text_lower))


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _dedupe(items: Iterable[str], limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = " ".join(str(item or "").split())
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text[:300])
            if len(out) >= limit:
                break
    return out


# --------------------------------------------------------------------------- structuring


def _years(lines: list[tuple[str, str]]) -> tuple[float | None, float | None]:
    """``(min, max)`` years of experience from required/general lines (preferred lines as a fallback)."""
    def scan(kinds: set[str]) -> tuple[float | None, float | None]:
        for line, kind in lines:
            if kind not in kinds:
                continue
            for pattern in _YEARS_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                numbers = [float(g) for g in match.groups() if g is not None]
                numbers = [n for n in numbers if 0 < n <= 30]
                if not numbers:
                    continue
                if len(numbers) == 2:
                    low, high = sorted(numbers)
                    return low, high
                return numbers[0], None
        return None, None

    found = scan({"required", "general", "responsibilities", "intro"})
    return found if found[0] is not None else scan({"preferred"})


def _seniority(title: str | None, text: str) -> str | None:
    for source in (title or "", text[:1500]):
        for level, pattern in _SENIORITY:
            if source and pattern.search(source):
                return level
    return None


def _title(lines: list[str], given: str | None) -> str | None:
    if given and given.strip():
        return " ".join(given.split())[:255]
    head = [l for l in (_strip_line(x) for x in lines[:12]) if l]
    for line in head:
        candidate = _TITLE_PREFIX.sub("", line).rstrip(":").strip()
        if 1 <= len(candidate.split()) <= 12 and _ROLE_WORDS.search(candidate) and _section_of(candidate) in (None, "general"):
            return candidate[:255]
    for line in head[:3]:
        candidate = _TITLE_PREFIX.sub("", line).rstrip(":").strip()
        if 1 <= len(candidate.split()) <= 10 and not candidate.endswith(".") and _section_of(candidate) is None:
            return candidate[:255]
    return None


def _keywords(lines: list[tuple[str, str]], title: str | None, company: str | None, skills: list[str]) -> list[str]:
    noise = set(STOP_WORDS) | _JD_STOP_WORDS | _ALIAS_WORDS | _LEVEL_WORDS
    noise |= set(_TOKEN_RE.findall((company or "").lower()))
    skill_words = {w for s in skills for w in re.findall(r"[a-z0-9+#]+", s.lower())}
    counts: Counter = Counter()
    first: dict[str, str] = {}
    for line, kind in lines:
        if kind in ("other",):
            continue
        for token in _TOKEN_RE.findall(line.lower()):
            if len(token) < 4 or token in noise or token in skill_words or token.isdigit():
                continue
            stem = _stem(token)
            counts[stem] += 1
            first.setdefault(stem, token)
    title_tokens = {_stem(t) for t in _TOKEN_RE.findall((title or "").lower()) if t not in noise}
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    picked = [first[stem] for stem, count in ranked if count >= 2 or stem in title_tokens]
    return picked[:MAX_KEYWORDS]


def structure_jd(
    text: str,
    *,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
) -> StructuredJD:
    """Deterministic structure of a JD (pure: no DB, no model)."""
    from app.modules.adapters.boards.common import detect_work_mode

    raw_lines = [line for line in (text or "").split("\n")]
    section = "intro"
    seen_heading = False
    classified: list[tuple[str, str]] = []  # (line, effective kind)
    bullets: dict[str, list[str]] = {"required": [], "preferred": [], "responsibilities": []}
    notes: list[str] = []

    for raw in raw_lines:
        line = raw.strip()
        if not line:
            continue
        if _is_heading(raw):
            kind = _section_of(raw)
            if kind:
                section = kind
                seen_heading = True
                # A heading like "Requirements: Python, Go" carries content after the colon.
                head, _, rest = _strip_line(raw).partition(":")
                if rest.strip():
                    classified.append((rest.strip(), section))
                continue
        content = _BULLET_RE.sub("", _strip_line(raw))
        if not content:
            continue
        kind = section
        if kind != "other":
            if _PREFERRED_CUE.search(content):
                kind = "preferred"
            elif kind in ("intro", "responsibilities", "general") and _REQUIRED_CUE.search(content) and extract_skills(content):
                kind = "required"
        classified.append((content, kind))
        if kind in bullets and 8 <= len(content) <= 400:
            bullets[kind].append(content)

    required: list[str] = []
    preferred: list[str] = []
    implied: list[str] = []
    for line, kind in classified:
        if kind == "other":
            continue
        found = extract_skills(line)
        if kind == "required":
            required += found
        elif kind == "preferred":
            preferred += found
        else:
            implied += found
    required_set = {s.lower() for s in required}
    preferred_only = [s for s in normalize_skills(preferred) if s.lower() not in required_set]
    preferred_set = {s.lower() for s in preferred_only}
    required_all = normalize_skills(required + [s for s in implied if s.lower() not in preferred_set])

    if not seen_heading:
        notes.append("No section headings found: skills named anywhere count as required unless the line says they are optional.")
    if not required_all and not preferred_only:
        notes.append("No technical skills from the skill taxonomy were found in this job description.")

    jd_title = _title(raw_lines, title)
    years_min, years_max = _years(classified)
    education = _dedupe((line for line, kind in classified if kind != "other" and _EDUCATION_RE.search(line)), 3)
    degree_required = any(
        kind == "required" and _EDUCATION_RE.search(line) and not _EQUIVALENT_RE.search(line) for line, kind in classified
    )
    work_mode = None
    try:
        # Benefits and "about us" text ("remote stipend") say nothing about this role's work mode.
        relevant = "\n".join(line for line, kind in classified if kind != "other")[:4000]
        work_mode = detect_work_mode(location, jd_title, relevant)
    except Exception:  # noqa: BLE001 - informational
        work_mode = None

    return StructuredJD(
        title=jd_title,
        company=(company or "").strip()[:255] or None,
        location=(location or "").strip()[:255] or None,
        work_mode=work_mode,
        seniority=_seniority(jd_title, text),
        years_min=years_min,
        years_max=years_max,
        required_skills=required_all,
        preferred_skills=preferred_only,
        responsibilities=_dedupe(bullets["responsibilities"], MAX_LIST_ITEMS),
        qualifications=_dedupe(bullets["required"], MAX_LIST_ITEMS),
        preferred_qualifications=_dedupe(bullets["preferred"], MAX_LIST_ITEMS),
        education=education,
        degree_required=degree_required,
        keywords=_keywords(classified, jd_title, company, required_all + preferred_only),
        notes=notes,
    )


# --------------------------------------------------------------------------- validation + model polish


def validate_against_text(text: str, structured: StructuredJD) -> StructuredJD:
    """Drop every skill, keyword or title that does not occur in ``text``.

    Used on the model's answer and on a ``structured`` object a client sends back from
    ``/ats/jd/parse``: classification may change, content may not be invented.
    """
    lower = " ".join((text or "").lower().split())
    taxonomy = {s.lower() for s in extract_skills(text or "")}

    def skill_ok(raw: str) -> str | None:
        canonical = normalize_skill(str(raw or ""))
        if not canonical:
            return None
        if canonical.lower() in taxonomy:
            return canonical
        literal = " ".join(str(raw).split())
        return literal[:60] if 2 <= len(literal) <= 60 and _contains(lower, literal) else None

    def skills(values: Iterable[str]) -> list[str]:
        return _dedupe((s for s in (skill_ok(v) for v in values) if s), 60)

    required = skills(structured.required_skills)
    required_keys = {s.lower() for s in required}
    preferred = [s for s in skills(structured.preferred_skills) if s.lower() not in required_keys]
    title = structured.title if structured.title and _contains(lower, structured.title) else None
    keywords = [k for k in _dedupe(structured.keywords, MAX_KEYWORDS) if _contains(lower, k)]
    lines_ok = lambda items: [i for i in _dedupe(items, MAX_LIST_ITEMS) if _contains(lower, i)]  # noqa: E731
    return structured.model_copy(
        update={
            "title": title,
            "required_skills": required,
            "preferred_skills": preferred,
            "keywords": keywords,
            "responsibilities": lines_ok(structured.responsibilities),
            "qualifications": lines_ok(structured.qualifications),
            "preferred_qualifications": lines_ok(structured.preferred_qualifications),
            "education": lines_ok(structured.education),
        }
    )


_POLISH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "required_skills": {"type": "array", "items": {"type": "string"}},
        "preferred_skills": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["required_skills", "preferred_skills"],
}

_POLISH_RULES = (
    "You classify the requirements of one job posting. Return JSON only: "
    '{"title": "<the job title as written>", "required_skills": [...], "preferred_skills": [...], "keywords": [...]}. '
    "Copy every skill, tool and keyword exactly as it is written in the posting; never add one that is not in it. "
    "required = must-have; preferred = nice-to-have, bonus, a plus. keywords = at most 8 important non-skill terms "
    "(domain, methods), copied from the posting."
)


def polish_structured(text: str, structured: StructuredJD) -> StructuredJD:
    """Let the configured model re-classify ``structured``; any failure keeps the deterministic result."""
    if not llm.model_available(llm.TASK_ANALYZE_JD):
        return structured
    prompt = (
        f"{llm.wrap_untrusted('JOB POSTING', text, max_chars=POLISH_MAX_CHARS)}\n\n"
        f"A rule-based reader found: required={structured.required_skills[:25]}, "
        f"preferred={structured.preferred_skills[:15]}, title={structured.title!r}. Correct the classification."
    )
    try:
        answer = llm.llm_json(
            llm.TASK_ANALYZE_JD, prompt, schema=_POLISH_SCHEMA, system=llm.system_prompt(_POLISH_RULES), max_tokens=600
        )
    except Exception as exc:  # noqa: BLE001 - the deterministic structure is always valid
        logger.info("JD polish failed; keeping the rule-based structure: %s", exc)
        return structured
    if not isinstance(answer, dict):
        return structured
    candidate = structured.model_copy(
        update={
            "title": structured.title or (str(answer.get("title") or "").strip() or None),
            "required_skills": [str(s) for s in answer.get("required_skills") or [] if isinstance(s, str)],
            "preferred_skills": [str(s) for s in answer.get("preferred_skills") or [] if isinstance(s, str)],
            "keywords": [str(s) for s in answer.get("keywords") or [] if isinstance(s, str)] or structured.keywords,
        }
    )
    checked = validate_against_text(text, candidate)
    # Anything the rules found and the model silently dropped keeps its rule-based class.
    have = {s.lower() for s in checked.required_skills + checked.preferred_skills}
    required = checked.required_skills + [s for s in structured.required_skills if s.lower() not in have]
    have |= {s.lower() for s in required}
    preferred = checked.preferred_skills + [s for s in structured.preferred_skills if s.lower() not in have]
    return checked.model_copy(
        update={
            "required_skills": normalize_skills(required),
            "preferred_skills": [s for s in normalize_skills(preferred) if s.lower() not in {r.lower() for r in required}],
            "title": checked.title or structured.title,
            "ai_polished": True,
        }
    )


def build_structured(
    text: str,
    *,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    use_ai: bool = False,
    client_structured: StructuredJD | None = None,
) -> StructuredJD:
    """The structure stored with a snapshot: the client's (re-validated) or a fresh one."""
    if client_structured is not None:
        base = structure_jd(text, title=title, company=company, location=location)
        checked = validate_against_text(text, client_structured)
        return checked.model_copy(
            update={
                "title": title or checked.title or base.title,
                "company": company or checked.company or base.company,
                "years_min": checked.years_min if checked.years_min is not None else base.years_min,
                "years_max": checked.years_max if checked.years_max is not None else base.years_max,
                "seniority": checked.seniority or base.seniority,
            }
        )
    structured = structure_jd(text, title=title, company=company, location=location)
    return polish_structured(text, structured) if use_ai else structured


__all__ = [
    "MAX_JD_UPLOAD_BYTES",
    "MIN_JD_CHARS",
    "build_structured",
    "extract_upload_text",
    "normalize_jd_text",
    "polish_structured",
    "require_readable",
    "structure_jd",
    "text_sha256",
    "validate_against_text",
]
