"""Field-level diff between two versions of structured resume data (plan §4.2).

Pure functions: no database. Entries are matched by identity (company + title, project
name, institution + degree, certification name) rather than by position, so moving a role
up does not read as "everything changed". Bullets are compared line by line, skills as
added/removed sets, so "+2 skills, 1 bullet changed" is something a user can act on.
"""
from __future__ import annotations

import difflib
import re
from typing import Any

from app.modules.ai.schemas import ParsedResume
from app.modules.resumes.recommendations import split_bullets
from app.modules.resumes.schemas import DiffField, DiffSummary, ResumeDiff

_SCALARS: tuple[tuple[str, str], ...] = (
    ("name", "Name"),
    ("headline", "Headline"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("location", "Location"),
    ("summary", "Summary"),
    ("total_experience_years", "Years of experience"),
)
_LINKS: tuple[tuple[str, str], ...] = (("linkedin", "LinkedIn"), ("github", "GitHub"), ("portfolio", "Portfolio"))

#: section -> (identity fields, scalar fields compared, bullet field, label, singular noun)
_ENTRY_SECTIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...], str | None, str, str]] = {
    "experience": (("company", "title"), ("title", "company", "start", "end", "location", "url"), "description", "Experience", "role"),
    "projects": (("name",), ("name", "url", "location"), "description", "Projects", "project"),
    "education": (("institution", "degree"), ("institution", "degree", "field", "start", "end"), None, "Education", "education entry"),
    "certifications": (("name",), ("name", "issuer", "year"), None, "Certifications", "certification"),
}
_TEXT_LISTS: tuple[tuple[str, str, str], ...] = (
    ("achievements", "Achievements", "achievement"),
    ("languages", "Languages", "language"),
)


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned or None
    return value


def _key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def normalise(data: dict[str, Any] | ParsedResume | None) -> dict[str, Any]:
    if isinstance(data, ParsedResume):
        return data.model_dump(mode="json")
    try:
        return ParsedResume.model_validate(data or {}).model_dump(mode="json")
    except Exception:  # noqa: BLE001 - a malformed old version still diffs as empty
        return ParsedResume().model_dump(mode="json")


def _entry_label(section: str, entry: dict[str, Any]) -> str:
    if section == "experience":
        title, company = _norm(entry.get("title")), _norm(entry.get("company"))
        return " at ".join(p for p in (title, company) if p) or "Role"
    if section == "education":
        return " - ".join(p for p in (_norm(entry.get("degree")), _norm(entry.get("institution"))) if p) or "Education"
    return _norm(entry.get("name")) or section.rstrip("s").title()


