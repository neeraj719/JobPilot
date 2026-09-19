"""Normalisation helpers shared by dedupe, matching and the job filters.

Two postings for the same role can look very different across platforms::

    "Sr. Software Engineer (Backend) - Bangalore"   on LinkedIn
    "Senior Software Engineer | Bengaluru"          on Naukri

After :func:`normalize_title` / :func:`normalize_location` both become
``"senior software engineer"`` / ``"bangalore"`` so the dedupe hash matches.
"""
from __future__ import annotations

import re

__all__ = [
    "normalize_title",
    "normalize_location",
    "normalize_company_name",
    "is_remote_location",
    "CITY_ALIASES",
]

# --------------------------------------------------------------------------- titles

#: Words that add nothing to the identity of a role.
_TITLE_NOISE: frozenset[str] = frozenset(
    {
        "hiring",
        "urgent",
        "urgently",
        "immediate",
        "immediately",
        "joiner",
        "joiners",
        "wfh",
        "apply",
        "now",
        "opening",
        "openings",
        "vacancy",
        "vacancies",
        "job",
        "jobs",
        "role",
        "required",
        "reqd",
        "needed",
        "hiring!",
    }
)

_ROMAN_TO_ARABIC: dict[str, str] = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}

#: Abbreviation expansions applied on whole tokens.
_TITLE_ABBREVIATIONS: tuple[tuple[str, str], ...] = (
    (r"\bsr\b", "senior"),
    (r"\bjr\b", "junior"),
    (r"\bsdet\b", "software development engineer in test"),
    (r"\bsde\b", "software development engineer"),
    (r"\bswe\b", "software engineer"),
    (r"\bmts\b", "member of technical staff"),
    (r"\bsre\b", "site reliability engineer"),
    (r"\bui\s*/\s*ux\b", "ui ux"),
    (r"\bfull\s*-\s*stack\b", "full stack"),
    (r"\bfullstack\b", "full stack"),
    (r"\bback\s*-?\s*end\b", "backend"),
    (r"\bfront\s*-?\s*end\b", "frontend"),
    (r"\bdev\s*ops\b", "devops"),
)


def normalize_title(title: str | None) -> str:
    """Canonical, comparable form of a job title.

    * lowercases and strips punctuation
    * drops parenthetical / bracketed noise — ``"Engineer (Remote)"`` → ``"engineer"``
    * expands abbreviations — ``"Sr."`` → ``"senior"``, ``"SDE"`` → ``"software development engineer"``
    * folds level numerals — ``"SDE II"``/``"SDE 2"`` → ``"software development engineer 2"``
    """
    if not title:
        return ""
    text = title.lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"\{[^}]*\}", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9+#./\s-]", " ", text)
    text = re.sub(r"\.", " ", text)  # "sr." -> "sr "
    for pattern, replacement in _TITLE_ABBREVIATIONS:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"[/|,_\\-]", " ", text)
    tokens = [t for t in text.split() if t and t not in _TITLE_NOISE]
    folded: list[str] = []
    for index, token in enumerate(tokens):
        if index > 0 and token in _ROMAN_TO_ARABIC:
            folded.append(_ROMAN_TO_ARABIC[token])
        else:
            folded.append(token)
    return " ".join(folded).strip()


# --------------------------------------------------------------------------- locations

