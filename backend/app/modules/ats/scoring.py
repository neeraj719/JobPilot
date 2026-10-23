"""Estimated ATS compatibility of one resume against one job description - pure and deterministic.

Nine categories, each 0-100 with the evidence that produced it. The overall estimate is the
weighted mean of the categories that apply (a JD with no stated years of experience has no
"years" signal, so its weight is shared by the others). Weights live in :data:`ATS_WEIGHTS`
under :data:`METHODOLOGY_VERSION` and can be overridden per request within
:data:`WEIGHT_BOUNDS` (they are re-normalised to sum to 1).

===========================  =============================================================
``keyword_coverage``         JD keywords on the resume: skills (exact or alias), non-skill
                             terms (light stemming), the job title. Required skills count 2x.
``required_vs_preferred``    Required items (skills 3x, years, degree) vs preferred skills (1x).
``technical_skills``         Depth of evidence per JD skill: shown in a role or project (0.6)
                             plus listed in the skills section (0.4).
``title_alignment``          Most recent / past titles and the summary vs the JD title.
``experience_relevance``     Years vs the JD's range; recent titles and recent use of the
                             required skills.
``achievement_quality``      Bullets with an outcome (55%), a strong opening verb (30%) and a
                             readable length (15%).
``readability_format``       Long bullets, passive phrasing, walls of text, length, pronouns.
``section_completeness``     Contact, summary, skills, experience, education, links.
``parse_risk``               Parsing safety (higher = safer): contact details, odd symbols,
                             tables, empty entries, missing dates, failed parse.
===========================  =============================================================

The result is an **estimate**: real ATS products differ and none of them is reproduced here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import ValidationFailed
from app.modules.ai.skills import extract_skills, normalize_skill, skill_category
from app.modules.ats.schemas import (
    CategoryScore,
    KeywordHit,
    KeywordMiss,
    Methodology,
    MethodologyCategory,
    ParseRisk,
    StructuredJD,
    WeakItem,
)
from app.modules.matching import scoring as match_scoring
from app.modules.resumes import recommendations as rec

METHODOLOGY_VERSION = "ats-2026.10-v1"

ATS_WEIGHTS: dict[str, float] = {
    "keyword_coverage": 0.20,
    "required_vs_preferred": 0.15,
    "technical_skills": 0.12,
    "title_alignment": 0.10,
    "experience_relevance": 0.13,
    "achievement_quality": 0.10,
    "readability_format": 0.06,
    "section_completeness": 0.08,
    "parse_risk": 0.06,
}
WEIGHT_BOUNDS: dict[str, float] = {"min": 0.0, "max": 0.5}

CATEGORIES: dict[str, tuple[str, str]] = {
    "keyword_coverage": (
        "Keyword coverage",
        "Share of the posting's keywords found on the resume: skills by name or alias, other terms with light "
        "stemming, and the job title. Required skills and the title count double.",
    ),
    "required_vs_preferred": (
        "Required vs preferred",
        "Required items (each required skill x3, the years of experience, a required degree) against the "
        "preferred skills (x1).",
    ),
    "technical_skills": (
        "Technical skills depth",
        "For each skill the posting names: shown in a role or project (60%) and listed in the skills section (40%).",
    ),
    "title_alignment": (
        "Title alignment",
        "How closely your most recent and past job titles, and your summary, match the posting's title.",
    ),
    "experience_relevance": (
        "Experience relevance",
        "Your years of experience against the posting's range, whether recent roles are this kind of role, and "
        "whether recent roles use the required skills.",
    ),
    "achievement_quality": (
        "Achievement quality",
        "Experience bullets that state an outcome (55%), open with a strong verb (30%) and stay readable (15%).",
    ),
    "readability_format": (
        "Readability",
        "Penalties for very long bullets, passive phrasing, walls of text, first-person pronouns and an unusual length.",
    ),
    "section_completeness": (
        "Section completeness",
        "Email, phone, summary, skills, experience, education and (for software roles) a profile link.",
    ),
    "parse_risk": (
        "Parsing safety",
        "How safely an ATS can read the document (higher is safer): contact details, unusual symbols, tables, "
        "empty entries, missing dates.",
    ),
}

_TOKEN_RE = re.compile(r"[a-z][a-z0-9+#]*(?:-[a-z0-9]+)*")
_WEAK_FIRST = frozenset("worked helped assisted involved did made wrote handled used responsible was participated".split())
_PASSIVE_RE = re.compile(r"\b(?:was|were|been|being)\s+\w+ed\b|\bresponsible for\b", re.IGNORECASE)
_PRONOUN_RE = re.compile(r"(?:^|[\s(])(?:I|my|me|I'm|I've)(?=[\s,.;:)])")
_ODD_CHAR_RE = re.compile("[-�─-╿■-◿]")
_TABLE_LINE_RE = re.compile(r"\S\s\|\s\S.*\s\|\s\S")
_CONTACT_LINE_RE = re.compile(r"@|https?://|linkedin|github|\+?\d[\d\s-]{7,}\d", re.IGNORECASE)
_DEGREE_RE = re.compile(r"\b(bachelor|master|ph\.?d|doctorate|b\.?\s?tech|m\.?\s?tech|b\.?e|b\.?sc?|m\.?sc?|mba|degree|diploma|b\.?s|m\.?s)\b", re.IGNORECASE)

#: Title score ceiling when the titles provably name different kinds of role (frontend vs backend...).
DIFFERENT_ROLE_CAP = 35.0
MIN_BULLET_WORDS = 8
MAX_BULLET_WORDS = 32
LONG_BULLET_WORDS = 35
WALL_OF_TEXT_WORDS = 120
SHORT_RESUME_WORDS = 250
LONG_RESUME_WORDS = 1100


def methodology() -> Methodology:
    return Methodology(
        version=METHODOLOGY_VERSION,
        categories=[
            MethodologyCategory(key=key, label=label, weight=ATS_WEIGHTS[key], description=description)
            for key, (label, description) in CATEGORIES.items()
        ],
        weight_bounds=WEIGHT_BOUNDS,
        notes=[
            "Every category is computed by fixed rules from your resume and the job description; no model decides the score.",
            "Categories that do not apply to a posting (for example no stated years of experience) are left out and "
            "their weight is shared by the others.",
            "Custom weights are accepted between 0 and 0.5 each and re-normalised to sum to 1.",
        ],
    )


def resolve_weights(overrides: dict[str, float] | None) -> dict[str, float]:
    """Default weights, or the overrides (bounded, re-normalised). Unknown keys are refused."""
    if not overrides:
        return dict(ATS_WEIGHTS)
    unknown = sorted(set(overrides) - set(ATS_WEIGHTS))
    if unknown:
        raise ValidationFailed(
            f"Unknown scoring categories: {', '.join(unknown)}.", code="unknown_weight", details={"unknown": unknown}
        )
    merged = dict(ATS_WEIGHTS)
    for key, value in overrides.items():
        number = float(value)
        if not (WEIGHT_BOUNDS["min"] <= number <= WEIGHT_BOUNDS["max"]):
            raise ValidationFailed(
                f"The weight for {key} must be between {WEIGHT_BOUNDS['min']} and {WEIGHT_BOUNDS['max']}.",
                code="weight_out_of_bounds",
                details={"key": key, "value": number},
            )
        merged[key] = number
    total = sum(merged.values())
    if total <= 0:
        raise ValidationFailed("At least one scoring category needs a weight above 0.", code="weights_all_zero")
    return {key: round(value / total, 4) for key, value in merged.items()}


# --------------------------------------------------------------------------- resume digest


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _mentions(text_lower: str, text_skills: set[str], skill: str) -> bool:
    if skill.lower() in text_skills:
        return True
    return bool(re.search(rf"(?<![a-z0-9+#]){re.escape(skill.lower())}(?![a-z0-9+#])", text_lower))


@dataclass
class Digest:
    """Everything the categories read, computed once per resume version."""

    view: rec.ResumeView
    raw_text: str
    listed: set[str]
    experience_lower: str
    experience_skills: set[str]
    project_lower: str
    project_skills: set[str]
    stems: set[str]
    bullets: list[tuple[int, str]]
    parse_failed: bool = False

    def presence(self, skill: str) -> dict[str, bool]:
        key = skill.lower()
        return {
            "skills": key in self.listed,
            "experience": _mentions(self.experience_lower, self.experience_skills, skill),
            "projects": _mentions(self.project_lower, self.project_skills, skill),
            "anywhere": _mentions(self.view.text_lower, self.view.text_skills, skill),
        }

    def where(self, skill: str) -> list[str]:
        found = self.presence(skill)
        places = [label for label, key in (("skills section", "skills"), ("experience", "experience"), ("projects", "projects")) if found[key]]
        if not places and found["anywhere"]:
            places = ["resume text"]
        return places


def digest(parsed: dict[str, Any] | None, raw_text: str | None, *, profile_years: float | None, parse_failed: bool = False) -> Digest:
    parsed = parsed if isinstance(parsed, dict) else {}
    view = rec.build_view(parsed, profile_years=profile_years, raw_text=raw_text)

    def entry_text(entries: list[dict[str, Any]], *keys: str) -> str:
        parts: list[str] = []
        for entry in entries:
            parts += [str(entry.get(k) or "") for k in keys]
            parts += [str(t) for t in entry.get("technologies") or []]
        return "\n".join(p for p in parts if p)

    experience_text = entry_text(view.experience, "title", "company", "description")
    project_text = entry_text(view.projects, "name", "description")
    bullets = [(index, bullet) for index, entry in enumerate(view.experience) for bullet in rec.split_bullets(entry.get("description"))]
    return Digest(
        view=view,
        raw_text=raw_text or "",
        listed={s.lower() for s in view.skills},
        experience_lower=experience_text.lower(),
        experience_skills={s.lower() for s in extract_skills(experience_text)},
        project_lower=project_text.lower(),
        project_skills={s.lower() for s in extract_skills(project_text)},
        stems={_stem(t) for t in _TOKEN_RE.findall(view.text_lower)},
        bullets=bullets,
        parse_failed=parse_failed or not parsed,
    )


def _keyword_found(d: Digest, keyword: str) -> bool:
    words = [_stem(t) for t in _TOKEN_RE.findall(keyword.lower())]
    return bool(words) and all(w in d.stems for w in words)


def _title_found(d: Digest, title: str) -> bool:
    return rec._title_mentioned(title, d.view.text)


def _join(items: list[str], limit: int = 6) -> str:
    shown = items[:limit]
    more = len(items) - len(shown)
    return ", ".join(shown) + (f" and {more} more" if more > 0 else "")


# --------------------------------------------------------------------------- categories


@dataclass
class Category:
    score: float | None
    evidence: list[str] = field(default_factory=list)


@dataclass
class KeywordReport:
    category: Category
    matched: list[KeywordHit]
    missing: list[KeywordMiss]


def keyword_coverage(d: Digest, jd: StructuredJD, *, profile_skills: set[str], profile_text: str = "") -> KeywordReport:
    terms: list[tuple[str, str, bool | None, int]] = []
    for skill in jd.required_skills:
        terms.append((skill, "skill", True, 2))
    for skill in jd.preferred_skills:
        terms.append((skill, "skill", False, 1))
    skill_keys = {s.lower() for s in jd.required_skills + jd.preferred_skills}
    for keyword in jd.keywords:
        if keyword.lower() not in skill_keys:
            terms.append((keyword, "keyword", None, 1))
    if jd.title:
        terms.append((jd.title, "title", None, 2))
    if not terms:
        return KeywordReport(Category(None, ["The posting names no skills or keywords to match."]), [], [])

    profile_lower = (profile_text or "").lower()
    profile_stems = {_stem(t) for t in _TOKEN_RE.findall(profile_lower)}
    matched: list[KeywordHit] = []
    missing: list[KeywordMiss] = []
    got = total = 0
    for term, kind, required, weight in terms:
        total += weight
        if kind == "skill":
            found = d.presence(term)["anywhere"]
            where = d.where(term)
        elif kind == "keyword":
            found = _keyword_found(d, term)
            where = ["resume text"] if found else []
        else:
            found = _title_found(d, term)
            where = ["title or summary"] if found else []
        if found:
            got += weight
            matched.append(KeywordHit(keyword=term, kind=kind, required=required, where=where))  # type: ignore[arg-type]
            continue
        evidenced = False
        fits: str | None = None
        if kind == "skill":
            if term.lower() in profile_skills:
                evidenced, fits = True, "Skills section (your profile lists it)"
            else:
                category = skill_category(normalize_skill(term))
                related = [
                    s for s in d.view.skills if category != "other" and skill_category(s) == category and s.lower() != term.lower()
                ]
                fits = f"Skills section, if you have used it (related on your resume: {_join(related, 3)})" if related else None
        elif kind == "keyword":
            words = [_stem(t) for t in _TOKEN_RE.findall(term.lower())]
            if words and all(w in profile_stems for w in words):
                evidenced, fits = True, "Summary or the role where you did this (your profile mentions it)"
        else:
            fits = "Summary (name the role you are applying for)"
            evidenced = True
        missing.append(
            KeywordMiss(keyword=term, kind=kind, required=required, where_it_fits=fits, evidenced=evidenced)  # type: ignore[arg-type]
        )
    score = 100.0 * got / total
    evidence = [f"{len(matched)} of {len(terms)} posting keywords found ({round(score)}% after weighting)"]
    missing_required = [m.keyword for m in missing if m.kind == "skill" and m.required]
    if missing_required:
        evidence.append(f"Missing required skills: {_join(missing_required)}")
    missing_terms = [m.keyword for m in missing if m.kind == "keyword"]
    if missing_terms:
        evidence.append(f"Missing terms: {_join(missing_terms)}")
    if any(m.kind == "title" for m in missing):
        evidence.append(f'The title "{jd.title}" does not appear on the resume')
    return KeywordReport(Category(score, evidence), matched, missing)


def _years_credit(years: float | None, jd: StructuredJD) -> tuple[float, str] | None:
    if jd.years_min is None:
        return None
    wanted = f"{rec._format_years(jd.years_min)}" + (f"-{rec._format_years(jd.years_max)}" if jd.years_max else "+")
    if years is None:
        return 0.4, f"The posting asks for {wanted} years; the resume does not state your total experience"
    if years >= jd.years_min:
        if jd.years_max is not None and years > jd.years_max + 3:
            return 0.85, f"{rec._format_years(years)} years of experience, above the posting's {wanted} range"
        return 1.0, f"{rec._format_years(years)} years of experience meets the posting's {wanted}"
    if years >= jd.years_min - 1:
        return 0.7, f"{rec._format_years(years)} years of experience, just under the posting's {wanted}"
    return max(0.0, 0.8 * years / jd.years_min), f"{rec._format_years(years)} years of experience vs {wanted} asked"


def _has_degree(d: Digest) -> bool:
    for entry in d.view.education:
        text = " ".join(str(entry.get(k) or "") for k in ("degree", "field", "institution"))
        if text.strip():
            return True
    return bool(_DEGREE_RE.search(d.raw_text or ""))


def required_vs_preferred(d: Digest, jd: StructuredJD) -> Category:
    got = total = 0.0
    evidence: list[str] = []
    if jd.required_skills:
        present = [s for s in jd.required_skills if d.presence(s)["anywhere"]]
        missing = [s for s in jd.required_skills if s not in present]
        got += 3 * len(present)
        total += 3 * len(jd.required_skills)
        evidence.append(f"Required skills: {len(present)} of {len(jd.required_skills)} on the resume")
        if missing:
            evidence.append(f"Required but missing: {_join(missing)}")
    years = _years_credit(d.view.years, jd)
    if years is not None:
        credit, text = years
        got += 3 * credit
        total += 3
        evidence.append(text)
    if jd.degree_required:
        has = _has_degree(d)
        got += 2 if has else 0
        total += 2
        evidence.append("Degree requirement: education section present" if has else "The posting requires a degree; no education is listed")
    if jd.preferred_skills:
        present = [s for s in jd.preferred_skills if d.presence(s)["anywhere"]]
        got += len(present)
        total += len(jd.preferred_skills)
        evidence.append(f"Preferred skills: {len(present)} of {len(jd.preferred_skills)} on the resume")
    if total == 0:
        return Category(None, ["The posting states no required or preferred skills, years or degree."])
    return Category(100.0 * got / total, evidence)


def technical_skills(d: Digest, jd: StructuredJD) -> Category:
    skills = [(s, 2) for s in jd.required_skills] + [(s, 1) for s in jd.preferred_skills]
    if not skills:
        return Category(None, ["The posting names no technical skills."])
    got = total = 0.0
    shown: list[str] = []
    listed_only: list[str] = []
    unlisted: list[str] = []
    absent: list[str] = []
    for skill, weight in skills:
        found = d.presence(skill)
        used = found["experience"] or found["projects"]
        credit = (0.6 if used else 0.0) + (0.4 if found["skills"] else 0.0)
        if credit == 0 and found["anywhere"]:
            credit = 0.5
        got += weight * credit
        total += weight
        if used and found["skills"]:
            shown.append(skill)
        elif found["skills"]:
            listed_only.append(skill)
        elif used or found["anywhere"]:
            unlisted.append(skill)
        else:
            absent.append(skill)
    evidence = []
    if shown:
        evidence.append(f"Listed and shown in a role or project: {_join(shown)}")
    if listed_only:
        evidence.append(f"Listed in skills but not shown in any role or project: {_join(listed_only)}")
    if unlisted:
        evidence.append(f"Used in your experience but not listed in the skills section: {_join(unlisted)}")
    if absent:
        evidence.append(f"Not on the resume: {_join(absent)}")
    return Category(100.0 * got / total, evidence)


def title_alignment(d: Digest, jd: StructuredJD) -> Category:
    if not jd.title:
        return Category(None, ["The posting has no recognisable job title."])
    found = rec.most_recent_entry(d.view.experience)
    recent = str(found[1].get("title") or "").strip() if found else ""
    titles = [str(e.get("title") or "").strip() for e in d.view.experience if str(e.get("title") or "").strip()]
    evidence: list[str] = []
    score = 0.0
    if recent:
        score = float(match_scoring.score_title(recent, [jd.title]))
        if rec.role_matches(recent, [jd.title]):
            score = max(score, 90.0)
        if rec.different_role(recent, [jd.title]):
            # "DevOps Engineer" vs "Backend Engineer": the shared "Engineer" is not alignment.
            score = min(score, DIFFERENT_ROLE_CAP)
        evidence.append(f'Most recent title "{recent}" vs "{jd.title}": {round(score)}/100')
        if rec.different_role(recent, [jd.title]):
            evidence.append("Your most recent title names a different kind of role")
    past = [t for t in titles if t != recent and rec.role_matches(t, [jd.title])]
    if past:
        score = max(score, 70.0)
        evidence.append(f'An earlier title matches: "{past[0]}"')
    if d.view.summary and rec._title_mentioned(jd.title, d.view.summary):
        score = min(100.0, max(score, 60.0) + 10.0)
        evidence.append("Your summary names this role")
    elif d.view.summary:
        evidence.append("Your summary does not name this role")
    if not titles:
        evidence.append("No job titles on the resume")
    return Category(score, evidence)


def experience_relevance(d: Digest, jd: StructuredJD) -> Category:
    parts: list[float] = []
    evidence: list[str] = []
    years = _years_credit(d.view.years, jd)
    if years is not None:
        parts.append(100.0 * years[0])
        evidence.append(years[1])
    recent = d.view.experience[:3]
    if recent or d.view.projects:
        role_part: float | None = None
        if jd.title and recent:
            relevant = [
                e for e in recent
                if rec.role_matches(str(e.get("title") or ""), [jd.title])
                or (
                    match_scoring.score_title(str(e.get("title") or ""), [jd.title]) >= 60
                    and not rec.different_role(str(e.get("title") or ""), [jd.title])
                )
            ]
            role_part = 100.0 * len(relevant) / len(recent)
            evidence.append(f"{len(relevant)} of your {len(recent)} most recent roles are this kind of role")
        skills_part: float | None = None
        if jd.required_skills:
            recent_text = "\n".join(
                " ".join([str(e.get("description") or ""), *[str(t) for t in e.get("technologies") or []]]) for e in d.view.experience[:2]
            )
            if not recent_text.strip():
                recent_text = "\n".join(
                    " ".join([str(p.get("description") or ""), *[str(t) for t in p.get("technologies") or []]]) for p in d.view.projects
                )
            lower = recent_text.lower()
            found_skills = {s.lower() for s in extract_skills(recent_text)}
            used = [s for s in jd.required_skills if _mentions(lower, found_skills, s)]
            skills_part = 100.0 * len(used) / len(jd.required_skills)
            evidence.append(f"Recent roles use {len(used)} of the {len(jd.required_skills)} required skills")
        if role_part is not None and skills_part is not None:
            parts.append(0.6 * role_part + 0.4 * skills_part)
        elif role_part is not None:
            parts.append(role_part)
        elif skills_part is not None:
            parts.append(skills_part)
    elif years is None:
        return Category(None, ["No experience on the resume and no years asked for."])
    else:
        parts.append(0.0)
        evidence.append("No experience entries on the resume")
    if not parts:
        return Category(None, ["Nothing to compare: the posting states no years and has no title or skills."])
    return Category(sum(parts) / len(parts), evidence)


def achievement_quality(d: Digest) -> tuple[Category, list[WeakItem]]:
    bullets = d.bullets
    if not bullets:
        if not d.view.experience:
            return Category(None, ["No experience entries to judge."]), []
        return Category(0.0, ["Your experience entries have no bullet points."]), [
            WeakItem(path=f"experience[{i}].description", text=rec._entry_label(e, i), reason="no bullet points")
            for i, e in enumerate(d.view.experience)
        ]
    outcome = [b for _, b in bullets if rec.has_outcome(b)]
    strong = [b for _, b in bullets if (b.split()[0].lower().strip(",.;:") if b.split() else "") not in _WEAK_FIRST]
    sized = [b for _, b in bullets if MIN_BULLET_WORDS <= len(b.split()) <= MAX_BULLET_WORDS]
    n = len(bullets)
    score = 100.0 * (0.55 * len(outcome) / n + 0.30 * len(strong) / n + 0.15 * len(sized) / n)
    weak: list[WeakItem] = []
    for index, bullet in bullets:
        first = bullet.split()[0].lower().strip(",.;:") if bullet.split() else ""
        reasons = []
        if not rec.has_outcome(bullet):
            reasons.append("no measurable outcome")
        if first in _WEAK_FIRST:
            reasons.append(f'opens with a weak verb ("{bullet.split()[0]}")')
        if len(bullet.split()) > MAX_BULLET_WORDS:
            reasons.append("too long to scan")
        if reasons:
            weak.append(WeakItem(path=f"experience[{index}].description", text=bullet, reason="; ".join(reasons)))
    evidence = [
        f"{len(outcome)} of {n} bullets state an outcome",
        f"{len(strong)} of {n} open with a strong verb",
        f"{len(sized)} of {n} are {MIN_BULLET_WORDS}-{MAX_BULLET_WORDS} words",
    ]
    return Category(score, evidence), weak[:25]


def readability_format(d: Digest) -> Category:
    score = 100.0
    evidence: list[str] = []
    long_bullets = [b for _, b in d.bullets if len(b.split()) > LONG_BULLET_WORDS]
    if long_bullets:
        score -= min(20, 5 * len(long_bullets))
        evidence.append(f"{len(long_bullets)} bullet(s) over {LONG_BULLET_WORDS} words")
    passive = sum(len(_PASSIVE_RE.findall(b)) for _, b in d.bullets)
    if passive:
        score -= min(15, 3 * passive)
        evidence.append(f"{passive} passive or duty-style phrase(s) (\"was responsible for\", \"were handled\")")
    walls = 0
    for entry in d.view.experience:
        description = str(entry.get("description") or "")
        if len(description.split()) > WALL_OF_TEXT_WORDS and len(rec.split_bullets(description)) < 3:
            walls += 1
    if walls:
        score -= min(20, 10 * walls)
        evidence.append(f"{walls} role(s) written as one long paragraph instead of bullets")
    if d.view.summary and len(d.view.summary.split()) > 90:
        score -= 8
        evidence.append(f"The summary is {len(d.view.summary.split())} words; two to four lines read best")
    words = d.view.word_count
    if words < SHORT_RESUME_WORDS:
        score -= 15
        evidence.append(f"About {words} words: too little for a reviewer to go on")
    elif words > LONG_RESUME_WORDS and (d.view.years or 0) < 8:
        score -= 10
        evidence.append(f"About {words} words: long for your experience")
    pronouns = sum(len(_PRONOUN_RE.findall(b)) for _, b in d.bullets) + len(_PRONOUN_RE.findall(d.view.summary or ""))
    if pronouns:
        score -= min(10, 2 * pronouns)
        evidence.append(f"{pronouns} first-person pronoun(s); resumes usually leave them out")
    if not evidence:
        evidence.append("Concise bullets, active phrasing and a sensible length")
    return Category(max(0.0, score), evidence)


def _is_software(jd: StructuredJD) -> bool:
    return rec._is_software_title(jd.title) or bool(jd.required_skills)


def section_completeness(d: Digest, jd: StructuredJD) -> Category:
    junior = d.view.years is not None and d.view.years < 2
    checks: list[tuple[str, bool]] = [
        ("email", bool(d.view.email)),
        ("phone", bool(d.view.phone)),
        ("summary", bool(d.view.summary)),
        ("skills", bool(d.view.skills)),
        ("experience" if not junior or d.view.experience else "experience or projects", bool(d.view.experience) or (junior and bool(d.view.projects))),
        ("education", bool(d.view.education)),
    ]
    if _is_software(jd):
        checks.append(("a LinkedIn, GitHub or portfolio link", any(d.view.links.get(k) for k in ("linkedin", "github", "portfolio"))))
    present = [name for name, ok in checks if ok]
    missing = [name for name, ok in checks if not ok]
    evidence = [f"Present: {_join(present, 8)}" if present else "No standard sections found"]
    if missing:
        evidence.append(f"Missing: {_join(missing, 8)}")
    return Category(100.0 * len(present) / len(checks), evidence)


def parse_risk(d: Digest) -> tuple[Category, list[ParseRisk]]:
    risks: list[tuple[int, ParseRisk]] = []
    if d.parse_failed:
        risks.append((40, ParseRisk(code="parse_failed", message="The resume could not be read into sections; an ATS may struggle too.", severity="high")))
    if not d.view.email:
        risks.append((25, ParseRisk(code="no_email", message="No email address was found.", severity="high")))
    if not d.view.phone:
        risks.append((10, ParseRisk(code="no_phone", message="No phone number was found.", severity="medium")))
    if not str(d.view.parsed.get("name") or "").strip():
        risks.append((10, ParseRisk(code="no_name", message="No name was found at the top of the resume.", severity="medium")))
    odd = len(_ODD_CHAR_RE.findall(d.raw_text or ""))
    if odd > 5:
        risks.append((10, ParseRisk(code="odd_characters", message=f"{odd} unusual symbols (icons, private-use glyphs) that some ATS drop or garble.", severity="low")))
    # "City | phone | email" header lines use pipes too; they are not tables.
    table_lines = sum(
        1 for line in (d.raw_text or "").splitlines() if _TABLE_LINE_RE.search(line) and not _CONTACT_LINE_RE.search(line)
    )
    if table_lines >= 2:
        risks.append((10, ParseRisk(code="tables", message="Tables detected; some ATS read tables cell by cell and scramble the order.", severity="medium")))
    empty = [i for i, e in enumerate(d.view.experience) if not str(e.get("title") or "").strip() and not str(e.get("company") or "").strip()]
    if empty:
        risks.append((10, ParseRisk(code="empty_entries", message=f"{len(empty)} experience entr{'y has' if len(empty) == 1 else 'ies have'} no title or company.", severity="medium")))
    undated = [i for i, e in enumerate(d.view.experience) if not str(e.get("start") or "").strip() or not str(e.get("end") or "").strip()]
    if undated:
        risks.append((10, ParseRisk(code="missing_dates", message=f"{len(undated)} role(s) without a start or end date; ATS use dates to work out experience.", severity="medium")))
    score = max(0.0, 100.0 - sum(points for points, _ in risks))
    evidence = [risk.message for _, risk in risks] or ["No parsing risks found in the text JobPilot extracted"]
    return Category(score, evidence), [risk for _, risk in risks]


# --------------------------------------------------------------------------- overall


@dataclass
class ScoreResult:
    overall: int
    categories: list[CategoryScore]
    matched: list[KeywordHit]
    missing: list[KeywordMiss]
    weak_items: list[WeakItem]
    parse_risks: list[ParseRisk]
    weights: dict[str, float]


def score_resume(
    parsed: dict[str, Any] | None,
    raw_text: str | None,
    jd: StructuredJD,
    *,
    profile_years: float | None = None,
    profile_skills: set[str] | None = None,
    profile_text: str = "",
    weights: dict[str, float] | None = None,
    parse_failed: bool = False,
) -> ScoreResult:
    """The estimated compatibility of ``parsed`` with ``jd`` - pure: no DB, no model."""
    weights = weights or dict(ATS_WEIGHTS)
    d = digest(parsed, raw_text, profile_years=profile_years, parse_failed=parse_failed)
    keywords = keyword_coverage(d, jd, profile_skills={s.lower() for s in (profile_skills or set())}, profile_text=profile_text)
    achievements, weak = achievement_quality(d)
    parsing, risks = parse_risk(d)
    results: dict[str, Category] = {
        "keyword_coverage": keywords.category,
        "required_vs_preferred": required_vs_preferred(d, jd),
        "technical_skills": technical_skills(d, jd),
        "title_alignment": title_alignment(d, jd),
        "experience_relevance": experience_relevance(d, jd),
        "achievement_quality": achievements,
        "readability_format": readability_format(d),
        "section_completeness": section_completeness(d, jd),
        "parse_risk": parsing,
    }
    categories: list[CategoryScore] = []
    weighted = used = 0.0
    for key, (label, _) in CATEGORIES.items():
        result = results[key]
        applicable = result.score is not None
        if applicable:
            weighted += weights[key] * float(result.score)  # type: ignore[arg-type]
            used += weights[key]
        categories.append(
            CategoryScore(
                key=key,
                label=label,
                score=round(result.score) if applicable else None,  # type: ignore[arg-type]
                weight=weights[key],
                applicable=applicable,
                evidence=result.evidence,
            )
        )
    overall = round(weighted / used) if used > 0 else 0
    return ScoreResult(
        overall=max(0, min(100, int(overall))),
        categories=categories,
        matched=keywords.matched,
        missing=keywords.missing,
        weak_items=weak,
        parse_risks=risks,
        weights=weights,
    )


__all__ = [
    "ATS_WEIGHTS",
    "CATEGORIES",
    "METHODOLOGY_VERSION",
    "WEIGHT_BOUNDS",
    "ScoreResult",
    "digest",
    "methodology",
    "resolve_weights",
    "score_resume",
]
