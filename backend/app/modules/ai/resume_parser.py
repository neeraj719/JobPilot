"""Deterministic, rule-based resume parsing.

This is what ``MockLLMProvider`` runs for the ``parse_resume`` task, and it is also
the safety net when a real provider returns something unusable. It is intentionally
conservative: **every value is copied from the resume text**, nothing is inferred
beyond dates arithmetic, so the parser can never fabricate a qualification.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.modules.ai.skills import extract_skills, normalize_skills

logger = logging.getLogger(__name__)

MAX_PLAUSIBLE_YEARS = 40.0

# --------------------------------------------------------------------------- regexes

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().\-]{7,18}\d)")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s,;<>()\[\]]+", re.IGNORECASE)
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/(?:in|pub)/[A-Za-z0-9_\-%.]+/?", re.IGNORECASE)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9_\-.]+/?", re.IGNORECASE)

_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
MONTH_RE = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_TOKEN = rf"(?:{MONTH_RE}[\s,/'-]*\d{{4}}|\d{{1,2}}[/-]\d{{4}}|\d{{4}})"
PRESENT_TOKEN = r"(?:present|current|currently|now|to\s?date|till\s?date|ongoing)"
RANGE_SEP = r"\s*(?:-{1,2}|–|—|to|until|through)\s*"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{DATE_TOKEN}){RANGE_SEP}(?P<end>{PRESENT_TOKEN}|{DATE_TOKEN})",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

_EXPLICIT_YEARS_RE = re.compile(
    r"(?P<years>\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)(?P<tail>[^.\n]{0,40})",
    re.IGNORECASE,
)
_EXPERIENCE_WORD_RE = re.compile(r"experien|exp\b|professional|industry|overall|total", re.IGNORECASE)

DEGREE_RE = re.compile(
    r"\b(b\.?\s?tech|b\.?\s?e\.?|bachelor(?:'?s)?|b\.?\s?sc|b\.?\s?c\.?\s?a|b\.?\s?com|"
    r"m\.?\s?tech|m\.?\s?sc|m\.?\s?c\.?\s?a|m\.?\s?com|master(?:'?s)?|m\.?b\.?a|"
    r"ph\.?\s?d|doctorate|diploma|h\.?s\.?c|s\.?s\.?c|intermediate)\b",
    re.IGNORECASE,
)

_TITLE_KEYWORDS = (
    "engineer", "developer", "programmer", "architect", "analyst", "scientist", "manager", "lead",
    "consultant", "designer", "administrator", "intern", "internship", "specialist", "sde", "swe",
    "qa", "tester", "devops", "sre", "full stack", "fullstack", "full-stack", "backend", "back-end",
    "frontend", "front-end", "founder", "cto", "head of", "associate", "trainee", "director",
)
_LOCATION_HINTS = (
    "remote", "hybrid", "onsite", "on-site", "wfh", "india", "bangalore", "bengaluru", "hyderabad",
    "pune", "chennai", "mumbai", "delhi", "ncr", "gurgaon", "gurugram", "noida", "kolkata", "kochi",
    "ahmedabad", "jaipur", "indore", "chandigarh", "coimbatore", "united states", "usa", "uk",
    "london", "singapore", "berlin", "toronto", "dubai", "sydney", "amsterdam", "new york",
)
_INSTITUTION_HINTS = (
    "university", "college", "institute", "school", "academy", "iit", "nit", "bits", "vit", "polytechnic",
)
# Trailing words that are part of a certification's *name*, not its issuer.
_CERT_LEVEL_WORDS = frozenset(
    {"associate", "professional", "specialty", "expert", "foundational", "practitioner", "fundamentals", "advanced", "level 1", "level 2"}
)
_ISSUER_PREFIXES = (
    ("aws", "Amazon Web Services"),
    ("amazon web services", "Amazon Web Services"),
    ("azure", "Microsoft"),
    ("microsoft", "Microsoft"),
    ("google cloud", "Google Cloud"),
    ("google", "Google"),
    ("oracle", "Oracle"),
    ("cisco", "Cisco"),
    ("comptia", "CompTIA"),
    ("kubernetes", "CNCF"),
    ("cka", "CNCF"),
    ("ckad", "CNCF"),
    ("terraform", "HashiCorp"),
    ("hashicorp", "HashiCorp"),
    ("scrum", "Scrum Alliance"),
    ("pmp", "PMI"),
    ("meta", "Meta"),
    ("coursera", "Coursera"),
    ("udemy", "Udemy"),
    ("hackerrank", "HackerRank"),
    ("mongodb", "MongoDB"),
)

# A heading is the WHOLE line (plus decoration) — "Languages: Java, Python" is content, not a heading.
SECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("summary", r"(?:professional|career|personal)?\s*(?:summary|profile|about(?:\s+me)?|objective|overview)"),
    (
        "skills",
        r"(?:technical|core|key|primary)?\s*(?:skills?|skill\s*set|technologies|tech(?:nology)?\s*stack|competencies|expertise)"
        r"(?:\s*(?:&|and|/)\s*(?:tools|technologies|abilities|expertise|frameworks|skills))?",
    ),
    (
        "experience",
        r"(?:work|professional|employment|industry|relevant)?\s*(?:experience|work\s+history|employment\s+history|history|employment)",
    ),
    ("education", r"(?:education(?:al)?(?:\s+(?:background|qualifications?))?|academics?|academic\s+background|qualifications?)"),
    ("projects", r"(?:personal|key|selected|academic|notable|side)?\s*projects?"),
    ("certifications", r"(?:certifications?|certificates?|licen[sc]es?)(?:\s*(?:&|and)\s*(?:certifications?|awards?))?"),
    ("achievements", r"(?:achievements?|awards?|honou?rs?|accomplishments?)(?:\s*(?:&|and)\s*(?:awards?|achievements?))?"),
    ("languages", r"languages?(?:\s+(?:known|spoken))?"),
    ("interests", r"(?:interests?|hobbies)(?:\s*(?:&|and)\s*(?:hobbies|interests?))?"),
    ("publications", r"publications?"),
    ("contact", r"(?:contact(?:\s+(?:info|information|details))?|personal\s+details)"),
)
_SECTION_COMPILED = tuple(
    (name, re.compile(rf"{pattern}[\s:|.\-–—]*", re.IGNORECASE)) for name, pattern in SECTION_PATTERNS
)

_BULLET_RE = re.compile(r"^\s*(?:[-*•●▪·o]|\d+[.)])\s+")


# --------------------------------------------------------------------------- helpers


def _clean_lines(text: str) -> list[str]:
    normalised = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    return [re.sub(r"[ \t]+", " ", line).rstrip() for line in normalised.split("\n")]


def _is_bullet(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


def _strip_bullet(line: str) -> str:
    return _BULLET_RE.sub("", line).strip()


def _is_heading(line: str) -> str | None:
    candidate = line.strip().strip("_=*#").strip()
    if not candidate or len(candidate) > 60 or len(candidate.split()) > 6:
        return None
    for name, regex in _SECTION_COMPILED:
        if regex.fullmatch(candidate):
            return name
    return None


def split_sections(lines: list[str]) -> dict[str, list[str]]:
    """Group resume lines by section name. Text before the first heading is ``header``."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in lines:
        heading = _is_heading(line)
        if heading:
            current = heading
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _section_text(sections: dict[str, list[str]], name: str) -> str:
    return "\n".join(sections.get(name, [])).strip()


