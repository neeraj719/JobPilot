"""Suggestions against one job description, and applying them to ``parsed_data``.

Built from the scoring digest and guarded by the same checks the resume module uses
(``resumes.apply``: ``bullet_problem``, ``summary_problem``, ``strip_filler``,
``build_factual_summary``). Nothing here invents a fact:

``ADD_SKILL``
    A skill the posting names that the resume's skills section lacks. **Safe** when the resume
    text already shows it (a role or project mentions it) or the user's profile lists it -
    both are facts the candidate gave. Otherwise it needs the user's confirmation
    ("I have used Kubernetes") and is never part of "Apply all safe".
``REPLACE_SUMMARY``
    Only when the summary is missing or thin: a summary built from resume/profile facts
    (most recent title, years, the candidate's own skills that the posting asks for, the
    posting's title as the goal). A full summary the user wrote is never replaced; it gets
    an ``ADD_KEYWORD_CONTEXT`` for the user to edit instead.
``REPLACE_BULLET``
    A weak bullet (weak opening verb) rephrased deterministically (``tidy_bullet``); safe only
    when ``bullet_problem`` finds nothing. A bullet with a strong verb but no outcome gets a
    suggestion with no ``after``: the outcome is the candidate's to type (the background model
    polish may propose a rewrite that keeps every fact).
``REORDER_SECTION``
    Skills (and projects) the posting asks for moved first. A permutation - always safe.
``ADD_KEYWORD_CONTEXT``
    A posting term the resume lacks but the candidate's profile mentions, or a summary that
    does not name the role: the user writes the sentence (edit manually).
``MANUAL``
    Everything that needs the candidate's own work (years, title, missing sections, contact).
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field, replace
from typing import Any

from app.modules.ai import tasks as ai_tasks
from app.modules.ai.skills import extract_skills, normalize_skill, normalize_skills
from app.modules.ats.schemas import StructuredJD
from app.modules.ats.scoring import Digest, ScoreResult, digest, score_resume
from app.modules.resumes import apply as resume_apply
from app.modules.resumes import recommendations as rec

MAX_BULLET_SUGGESTIONS = 6
MAX_REQUIRED_SKILLS = 8
MAX_PREFERRED_SKILLS = 4
MAX_KEYWORD_CONTEXT = 3

_EXPERIENCE_PATH = re.compile(r"^experience\[(\d+)\]\.description$")


@dataclass
class Draft:
    kind: str
    title: str
    rationale: str
    target_path: str | None = None
    before: str | None = None
    after: str | None = None
    safe: bool = False
    requires_confirmation: bool = False
    confirmation_label: str | None = None
    estimated_gain: float = 0.0
    checks: dict[str, Any] = field(default_factory=dict)
    rank: int = 50


# --------------------------------------------------------------------------- facts


def make_facts(parsed: dict[str, Any], raw_text: str, inputs: rec.MatchInputs) -> Any:
    """``resumes.apply._Facts`` for the guards (the resume + the user's verified profile)."""
    return resume_apply._Facts(parsed=copy.deepcopy(parsed or {}), raw_text=raw_text or "", inputs=inputs)


def _entry_label(entry: dict[str, Any], index: int) -> str:
    return rec._entry_label(entry, index)


def _related_entry(d: Digest, skill: str) -> str | None:
    for index, entry in enumerate(d.view.experience):
        text = " ".join([str(entry.get("description") or ""), *[str(t) for t in entry.get("technologies") or []]])
        if skill.lower() in {s.lower() for s in extract_skills(text)}:
            return _entry_label(entry, index)
    for project in d.view.projects:
        text = " ".join([str(project.get("description") or ""), *[str(t) for t in project.get("technologies") or []]])
        if skill.lower() in {s.lower() for s in extract_skills(text)}:
            return f"project {project.get('name') or ''}".strip()
    return None


# --------------------------------------------------------------------------- reordering (pure)


def jd_skill_order(jd: StructuredJD) -> list[str]:
    return [s.lower() for s in normalize_skills(jd.required_skills + jd.preferred_skills)]


def reorder_skills(skills: list[str], jd: StructuredJD) -> list[str]:
    """The same skills, the posting's first (required, then preferred, in the posting's order)."""
    order = {key: i for i, key in enumerate(jd_skill_order(jd))}
    indexed = list(enumerate(skills))
    indexed.sort(key=lambda item: (order.get(normalize_skill(str(item[1])).lower(), len(order) + item[0]), item[0]))
    return [skill for _, skill in indexed]


def _project_relevance(project: dict[str, Any], wanted: set[str]) -> int:
    text = " ".join([str(project.get("name") or ""), str(project.get("description") or ""), *[str(t) for t in project.get("technologies") or []]])
    return len({s.lower() for s in extract_skills(text)} & wanted)


def reorder_projects(projects: list[Any], jd: StructuredJD) -> list[Any]:
    wanted = set(jd_skill_order(jd))
    indexed = list(enumerate(projects))
    indexed.sort(key=lambda item: (-_project_relevance(item[1], wanted) if isinstance(item[1], dict) else 0, item[0]))
    return [project for _, project in indexed]


# --------------------------------------------------------------------------- building


def _skill_drafts(d: Digest, jd: StructuredJD, profile_skills: set[str]) -> list[Draft]:
    drafts: list[Draft] = []
    for skills, required, limit in ((jd.required_skills, True, MAX_REQUIRED_SKILLS), (jd.preferred_skills, False, MAX_PREFERRED_SKILLS)):
        count = 0
        for skill in skills:
            if count >= limit:
                break
            canonical = normalize_skill(skill)
            if not canonical or canonical.lower() in d.listed:
                continue
            count += 1
            need = "required" if required else "listed as a plus"
            found = d.presence(canonical)
            where = _related_entry(d, canonical)
            if found["anywhere"]:
                evidence = [f"Mentioned in {where}" if where else "Mentioned in your resume text"]
                drafts.append(
                    Draft(
                        kind="ADD_SKILL",
                        title=f"List {canonical} in your skills",
                        rationale=(
                            f"The posting has {canonical} {need}. Your resume already shows it"
                            + (f" ({where})" if where else "")
                            + " but the skills section, which ATS filters read first, does not list it."
                        ),
                        target_path="skills",
                        after=canonical,
                        safe=True,
                        checks={"evidence": evidence, "required": required, "source": "resume"},
                        rank=10 if required else 30,
                    )
                )
            elif canonical.lower() in profile_skills:
                drafts.append(
                    Draft(
                        kind="ADD_SKILL",
                        title=f"Add {canonical} from your profile",
                        rationale=(
                            f"The posting has {canonical} {need}. Your JobPilot profile lists it as one of your skills, "
                            "but this resume does not mention it."
                        ),
                        target_path="skills",
                        after=canonical,
                        safe=True,
                        checks={"evidence": ["Listed in your profile skills"], "required": required, "source": "profile"},
                        rank=12 if required else 32,
                    )
                )
            else:
                drafts.append(
                    Draft(
                        kind="ADD_SKILL",
                        title=f"Add {canonical} only if you have used it",
                        rationale=(
                            f"The posting has {canonical} {need}, and nothing on your resume or profile shows it. Tick it only "
                            "if you have really worked with it - then also mention it in the role where you used it."
                        ),
                        target_path="skills",
                        after=canonical,
                        safe=False,
                        requires_confirmation=True,
                        confirmation_label=f"I have used {canonical}",
                        checks={"evidence": [], "required": required, "source": "confirmation"},
                        rank=60 if required else 70,
                    )
                )
    return drafts


def _summary_drafts(d: Digest, jd: StructuredJD, facts: Any) -> list[Draft]:
    current = (d.view.summary or "").strip()
    listed = {s.lower(): s for s in d.view.skills}
    hint = [listed[s.lower()] for s in jd.required_skills + jd.preferred_skills if s.lower() in listed]
    if not current or len(current.split()) < rec.SUMMARY_MIN_WORDS:
        goal = [jd.title] if jd.title else []
        jd_facts = replace(facts, inputs=replace(facts.inputs, desired_titles=goal + list(facts.inputs.desired_titles)))
        text = resume_apply.build_factual_summary(jd_facts, hint)
        if text and text != current:
            problem = resume_apply.summary_problem(text, jd_facts, check_skills=True)
            if problem is None:
                return [
                    Draft(
                        kind="REPLACE_SUMMARY",
                        title="Replace your summary" if current else "Add a summary",
                        rationale=(
                            ("Your summary is short" if current else "Your resume has no summary")
                            + "; this one is built only from your resume and profile: your most recent title, your years "
                            "of experience and your skills that the posting asks for"
                            + (f", with {jd.title} as the goal." if jd.title else ".")
                        ),
                        target_path="summary",
                        before=current or None,
                        after=text,
                        safe=True,
                        checks={"summary_problem": None, "evidence": hint[:3]},
                        rank=20,
                    )
                ]
    if current:
        missing: list[str] = []
        if jd.title and not rec._title_mentioned(jd.title, current):
            missing.append(f'the role ("{jd.title}")')
        absent = [s for s in hint[:3] if s.lower() not in {x.lower() for x in extract_skills(current)}]
        if absent:
            missing.append(", ".join(absent))
        if missing:
            return [
                Draft(
                    kind="ADD_KEYWORD_CONTEXT",
                    title="Name the role and your matching skills in your summary",
                    rationale=(
                        f"Your summary does not mention {' or '.join(missing)}. Reviewers and ATS read the summary first; "
                        "edit it in your own words (only what is true of you)."
                    ),
                    target_path="summary",
                    before=current,
                    after=None,
                    safe=False,
                    checks={"needs": "edit", "mention": missing},
                    rank=75,
                )
            ]
    return []


def _bullet_drafts(d: Digest, jd: StructuredJD, facts: Any) -> list[Draft]:
    wanted = set(jd_skill_order(jd))

    def relevance(index: int) -> tuple[int, int]:
        entry = d.view.experience[index]
        text = " ".join([str(entry.get("description") or ""), *[str(t) for t in entry.get("technologies") or []]])
        return (-len({s.lower() for s in extract_skills(text)} & wanted), index)

    drafts: list[Draft] = []
    for index in sorted(range(len(d.view.experience)), key=relevance):
        entry = d.view.experience[index]
        label = _entry_label(entry, index)
        for bullet in rec.split_bullets(entry.get("description")):
            if len(drafts) >= MAX_BULLET_SUGGESTIONS:
                return drafts
            if rec.has_outcome(bullet):
                continue
            path = f"experience[{index}].description"
            candidate = resume_apply.strip_filler(resume_apply.tidy_bullet(bullet), bullet) or ""
            changed = candidate and candidate.strip().rstrip(".") != bullet.strip().rstrip(".")
            if changed:
                problem = resume_apply.bullet_problem(candidate, bullet, facts)
                drafts.append(
                    Draft(
                        kind="REPLACE_BULLET",
                        title=f"Strengthen a bullet for {label}",
                        rationale=(
                            "Opens with a stronger verb and keeps every fact of the original. It still states no result: "
                            "edit it to add one if you can (time saved, users served, errors cut)."
                        ),
                        target_path=path,
                        before=bullet,
                        after=candidate,
                        safe=problem is None,
                        checks={"bullet_problem": problem, "method": "rules"},
                        rank=25 if problem is None else 65,
                    )
                )
            else:
                drafts.append(
                    Draft(
                        kind="REPLACE_BULLET",
                        title=f"Add the result to a bullet for {label}",
                        rationale=(
                            "This bullet says what you did but not what changed. Add the outcome in your own words - only "
                            "numbers you can stand behind."
                        ),
                        target_path=path,
                        before=bullet,
                        after=None,
                        safe=False,
                        checks={"needs": "outcome", "method": "rules"},
                        rank=80,
                    )
                )
    return drafts


def _reorder_drafts(d: Digest, jd: StructuredJD) -> list[Draft]:
    drafts: list[Draft] = []
    skills = [str(s) for s in d.view.parsed.get("skills") or []]
    if len(skills) >= 3:
        ordered = reorder_skills(skills, jd)
        if ordered != skills:
            drafts.append(
                Draft(
                    kind="REORDER_SECTION",
                    title="Put the posting's skills first",
                    rationale="Moves the skills this posting asks for to the front of your skills list. Nothing is added or removed.",
                    target_path="skills",
                    before=", ".join(skills),
                    after=", ".join(ordered),
                    safe=True,
                    checks={"permutation": True},
                    rank=40,
                )
            )
    projects = d.view.parsed.get("projects") if isinstance(d.view.parsed.get("projects"), list) else []
    if len(projects) >= 2:
        ordered_projects = reorder_projects(projects, jd)
        if ordered_projects != projects:
            names = lambda items: ", ".join(str((p or {}).get("name") or "Untitled") for p in items if isinstance(p, dict))  # noqa: E731
            drafts.append(
                Draft(
                    kind="REORDER_SECTION",
                    title="Lead with your most relevant project",
                    rationale="Orders your projects by how many of the posting's skills they use. Nothing is added or removed.",
                    target_path="projects",
                    before=names(projects),
                    after=names(ordered_projects),
                    safe=True,
                    checks={"permutation": True},
                    rank=45,
                )
            )
    return drafts


def _keyword_drafts(score: ScoreResult, summary: str | None) -> list[Draft]:
    drafts: list[Draft] = []
    evidenced = [m for m in score.missing if m.kind == "keyword" and m.evidenced][:MAX_KEYWORD_CONTEXT]
    for miss in evidenced:
        drafts.append(
            Draft(
                kind="ADD_KEYWORD_CONTEXT",
                title=f'Use "{miss.keyword}" where it describes your work',
                rationale=(
                    f'The posting uses "{miss.keyword}" and your profile mentions it, but this resume does not. Add it to the '
                    "summary or to the bullet where you did that work, in your own words."
                ),
                target_path="summary",
                before=(summary or "").strip() or None,
                after=None,
                safe=False,
                checks={"needs": "edit", "keyword": miss.keyword, "where_it_fits": miss.where_it_fits},
                rank=78,
            )
        )
    plain = [m.keyword for m in score.missing if m.kind == "keyword" and not m.evidenced]
    if plain:
        drafts.append(
            Draft(
                kind="MANUAL",
                title="Use the posting's own words where they are true",
                rationale=(
                    f"The posting uses terms your resume does not: {', '.join(plain[:8])}. ATS match exact words, so where "
                    "one truthfully describes your work, use it. Do not add terms for work you have not done."
                ),
                checks={"keywords": plain[:8]},
                rank=90,
            )
        )
    return drafts


def _manual_drafts(d: Digest, jd: StructuredJD, score: ScoreResult) -> list[Draft]:
    drafts: list[Draft] = []
    if jd.years_min is not None and (d.view.years is None or d.view.years < jd.years_min):
        stated = f"your resume states {rec._format_years(d.view.years)}" if d.view.years is not None else "your resume does not state your total"
        drafts.append(
            Draft(
                kind="MANUAL",
                title="Make all relevant experience visible",
                rationale=(
                    f"The posting asks for {rec._format_years(jd.years_min)}+ years and {stated}. Make sure every relevant "
                    "role (internships, freelance, contract work) is listed with its dates. Do not round up."
                ),
                checks={"years_min": jd.years_min, "years": d.view.years},
                rank=85,
            )
        )
    title = next((c for c in score.categories if c.key == "title_alignment"), None)
    if title and title.applicable and (title.score or 0) < 60 and jd.title:
        drafts.append(
            Draft(
                kind="MANUAL",
                title="Connect your title to this role",
                rationale=(
                    f'Your titles do not match "{jd.title}". Keep your real titles; name the target role in your summary and '
                    "lead with the work closest to it."
                ),
                rank=86,
            )
        )
    for risk in score.parse_risks:
        if risk.severity == "high" or risk.code in ("no_phone", "missing_dates", "tables"):
            drafts.append(Draft(kind="MANUAL", title=f"Fix: {risk.message}", rationale=risk.message, checks={"parse_risk": risk.code}, rank=88))
    if jd.degree_required and not d.view.education:
        drafts.append(
            Draft(
                kind="MANUAL",
                title="Add your education",
                rationale="The posting asks for a degree and your resume has no education section. Add it exactly as on your records.",
                rank=87,
            )
        )
    if not d.view.skills:
        drafts.append(
            Draft(kind="MANUAL", title="Add a skills section", rationale="Your resume has no skills section; ATS filters read it first.", rank=84)
        )
    return drafts


def build_drafts(
    parsed: dict[str, Any],
    raw_text: str,
    jd: StructuredJD,
    score: ScoreResult,
    *,
    facts: Any,
    profile_skills: set[str],
    profile_text: str = "",
    profile_years: float | None = None,
) -> list[Draft]:
    """Every suggestion for this resume against ``jd``, ranked, with its estimated gain."""
    d = digest(parsed, raw_text, profile_years=profile_years)
    drafts = [
        *_skill_drafts(d, jd, profile_skills),
        *_summary_drafts(d, jd, facts),
        *_bullet_drafts(d, jd, facts),
        *_reorder_drafts(d, jd),
        *_keyword_drafts(score, d.view.summary),
        *_manual_drafts(d, jd, score),
    ]
    for draft in drafts:
        if draft.kind in ("MANUAL", "ADD_KEYWORD_CONTEXT") or not draft.after:
            continue
        new_parsed, applied, _ = apply_to_parsed(parsed, [(draft, draft.after)], jd)
        if applied:
            rescored = score_resume(
                new_parsed, raw_text, jd, profile_years=profile_years, profile_skills=profile_skills,
                profile_text=profile_text, weights=score.weights,
            )
            draft.estimated_gain = round(max(0.0, float(rescored.overall - score.overall)), 1)
    drafts.sort(key=lambda dr: (dr.rank, -dr.estimated_gain))
    return drafts


# --------------------------------------------------------------------------- applying (pure)


def apply_to_parsed(parsed: dict[str, Any], items: list[tuple[Any, str | None]], jd: StructuredJD) -> tuple[dict[str, Any], list[Any], list[tuple[Any, str]]]:
    """Apply ``(suggestion, after_text)`` pairs to a deep copy of ``parsed``.

    ``suggestion`` is a :class:`Draft` or an ``OptimizationSuggestion`` row (same attribute names).
    Skills first, then text replacements, then reorders (computed on the result, so a skill just
    added is ordered too). Anything whose anchor text moved is skipped, never forced.
    """
    data = copy.deepcopy(parsed or {})
    applied: list[Any] = []
    skipped: list[tuple[Any, str]] = []
    order = {"ADD_SKILL": 0, "REPLACE_SUMMARY": 1, "REPLACE_BULLET": 1, "ADD_KEYWORD_CONTEXT": 1, "REORDER_SECTION": 2}
    kind_of = lambda s: str(getattr(s.kind, "value", s.kind))  # noqa: E731
    for item, after in sorted(items, key=lambda pair: order.get(kind_of(pair[0]), 9)):
        kind = kind_of(item)
        target = item.target_path or ""
        if kind == "ADD_SKILL":
            skills = [str(s) for s in data.get("skills") or []]
            skill = normalize_skill(str(after or item.after or ""))
            if not skill:
                skipped.append((item, "empty_skill"))
                continue
            if skill.lower() in {s.lower() for s in normalize_skills(skills)}:
                skipped.append((item, "already_listed"))
                continue
            data["skills"] = [*skills, skill]
        elif kind in ("REPLACE_SUMMARY",) or (kind == "ADD_KEYWORD_CONTEXT" and target == "summary"):
            current = str(data.get("summary") or "").strip()
            if item.before is not None and current != str(item.before).strip():
                skipped.append((item, "summary_changed"))
                continue
            if not after:
                skipped.append((item, "edit_required"))
                continue
            data["summary"] = after
        elif kind in ("REPLACE_BULLET", "ADD_KEYWORD_CONTEXT"):
            match = _EXPERIENCE_PATH.match(target)
            experience = data.get("experience") if isinstance(data.get("experience"), list) else []
            index = int(match.group(1)) if match else -1
            entry = experience[index] if 0 <= index < len(experience) else None
            description = str(entry.get("description") or "") if isinstance(entry, dict) else ""
            if not item.before or item.before not in description:
                skipped.append((item, "bullet_not_found"))
                continue
            if not after:
                skipped.append((item, "edit_required"))
                continue
            entry["description"] = description.replace(item.before, after, 1)  # type: ignore[index]
        elif kind == "REORDER_SECTION":
            if target == "skills":
                skills = [str(s) for s in data.get("skills") or []]
                data["skills"] = reorder_skills(skills, jd)
            elif target == "projects" and isinstance(data.get("projects"), list):
                data["projects"] = reorder_projects(data["projects"], jd)
            else:
                skipped.append((item, "unknown_section"))
                continue
        else:
            skipped.append((item, "not_applicable"))
            continue
        applied.append(item)
    return data, applied, skipped


def invented_numbers(text: str, facts: Any, original: str | None = None) -> set[str]:
    return ai_tasks.invented_numbers(text, *(([original] if original else []) + list(facts.number_sources())))


__all__ = [
    "Draft",
    "apply_to_parsed",
    "build_drafts",
    "invented_numbers",
    "make_facts",
    "reorder_projects",
    "reorder_skills",
]