#: alias → canonical city. Everything in the NCR collapses to ``"delhi ncr"``.
CITY_ALIASES: dict[str, str] = {
    "bangalore": "bangalore",
    "bengaluru": "bangalore",
    "bangaluru": "bangalore",
    "blr": "bangalore",
    "bangalore urban": "bangalore",
    "gurgaon": "gurugram",
    "gurugram": "gurugram",
    "delhi": "delhi ncr",
    "new delhi": "delhi ncr",
    "delhi ncr": "delhi ncr",
    "ncr": "delhi ncr",
    "noida": "delhi ncr",
    "greater noida": "delhi ncr",
    "ghaziabad": "delhi ncr",
    "faridabad": "delhi ncr",
    "hyderabad": "hyderabad",
    "secunderabad": "hyderabad",
    "hyd": "hyderabad",
    "pune": "pune",
    "pimpri chinchwad": "pune",
    "mumbai": "mumbai",
    "bombay": "mumbai",
    "navi mumbai": "mumbai",
    "thane": "mumbai",
    "chennai": "chennai",
    "madras": "chennai",
    "kolkata": "kolkata",
    "calcutta": "kolkata",
    "ahmedabad": "ahmedabad",
    "jaipur": "jaipur",
    "kochi": "kochi",
    "cochin": "kochi",
    "coimbatore": "coimbatore",
    "indore": "indore",
    "chandigarh": "chandigarh",
    "trivandrum": "trivandrum",
    "thiruvananthapuram": "trivandrum",
    "bhubaneswar": "bhubaneswar",
    "remote": "remote",
    "anywhere": "remote",
    "work from home": "remote",
    "wfh": "remote",
    "india": "india",
}

_REMOTE_MARKERS: tuple[str, ...] = ("remote", "work from home", "wfh", "anywhere", "telecommute")

#: Dropped when they trail a city ("Bangalore, Karnataka, India").
_LOCATION_NOISE: frozenset[str] = frozenset(
    {
        "india",
        "karnataka",
        "telangana",
        "maharashtra",
        "tamil nadu",
        "haryana",
        "uttar pradesh",
        "delhi state",
        "west bengal",
        "kerala",
        "gujarat",
        "rajasthan",
        "in",
        "hybrid",
        "onsite",
        "on site",
        "office",
        "full time",
    }
)


def is_remote_location(location: str | None) -> bool:
    """True when the raw location string advertises remote work."""
    if not location:
        return False
    lowered = location.lower()
    return any(marker in lowered for marker in _REMOTE_MARKERS)


def normalize_location(location: str | None) -> str | None:
    """Canonical city (or ``"remote"``) for a free-form location string."""
    if not location:
        return None
    text = location.lower().strip()
    if is_remote_location(text):
        return "remote"
    text = re.sub(r"[^a-z0-9,/|\-\s]", " ", text)
    parts = [p.strip() for p in re.split(r"[,/|]|\s-\s|\s+or\s+", text) if p.strip()]
    for part in parts:
        collapsed = " ".join(part.split())
        if collapsed in CITY_ALIASES:
            return CITY_ALIASES[collapsed]
    # second pass: a city name embedded in a longer phrase ("hybrid bangalore office")
    for part in parts:
        collapsed = " ".join(part.split())
        for alias, canonical in CITY_ALIASES.items():
            if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", collapsed):
                return canonical
    meaningful = [p for p in (" ".join(part.split()) for part in parts) if p not in _LOCATION_NOISE]
    if not meaningful:
        return None
    return meaningful[0]


# --------------------------------------------------------------------------- companies

#: Legal / filler suffixes removed before comparing company names.
_COMPANY_SUFFIXES: tuple[str, ...] = (
    "private limited",
    "pvt ltd",
    "pvt limited",
    "pvt",
    "private",
    "limited",
    "ltd",
    "llp",
    "llc",
    "inc",
    "incorporated",
    "corporation",
    "corp",
    "co",
    "company",
    "technologies",
    "technology",
    "technologie",
    "tech",
    "labs",
    "lab",
    "solutions",
    "systems",
    "services",
    "software",
    "india",
    "global",
    "group",
    "holdings",
)


def normalize_company_name(name: str | None) -> str:
    """Fallback implementation of ``companies.service.normalize_company_name``.

    Lowercases, strips legal suffixes and removes every non-alphanumeric character so
    ``"Acme Cloud Pvt. Ltd."`` and ``"ACME Cloud"`` collapse to ``"acmecloud"``.
    """
    if not name:
        return ""
    text = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    tokens = [t for t in text.split() if t]
    while len(tokens) > 1 and tokens[-1] in _COMPANY_SUFFIXES:
        tokens.pop()
    collapsed = "".join(tokens)
    return collapsed or re.sub(r"[^a-z0-9]", "", name.lower())