def _looks_like_name(line: str) -> bool:
    candidate = line.strip().strip("|-—–").strip()
    if not candidate or len(candidate) > 60 or any(ch.isdigit() for ch in candidate):
        return False
    if "@" in candidate or "http" in candidate.lower() or "/" in candidate:
        return False
    lowered = candidate.lower()
    if any(word in lowered for word in ("resume", "curriculum", "vitae", "profile", "portfolio")):
        return False
    words = candidate.split()
    if not 2 <= len(words) <= 4:
        return False
    return all(w[0].isupper() or w.isupper() for w in words if w and w[0].isalpha())


def _extract_name(sections: dict[str, list[str]], lines: list[str]) -> str | None:
    for line in sections.get("header", []) or lines:
        if _looks_like_name(line):
            return re.sub(r"\s+", " ", line.strip())
    return None


def _extract_phone(text: str) -> str | None:
    for raw in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", raw)
        if 10 <= len(digits) <= 15 and not re.fullmatch(r"(?:19|20)\d{2}", digits):
            return re.sub(r"\s{2,}", " ", raw.strip(" .-"))
    return None


def _extract_links(text: str) -> dict[str, str | None]:
    def _normalise(url: str) -> str:
        url = url.rstrip("/.,;")
        return url if url.lower().startswith("http") else f"https://{url}"

    linkedin = LINKEDIN_RE.search(text)
    github = GITHUB_RE.search(text)
    portfolio: str | None = None
    for candidate in URL_RE.findall(text):
        lowered = candidate.lower()
        if "linkedin.com" in lowered or "github.com" in lowered:
            continue
        portfolio = _normalise(candidate)
        break
    return {
        "linkedin": _normalise(linkedin.group(0)) if linkedin else None,
        "github": _normalise(github.group(0)) if github else None,
        "portfolio": portfolio,
    }