def _match_entries(
    before: list[dict[str, Any]], after: list[dict[str, Any]], identity: tuple[str, ...]
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """``(pairs (before_i, after_j), removed before_i, added after_j)``."""
    used: set[int] = set()
    pairs: list[tuple[int, int]] = []
    added: list[int] = []

    def ident(entry: dict[str, Any], fields: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_key(entry.get(f)) for f in fields)

    # 1. exact identity; 2. any one identity field equal (a renamed title at the same company);
    # 3. the same position, when both entries are otherwise unmatched.
    pending: list[int] = []
    for j, entry in enumerate(after):
        target = ident(entry, identity)
        match = next((i for i, b in enumerate(before) if i not in used and any(target) and ident(b, identity) == target), None)
        if match is None:
            pending.append(j)
            continue
        used.add(match)
        pairs.append((match, j))
    still: list[int] = []
    for j in pending:
        entry = after[j]
        match = None
        for field in identity:
            value = _key(entry.get(field))
            if not value:
                continue
            match = next((i for i, b in enumerate(before) if i not in used and _key(b.get(field)) == value), None)
            if match is not None:
                break
        if match is None:
            still.append(j)
            continue
        used.add(match)
        pairs.append((match, j))
    for j in still:
        if j < len(before) and j not in used and len(before) == len(after):
            used.add(j)
            pairs.append((j, j))
        else:
            added.append(j)
    removed = [i for i in range(len(before)) if i not in used]
    pairs.sort(key=lambda p: p[1])
    return pairs, removed, added


def _diff_lines(
    before: list[str], after: list[str], path: str, label: str, out: list[DiffField]
) -> tuple[int, int, int]:
    """Line-by-line diff of two text lists; returns ``(added, removed, changed)`` counts."""
    norm_b = [" ".join(x.split()) for x in before]
    norm_a = [" ".join(x.split()) for x in after]
    added = removed = changed = 0
    matcher = difflib.SequenceMatcher(a=[x.lower() for x in norm_b], b=[x.lower() for x in norm_a], autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            span = min(i2 - i1, j2 - j1)
            for k in range(span):
                if norm_b[i1 + k] == norm_a[j1 + k]:
                    continue
                out.append(DiffField(path=f"{path}[{j1 + k}]", label=label, before=norm_b[i1 + k], after=norm_a[j1 + k], kind="changed"))
                changed += 1
            for k in range(i1 + span, i2):
                out.append(DiffField(path=f"{path}[{k}]", label=label, before=norm_b[k], after=None, kind="removed"))
                removed += 1
            for k in range(j1 + span, j2):
                out.append(DiffField(path=f"{path}[{k}]", label=label, before=None, after=norm_a[k], kind="added"))
                added += 1
        elif tag == "delete":
            for k in range(i1, i2):
                out.append(DiffField(path=f"{path}[{k}]", label=label, before=norm_b[k], after=None, kind="removed"))
                removed += 1
        elif tag == "insert":
            for k in range(j1, j2):
                out.append(DiffField(path=f"{path}[{k}]", label=label, before=None, after=norm_a[k], kind="added"))
                added += 1
    return added, removed, changed


def _scalar(path: str, label: str, before: Any, after: Any, out: list[DiffField]) -> bool:
    b, a = _norm(before), _norm(after)
    if b == a or (isinstance(b, str) and isinstance(a, str) and b == a):
        return False
    if b in (None, "") and a not in (None, ""):
        kind = "added"
    elif a in (None, "") and b not in (None, ""):
        kind = "removed"
    else:
        kind = "changed"
    out.append(DiffField(path=path, label=label, before=b, after=a, kind=kind))  # type: ignore[arg-type]
    return True


def _plural(count: int, noun: str) -> str:
    if count == 1:
        return f"1 {noun}"
    if noun.endswith("y") and not noun.endswith("ey"):
        return f"{count} {noun[:-1]}ies"
    return f"{count} {noun}s"


def diff_parsed(
    before: dict[str, Any] | ParsedResume | None,
    after: dict[str, Any] | ParsedResume | None,
    *,
    before_label: str | None = None,
    after_label: str | None = None,
) -> ResumeDiff:
    """The field-level changes that turn ``before`` into ``after``."""
    b, a = normalise(before), normalise(after)
    fields: list[DiffField] = []
    words: list[str] = []

    changed_scalars: list[str] = []
    for key, label in _SCALARS:
        if _scalar(key, label, b.get(key), a.get(key), fields):
            changed_scalars.append(label.lower())
    links_changed = False
    for key, label in _LINKS:
        links_changed |= _scalar(f"links.{key}", label, (b.get("links") or {}).get(key), (a.get("links") or {}).get(key), fields)

    # Skills: sets (case-insensitive), in the order they appear.
    before_skills = {_key(s): str(s) for s in b.get("skills") or [] if _key(s)}
    after_skills = {_key(s): str(s) for s in a.get("skills") or [] if _key(s)}
    skills_added = [after_skills[k] for k in after_skills if k not in before_skills]
    skills_removed = [before_skills[k] for k in before_skills if k not in after_skills]
    for skill in skills_added:
        fields.append(DiffField(path="skills", label="Skills", before=None, after=skill, kind="added"))
    for skill in skills_removed:
        fields.append(DiffField(path="skills", label="Skills", before=skill, after=None, kind="removed"))
    if skills_added:
        words.append(f"+{_plural(len(skills_added), 'skill')}")
    if skills_removed:
        words.append(f"-{_plural(len(skills_removed), 'skill')}")

    bullets_added = bullets_removed = bullets_changed = 0
    for section, (identity, compared, bullet_field, section_label, noun) in _ENTRY_SECTIONS.items():
        before_entries = [e for e in b.get(section) or [] if isinstance(e, dict)]
        after_entries = [e for e in a.get(section) or [] if isinstance(e, dict)]
        pairs, removed, added = _match_entries(before_entries, after_entries, identity)
        for i in removed:
            label = f"{section_label} · {_entry_label(section, before_entries[i])}"
            fields.append(DiffField(path=f"{section}[{i}]", label=label, before=_entry_label(section, before_entries[i]), after=None, kind="removed"))
        for j in added:
            label = f"{section_label} · {_entry_label(section, after_entries[j])}"
            fields.append(DiffField(path=f"{section}[{j}]", label=label, before=None, after=_entry_label(section, after_entries[j]), kind="added"))
        if added:
            words.append(f"{_plural(len(added), noun)} added")
        if removed:
            words.append(f"{_plural(len(removed), noun)} removed")
        entry_edits = 0
        for i, j in pairs:
            old, new = before_entries[i], after_entries[j]
            label = f"{section_label} · {_entry_label(section, new)}"
            for field in compared:
                if _scalar(f"{section}[{j}].{field}", label, old.get(field), new.get(field), fields):
                    entry_edits += 1
            if bullet_field:
                ba, br, bc = _diff_lines(
                    split_bullets(old.get(bullet_field)), split_bullets(new.get(bullet_field)), f"{section}[{j}].bullets", label, fields
                )
                bullets_added, bullets_removed, bullets_changed = bullets_added + ba, bullets_removed + br, bullets_changed + bc
            old_tech = {_key(t) for t in old.get("technologies") or [] if _key(t)}
            new_tech = {_key(t): str(t) for t in new.get("technologies") or [] if _key(t)}
            for key, tech in new_tech.items():
                if key not in old_tech:
                    fields.append(DiffField(path=f"{section}[{j}].technologies", label=label, before=None, after=tech, kind="added"))
                    entry_edits += 1
            for tech in old.get("technologies") or []:
                if _key(tech) and _key(tech) not in new_tech:
                    fields.append(DiffField(path=f"{section}[{j}].technologies", label=label, before=str(tech), after=None, kind="removed"))
                    entry_edits += 1
        if entry_edits:
            words.append(f"{_plural(entry_edits, noun + ' detail')} edited")
        if [i for i, _ in pairs] != sorted(i for i, _ in pairs) and pairs:
            fields.append(DiffField(path=section, label=section_label, before="previous order", after="new order", kind="changed"))
            words.append(f"{section_label.lower()} reordered")

    if bullets_changed:
        words.append(f"{_plural(bullets_changed, 'bullet')} changed")
    if bullets_added:
        words.append(f"+{_plural(bullets_added, 'bullet')}")
    if bullets_removed:
        words.append(f"-{_plural(bullets_removed, 'bullet')}")

    for key, label, noun in _TEXT_LISTS:
        added_n, removed_n, changed_n = _diff_lines(
            [str(x) for x in b.get(key) or []], [str(x) for x in a.get(key) or []], key, label, fields
        )
        if added_n:
            words.append(f"+{_plural(added_n, noun)}")
        if removed_n:
            words.append(f"-{_plural(removed_n, noun)}")
        if changed_n:
            words.append(f"{_plural(changed_n, noun)} changed")

    if (b.get("section_order") or []) != (a.get("section_order") or []):
        # An empty order means "the template's default order".
        fields.append(
            DiffField(
                path="section_order",
                label="Section order",
                before=b.get("section_order") or "template default",
                after=a.get("section_order") or "template default",
                kind="changed",
            )
        )
        words.append("sections rearranged")

    if changed_scalars:
        words.append(", ".join(changed_scalars) + " edited")
    if links_changed:
        words.append("links edited")

    summary = DiffSummary(
        added=sum(1 for f in fields if f.kind == "added"),
        removed=sum(1 for f in fields if f.kind == "removed"),
        changed=sum(1 for f in fields if f.kind == "changed"),
    )
    return ResumeDiff(
        fields=fields,
        summary=summary,
        description=", ".join(words) if words else "No content changes",
        before_label=before_label,
        after_label=after_label,
    )


def content_summary(data: dict[str, Any] | None) -> str:
    """"12 skills · 2 roles · 1 project" — for a first version, which has nothing to diff against."""
    d = normalise(data)
    bits = []
    for key, noun in (("skills", "skill"), ("experience", "role"), ("projects", "project"), ("education", "education entry")):
        count = len(d.get(key) or [])
        if count:
            bits.append(_plural(count, noun))
    return " · ".join(bits) if bits else "No structured content"


__all__ = ["content_summary", "diff_parsed", "normalise"]