# --------------------------------------------------------------------------- dates


def _parse_date_token(token: str) -> tuple[int, int] | None:
    """Return ``(year, month)`` for a date token; month defaults to 1/12 heuristics."""
    if not token:
        return None
    lowered = token.strip().lower()
    if re.match(PRESENT_TOKEN, lowered):
        now = datetime.now(timezone.utc)
        return now.year, now.month
    month_match = re.match(rf"({MONTH_RE})[\s,/'-]*(\d{{4}})", lowered)
    if month_match:
        month = _MONTH_NAMES.get(month_match.group(1)[:4].strip("."), _MONTH_NAMES.get(month_match.group(1)[:3], 1))
        return int(month_match.group(2)), month
    numeric = re.match(r"(\d{1,2})[/-](\d{4})", lowered)
    if numeric:
        month = max(1, min(12, int(numeric.group(1))))
        return int(numeric.group(2)), month
    year_only = re.match(r"(\d{4})", lowered)
    if year_only:
        return int(year_only.group(1)), 1
    return None


def _format_date(token: str) -> str | None:
    if not token:
        return None
    if re.match(PRESENT_TOKEN, token.strip().lower()):
        return "Present"
    parsed = _parse_date_token(token)
    if not parsed:
        return token.strip() or None
    year, month = parsed
    if re.fullmatch(r"\d{4}", token.strip()):
        return str(year)
    return f"{year:04d}-{month:02d}"


def _months_between(start: tuple[int, int], end: tuple[int, int]) -> int:
    return max(0, (end[0] - start[0]) * 12 + (end[1] - start[1]))


def _merge_intervals(intervals: list[tuple[int, int]]) -> int:
    """Total months covered by (possibly overlapping) [start_month, end_month] pairs."""
    if not intervals:
        return 0
    ordered = sorted(intervals)
    total = 0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    total += current_end - current_start
    return max(0, total)


# --------------------------------------------------------------------------- blocks


def _looks_like_header_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or _is_bullet(line):
        return False
    return len(stripped.split()) <= 12 and not stripped.endswith(".")


def _split_blocks(lines: list[str]) -> list[list[str]]:
    """Split a section into entry blocks anchored on lines carrying a date range."""
    date_indexes = [i for i, line in enumerate(lines) if DATE_RANGE_RE.search(line)]
    if not date_indexes:
        return _split_blocks_by_blank(lines)

    starts: list[int] = []
    for index in date_indexes:
        start = index
        cursor = index - 1
        steps = 0
        while cursor >= 0 and steps < 2:
            if starts and cursor <= starts[-1]:
                break
            line = lines[cursor]
            if not line.strip() or DATE_RANGE_RE.search(line) or not _looks_like_header_line(line):
                break
            start = cursor
            cursor -= 1
            steps += 1
        if starts and start <= starts[-1]:
            continue
        starts.append(start)

    blocks: list[list[str]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        block = [line for line in lines[start:end]]
        if any(line.strip() for line in block):
            blocks.append(block)
    return blocks


def _split_blocks_by_blank(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if not line.strip():
            if current:
                blocks.append(current)
                current = []
            continue
        if current and not _is_bullet(line) and _is_bullet(current[-1]):
            blocks.append(current)
            current = [line]
            continue
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


_SPLIT_PARTS_RE = re.compile(r"\s*(?:\||—|–|–|—|,|\bat\b|@|·|•|\s-\s)\s*", re.IGNORECASE)


def _split_header_parts(text: str) -> list[str]:
    parts = [p.strip(" .:-|") for p in _SPLIT_PARTS_RE.split(text)]
    return [p for p in parts if p and len(p) > 1]


def _is_title_part(part: str) -> bool:
    lowered = part.lower()
    return any(keyword in lowered for keyword in _TITLE_KEYWORDS)


def _is_location_part(part: str) -> bool:
    lowered = part.lower()
    return any(hint == lowered or hint in lowered for hint in _LOCATION_HINTS) and not _is_title_part(part)


# --------------------------------------------------------------------------- sections


def _parse_experience(section_lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for block in _split_blocks(section_lines):
        block_text = "\n".join(block).strip()
        if not block_text:
            continue
        date_line_index = next((i for i, line in enumerate(block) if DATE_RANGE_RE.search(line)), None)
        start = end = None
        header_lines = block[: (date_line_index + 1) if date_line_index is not None else 1]
        if date_line_index is not None:
            match = DATE_RANGE_RE.search(block[date_line_index])
            if match:
                start = _format_date(match.group("start"))
                end = _format_date(match.group("end"))
            header_lines = list(block[:date_line_index]) + [DATE_RANGE_RE.sub(" ", block[date_line_index])]

        parts: list[str] = []
        for line in header_lines:
            if _is_bullet(line):
                continue
            parts.extend(_split_header_parts(line))

        title = next((p for p in parts if _is_title_part(p)), None)
        remaining = [p for p in parts if p != title and not _is_location_part(p)]
        company = next((p for p in remaining if p), None)
        if title is None and len(parts) >= 2:
            title, company = parts[0], parts[1]
        elif title is None and parts:
            company = parts[0]

        body_start = (date_line_index + 1) if date_line_index is not None else 1
        description_lines = [line.strip() for line in block[body_start:] if line.strip()]
        description = "\n".join(description_lines)[:1500] or None

        if not any([title, company, start, end]):
            continue
        entries.append(
            {
                "company": company,
                "title": title,
                "start": start,
                "end": end,
                "description": description,
                "technologies": extract_skills(block_text),
            }
        )
    return entries


def _parse_education(section_lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    blocks = _split_blocks_by_blank(section_lines)
    if len(blocks) <= 1:
        degree_lines = [i for i, line in enumerate(section_lines) if DEGREE_RE.search(line)]
        if len(degree_lines) > 1:
            blocks = []
            for position, index in enumerate(degree_lines):
                stop = degree_lines[position + 1] if position + 1 < len(degree_lines) else len(section_lines)
                start = index - 1 if index > 0 and position == 0 and section_lines[index - 1].strip() else index
                blocks.append(section_lines[start:stop])

    for block in blocks:
        block_text = "\n".join(block).strip()
        if not block_text:
            continue
        degree_match = DEGREE_RE.search(block_text)
        institution = None
        for line in block:
            for part in _split_header_parts(line) or [line.strip()]:
                if any(hint in part.lower() for hint in _INSTITUTION_HINTS):
                    institution = part.strip(" ,|-")
                    break
            if institution:
                break
        if not degree_match and not institution:
            continue

        degree = None
        field = None
        if degree_match:
            degree_line = next((line for line in block if DEGREE_RE.search(line)), block[0])
            line_match = DEGREE_RE.search(degree_line) or degree_match
            degree = re.sub(r"\s+", " ", line_match.group(0)).strip()
            tail = degree_line[line_match.end() :]
            field_match = re.search(r"^\s*(?:[.,:;|/-]|–|—)?\s*(?:in|of)?\s+([A-Za-z&/ ]{3,60})", tail)
            if field_match:
                candidate = re.sub(r"\s+", " ", field_match.group(1)).strip(" ,.-")
                if candidate and not any(hint in candidate.lower() for hint in _INSTITUTION_HINTS):
                    field = candidate

        start = end = None
        range_match = DATE_RANGE_RE.search(block_text)
        if range_match:
            start = _format_date(range_match.group("start"))
            end = _format_date(range_match.group("end"))
        else:
            all_years = [m.group(0) for m in YEAR_RE.finditer(block_text)]
            if len(all_years) >= 2:
                start, end = all_years[0], all_years[1]
            elif all_years:
                end = all_years[0]

        entries.append(
            {
                "institution": institution,
                "degree": degree,
                "field": field,
                "start": start,
                "end": end,
            }
        )
    return entries


_PROJECT_META_RE = re.compile(
    r"^(?:tech(?:nologies)?|stack|tools|description|role|link|url|github|demo|impact|outcome|repo)\b",
    re.IGNORECASE,
)
_PROJECT_HEADING_RE = re.compile(r"^[A-Za-z0-9][\w .+#/&'()-]{1,60}?(?:\s+[-–—|]\s+|:\s+)")


def _is_project_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or _is_bullet(line) or _PROJECT_META_RE.match(stripped):
        return False
    return bool(_PROJECT_HEADING_RE.match(stripped))


def _split_project_blocks(section_lines: list[str]) -> list[list[str]]:
    """Blank lines first; otherwise split on "Name - description" heading lines."""
    refined: list[list[str]] = []
    for block in _split_blocks_by_blank(section_lines):
        heads = [i for i, line in enumerate(block) if _is_project_heading(line)]
        if len(heads) <= 1:
            refined.append(block)
            continue
        for position, index in enumerate(heads):
            stop = heads[position + 1] if position + 1 < len(heads) else len(block)
            start = 0 if position == 0 else index
            refined.append(block[start:stop])
    return refined


def _parse_projects(section_lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for block in _split_project_blocks(section_lines):
        block_text = "\n".join(block).strip()
        if not block_text:
            continue
        head = _strip_bullet(block[0]).strip()
        head_parts = re.split(r"\s+[-–—:|]\s+|:\s+", head, maxsplit=1)
        name = (head_parts[0] if head_parts else head).strip(" .:-")
        inline_description = head_parts[1].strip() if len(head_parts) > 1 else ""
        description_parts = [part for part in [inline_description] if part]
        for line in block[1:]:
            stripped = _strip_bullet(line).strip()
            if stripped:
                description_parts.append(stripped)
        technologies = extract_skills(block_text)
        explicit = re.search(r"(?:tech(?:nologies)?|stack|tools)\s*[:\-]\s*(.+)", block_text, re.IGNORECASE)
        if explicit:
            technologies = normalize_skills(re.split(r"[,/|]", explicit.group(1))) or technologies
        if not name:
            continue
        entries.append(
            {
                "name": name[:200],
                "description": " ".join(description_parts)[:1000] or None,
                "technologies": technologies,
            }
        )
    return entries


def _parse_certifications(section_lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw in section_lines:
        line = _strip_bullet(raw).strip(" .")
        if not line or len(line) < 4:
            continue
        year_match = re.search(r"\b((?:19|20)\d{2})\b", line)
        year = year_match.group(1) if year_match else None
        without_year = re.sub(r"[\(\[]?\b(?:19|20)\d{2}\b[\)\]]?", " ", line).strip(" ,.|-–—")
        parts = [p.strip() for p in re.split(r"\s*[|–—]\s*|\s+-\s+|\s*,\s*(?=[A-Z])", without_year) if p.strip()]
        name = without_year
        issuer = None
        if len(parts) > 1 and parts[-1].lower() not in _CERT_LEVEL_WORDS:
            name, issuer = parts[0], parts[1]
        if not issuer:
            lowered = name.lower()
            for prefix, canonical in _ISSUER_PREFIXES:
                if lowered.startswith(prefix) or f" {prefix} " in f" {lowered} ":
                    issuer = canonical
                    break
        if not name:
            continue
        entries.append({"name": name[:200], "issuer": issuer, "year": year})
    return entries


def _parse_summary(sections: dict[str, list[str]], full_text: str) -> str | None:
    lines = sections.get("summary") or []
    paragraph: list[str] = []
    for line in lines:
        if not line.strip():
            if paragraph:
                break
            continue
        paragraph.append(_strip_bullet(line).strip())
    if paragraph:
        return re.sub(r"\s+", " ", " ".join(paragraph)).strip()[:1000]
    stripped = re.sub(r"\s+", " ", full_text).strip()
    return stripped[:400] or None


def _total_experience_years(full_text: str, experience: list[dict[str, Any]]) -> float | None:
    contextual: list[float] = []
    loose: list[float] = []
    for match in _EXPLICIT_YEARS_RE.finditer(full_text):
        try:
            years = float(match.group("years"))
        except ValueError:  # pragma: no cover - regex guarantees a number
            continue
        if years <= 0 or years > MAX_PLAUSIBLE_YEARS:
            continue
        window_start = max(0, match.start() - 60)
        window = full_text[window_start : match.end() + 40]
        (contextual if _EXPERIENCE_WORD_RE.search(window) else loose).append(years)
    if contextual:
        return round(max(contextual), 1)

    intervals: list[tuple[int, int]] = []
    for entry in experience:
        start = _parse_date_token(entry.get("start") or "")
        end = _parse_date_token(entry.get("end") or "") if entry.get("end") else None
        if entry.get("end") in (None, "Present"):
            now = datetime.now(timezone.utc)
            end = (now.year, now.month)
        if not start or not end:
            continue
        start_months = start[0] * 12 + start[1]
        end_months = end[0] * 12 + end[1]
        if end_months > start_months:
            intervals.append((start_months, end_months))
    if intervals:
        months = _merge_intervals(intervals)
        if months:
            return round(min(months / 12.0, MAX_PLAUSIBLE_YEARS), 1)
    if loose:
        return round(max(loose), 1)
    return None


# --------------------------------------------------------------------------- entry point


def parse_resume_text(text: str) -> dict[str, Any]:
    """Parse raw resume text into a ``ParsedResume``-shaped dict."""
    lines = _clean_lines(text)
    full_text = "\n".join(lines)
    sections = split_sections(lines)

    email_match = EMAIL_RE.search(full_text)
    skills_section = _section_text(sections, "skills")
    skills = normalize_skills(extract_skills(skills_section) + extract_skills(full_text))

    experience = _parse_experience(sections.get("experience", []))
    parsed: dict[str, Any] = {
        "name": _extract_name(sections, lines),
        "email": email_match.group(0) if email_match else None,
        "phone": _extract_phone(full_text),
        "summary": _parse_summary(sections, full_text),
        "skills": skills,
        "experience": experience,
        "education": _parse_education(sections.get("education", [])),
        "projects": _parse_projects(sections.get("projects", [])),
        "certifications": _parse_certifications(sections.get("certifications", [])),
        "total_experience_years": _total_experience_years(full_text, experience),
        "links": _extract_links(full_text),
    }
    logger.debug(
        "Rule-based resume parse: %d skills, %d experience, %d education entries",
        len(parsed["skills"]),
        len(parsed["experience"]),
        len(parsed["education"]),
    )
    return parsed


__all__ = ["DATE_RANGE_RE", "parse_resume_text", "split_sections"]
