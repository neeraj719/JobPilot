"""Ways to start a resume without uploading a PDF/DOCX.

* :func:`prefill_from_profile` — a ``ParsedResume`` from the user's master profile and job
  preferences (the verified facts), so "Create from profile" starts filled in;
* :func:`import_text` — pasted resume text through the same parse pipeline as uploads;
* :func:`import_linkedin` — a LinkedIn "Download your data" export (the ZIP, or the
  individual CSVs). Read in memory with the standard library: nothing is extracted to
  disk, member names are only compared, every member is size-capped, and there is no
  scraping and no LinkedIn login.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import uuid
import zipfile
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationFailed
from app.models.enums import ResumeChangeSource, ResumeKind
from app.models.profile import JobPreference, UserProfile
from app.models.resume import Resume
from app.modules.ai import tasks as ai_tasks
from app.modules.ai.schemas import ParsedResume
from app.modules.resumes import service

logger = logging.getLogger(__name__)

#: A LinkedIn export is a few hundred KB; its CSVs are each far below this.
MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_ZIP_MEMBERS = 5000
MAX_CSV_ROWS = 2000

LINKEDIN_FILES: frozenset[str] = frozenset(
    {
        "profile.csv",
        "positions.csv",
        "education.csv",
        "skills.csv",
        "certifications.csv",
        "projects.csv",
        "languages.csv",
        "email addresses.csv",
        "phonenumbers.csv",
        "honors.csv",
    }
)
#: A column each file's header row must contain (rows before it, like a "Notes:" preamble, are skipped).
_HEADER_HINT = {
    "profile.csv": "First Name",
    "positions.csv": "Company Name",
    "education.csv": "School Name",
    "skills.csv": "Name",
    "certifications.csv": "Name",
    "projects.csv": "Title",
    "languages.csv": "Name",
    "email addresses.csv": "Email Address",
    "phonenumbers.csv": "Number",
    "honors.csv": "Title",
}

_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
_URL_RE = re.compile(r"https?://[^\s,\]\[]+", re.IGNORECASE)


# --------------------------------------------------------------------------- helpers


def _s(value: Any) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = _s(item)
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return out


def normalise_date(value: Any) -> str | None:
    """``Mar 2023`` / ``03/2023`` / ``2023-03-01`` / ``2023`` -> ``2023-03`` / ``2023``."""
    text = _s(value)
    if not text:
        return None
    if m := re.match(r"^([A-Za-z]{3,9})\.?\s+(?:\d{1,2},\s*)?(\d{4})$", text):
        month = _MONTHS.get(m.group(1)[:3].lower())
        if month:
            return f"{m.group(2)}-{month:02d}"
    if m := re.match(r"^(\d{1,2})/(\d{4})$", text):
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    if m := re.match(r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?$", text):
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    if re.fullmatch(r"\d{4}", text):
        return text
    return text[:40]


# --------------------------------------------------------------------------- profile


def prefill_from_profile(db: Session, user_id: uuid.UUID) -> ParsedResume:
    """The user's verified facts as resume data. Nothing is derived or guessed."""
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    prefs = db.scalar(select(JobPreference).where(JobPreference.user_id == user_id))
    if profile is None:
        return ParsedResume()

    name = _s(profile.full_name) or _s(" ".join(p for p in (profile.first_name, profile.last_name) if p))
    location = ", ".join(p for p in (_s(profile.city), _s(profile.state), _s(profile.country)) if p) or None

    experience: list[dict[str, Any]] = []
    for entry in profile.previous_companies or []:
        if not isinstance(entry, dict):
            continue
        company, title = _s(entry.get("company")), _s(entry.get("title") or entry.get("designation"))
        if not (company or title):
            continue
        experience.append(
            {
                "company": company,
                "title": title,
                "start": _s(entry.get("start")),
                "end": _s(entry.get("end")),
                "description": (str(entry.get("description")).strip() or None) if entry.get("description") else None,
                "location": _s(entry.get("location")),
                "technologies": [str(t) for t in entry.get("technologies") or entry.get("tech") or [] if _s(t)],
            }
        )
    current_company, current_title = _s(profile.current_company), _s(profile.current_designation)
    if current_company or current_title:
        known = any(
            (e.get("company") or "").lower() == (current_company or "").lower()
            and (not current_title or (e.get("title") or "").lower() == current_title.lower())
            for e in experience
        )
        if not known:
            # The current role as stated on the profile; no dates are invented for it.
            experience.insert(0, {"company": current_company, "title": current_title, "end": "Present"})

    education = [
        {
            "institution": _s(e.get("institution") or e.get("school")),
            "degree": _s(e.get("degree")),
            "field": _s(e.get("field") or e.get("field_of_study")),
            "start": _s(e.get("start")),
            "end": _s(e.get("end")),
        }
        for e in profile.education or []
        if isinstance(e, dict) and (e.get("institution") or e.get("school") or e.get("degree"))
    ]
    projects = [
        {
            "name": _s(p.get("name") or p.get("title")),
            "description": (str(p.get("description")).strip() or None) if p.get("description") else None,
            "technologies": [str(t) for t in p.get("technologies") or p.get("tech") or [] if _s(t)],
            "url": _s(p.get("url")),
        }
        for p in profile.projects or []
        if isinstance(p, dict) and (p.get("name") or p.get("title") or p.get("description"))
    ]
    certifications = [
        {"name": _s(c.get("name")), "issuer": _s(c.get("issuer")), "year": _s(c.get("year"))}
        for c in profile.certifications or []
        if isinstance(c, dict) and c.get("name")
    ]
    achievements = [
        _s(a if isinstance(a, str) else (a.get("title") or a.get("description") if isinstance(a, dict) else None))
        for a in profile.achievements or []
    ]
    languages = [
        _s(lang if isinstance(lang, str) else (lang.get("name") if isinstance(lang, dict) else None))
        for lang in profile.languages or []
    ]
    headline = _s(profile.headline) or next((_s(t) for t in (prefs.desired_titles if prefs else []) or [] if _s(t)), None)
    return ParsedResume.model_validate(
        {
            "name": name,
            "email": _s(profile.email),
            "phone": _s(profile.phone),
            "headline": headline,
            "location": location,
            "summary": (profile.summary or "").strip() or None,
            "skills": _dedupe([str(s) for s in (profile.skills or []) + (profile.technologies or []) if s]),
            "experience": experience,
            "education": education,
            "projects": projects,
            "certifications": certifications,
            "achievements": [a for a in achievements if a],
            "languages": [lang for lang in languages if lang],
            "total_experience_years": profile.years_of_experience,
            "links": {"linkedin": _s(profile.linkedin_url), "github": _s(profile.github_url), "portfolio": _s(profile.portfolio_url)},
        }
    )


def default_target_role(db: Session, user_id: uuid.UUID) -> str | None:
    prefs = db.scalar(select(JobPreference).where(JobPreference.user_id == user_id))
    return next((_s(t) for t in (prefs.desired_titles if prefs else []) or [] if _s(t)), None)


# --------------------------------------------------------------------------- text


def import_text(
    db: Session,
    user_id: uuid.UUID,
    text: str,
    *,
    name: str | None = None,
    target_role: str | None = None,
    template: str | None = None,
) -> Resume:
    """Parse pasted text like an upload (rules, then model gap-fill) into a CREATED resume."""
    from app.modules.resumes.extraction import normalize_text

    cleaned = normalize_text(text or "").strip()
    if len(cleaned) < 30:
        raise ValidationFailed("Paste the full resume text (at least a few lines).", code="text_too_short")
    parsed = ai_tasks.parse_resume(cleaned)
    display = _s(name) or (f"{parsed.name} - resume" if parsed.name else "Pasted resume")
    resume = service.create_resume_from_parsed(
        db,
        user_id,
        parsed,
        name=display,
        kind=ResumeKind.CREATED,
        target_role=target_role,
        template=template or "classic",
        note="Imported from pasted text",
        change_source=ResumeChangeSource.SYSTEM,
    )
    # The pasted text is the source document: the fact checks compare against it.
    resume.text_content = cleaned
    db.add(resume)
    return resume


# --------------------------------------------------------------------------- LinkedIn


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.file_size > MAX_MEMBER_BYTES:
        raise ValidationFailed(f"{PurePosixPath(info.filename).name} is too large for a LinkedIn export.", code="file_too_large")
    with archive.open(info) as handle:
        data = handle.read(MAX_MEMBER_BYTES + 1)  # the header's size can lie (zip bombs)
    if len(data) > MAX_MEMBER_BYTES:
        raise ValidationFailed(f"{PurePosixPath(info.filename).name} is too large for a LinkedIn export.", code="file_too_large")
    return data


def linkedin_members(files: list[tuple[str, bytes]]) -> dict[str, bytes]:
    """``{"positions.csv": bytes, ...}`` from uploaded ZIPs and/or CSVs (never touches disk)."""
    found: dict[str, bytes] = {}
    total = 0
    for filename, content in files:
        base = PurePosixPath((filename or "").replace("\\", "/")).name.lower()
        if content[:2] == b"PK" or base.endswith(".zip"):
            try:
                archive = zipfile.ZipFile(io.BytesIO(content))
            except (zipfile.BadZipFile, OSError) as exc:
                raise ValidationFailed("That ZIP file could not be read.", code="invalid_zip") from exc
            with archive:
                infos = archive.infolist()
                if len(infos) > MAX_ZIP_MEMBERS:
                    raise ValidationFailed("That ZIP has too many files to be a LinkedIn export.", code="invalid_zip")
                for info in infos:
                    raw_name = info.filename.replace("\\", "/")
                    # Zip-slip: nothing is ever extracted, and a member with a traversal or
                    # absolute path is not something LinkedIn produces, so it is ignored.
                    if info.is_dir() or raw_name.startswith("/") or ".." in raw_name.split("/") or re.match(r"^[A-Za-z]:", raw_name):
                        continue
                    if info.flag_bits & 0x1:  # encrypted
                        continue
                    member = PurePosixPath(raw_name).name.lower()
                    if member not in LINKEDIN_FILES or member in found:
                        continue
                    data = _read_member(archive, info)
                    total += len(data)
                    if total > MAX_TOTAL_BYTES:
                        raise ValidationFailed("That export is larger than expected.", code="file_too_large")
                    found[member] = data
        elif base in LINKEDIN_FILES:
            if len(content) > MAX_MEMBER_BYTES:
                raise ValidationFailed(f"{base} is too large for a LinkedIn export.", code="file_too_large")
            total += len(content)
            if total > MAX_TOTAL_BYTES:
                raise ValidationFailed("That export is larger than expected.", code="file_too_large")
            found[base] = content
        else:
            raise ValidationFailed(
                f"{PurePosixPath(filename or 'file').name} is not part of a LinkedIn export. Upload the ZIP or its CSV files "
                "(Profile.csv, Positions.csv, Education.csv, Skills.csv, ...).",
                code="unsupported_file_type",
            )
    return found


def _rows(name: str, content: bytes) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    rows = list(csv.reader(io.StringIO(text)))
    hint = _HEADER_HINT.get(name, "")
    header_index = next((i for i, row in enumerate(rows[:20]) if hint in [c.strip() for c in row]), None)
    if header_index is None:
        return []
    header = [c.strip() for c in rows[header_index]]
    out: list[dict[str, str]] = []
    for row in rows[header_index + 1 : header_index + 1 + MAX_CSV_ROWS]:
        if not any(cell.strip() for cell in row):
            continue
        out.append({header[i]: (row[i] if i < len(row) else "").strip() for i in range(len(header))})
    return out


def parse_linkedin(members: dict[str, bytes]) -> ParsedResume:
    """Map LinkedIn export CSVs onto ``ParsedResume`` (column names as LinkedIn writes them)."""
    data: dict[str, Any] = {"links": {}}
    profile = _rows("profile.csv", members["profile.csv"]) if "profile.csv" in members else []
    if profile:
        row = profile[0]
        data["name"] = _s(" ".join(p for p in (row.get("First Name"), row.get("Last Name")) if p))
        data["headline"] = _s(row.get("Headline"))
        data["summary"] = (row.get("Summary") or "").strip() or None
        data["location"] = _s(row.get("Geo Location")) or _s(row.get("Address"))
        for url in _URL_RE.findall(row.get("Websites") or ""):
            url = url.rstrip(".,;")
            if "github.com" in url.lower():
                data["links"].setdefault("github", url)
            elif "linkedin.com" in url.lower():
                data["links"].setdefault("linkedin", url)
            else:
                data["links"].setdefault("portfolio", url)
    emails = _rows("email addresses.csv", members["email addresses.csv"]) if "email addresses.csv" in members else []
    if emails:
        primary = next((r for r in emails if (r.get("Primary") or "").lower() == "yes"), emails[0])
        data["email"] = _s(primary.get("Email Address"))
    phones = _rows("phonenumbers.csv", members["phonenumbers.csv"]) if "phonenumbers.csv" in members else []
    if phones:
        data["phone"] = _s(phones[0].get("Number"))

    data["experience"] = [
        {
            "company": _s(r.get("Company Name")),
            "title": _s(r.get("Title")),
            "description": (r.get("Description") or "").strip() or None,
            "location": _s(r.get("Location")),
            "start": normalise_date(r.get("Started On")),
            # LinkedIn leaves "Finished On" empty for the role you hold now.
            "end": normalise_date(r.get("Finished On")) or ("Present" if _s(r.get("Started On")) else None),
        }
        for r in (_rows("positions.csv", members["positions.csv"]) if "positions.csv" in members else [])
        if _s(r.get("Company Name")) or _s(r.get("Title"))
    ]
    data["education"] = [
        {
            "institution": _s(r.get("School Name")),
            "degree": _s(r.get("Degree Name")),
            "start": normalise_date(r.get("Start Date")),
            "end": normalise_date(r.get("End Date")),
        }
        for r in (_rows("education.csv", members["education.csv"]) if "education.csv" in members else [])
        if _s(r.get("School Name")) or _s(r.get("Degree Name"))
    ]
    data["skills"] = _dedupe(
        [ai_tasks.resume_skill_name(r.get("Name") or "") for r in (_rows("skills.csv", members["skills.csv"]) if "skills.csv" in members else [])]
    )
    data["certifications"] = [
        {
            "name": _s(r.get("Name")),
            "issuer": _s(r.get("Authority")),
            "year": (m.group(0) if (m := re.search(r"(19|20)\d{2}", r.get("Started On") or "")) else None),
        }
        for r in (_rows("certifications.csv", members["certifications.csv"]) if "certifications.csv" in members else [])
        if _s(r.get("Name"))
    ]
    data["projects"] = [
        {"name": _s(r.get("Title")), "description": (r.get("Description") or "").strip() or None, "url": _s(r.get("Url"))}
        for r in (_rows("projects.csv", members["projects.csv"]) if "projects.csv" in members else [])
        if _s(r.get("Title")) or _s(r.get("Description"))
    ]
    data["languages"] = [
        f"{_s(r.get('Name'))} ({_s(r.get('Proficiency'))})" if _s(r.get("Proficiency")) else _s(r.get("Name"))
        for r in (_rows("languages.csv", members["languages.csv"]) if "languages.csv" in members else [])
        if _s(r.get("Name"))
    ]
    data["achievements"] = [
        _s(" - ".join(p for p in (r.get("Title"), r.get("Description")) if _s(p)))
        for r in (_rows("honors.csv", members["honors.csv"]) if "honors.csv" in members else [])
        if _s(r.get("Title"))
    ]
    return ParsedResume.model_validate(data)


def import_linkedin(
    db: Session,
    user_id: uuid.UUID,
    files: list[tuple[str, bytes]],
    *,
    name: str | None = None,
    target_role: str | None = None,
    template: str | None = None,
) -> Resume:
    members = linkedin_members(files)
    if not ({"profile.csv", "positions.csv"} & set(members)):
        raise ValidationFailed(
            "No LinkedIn profile data found. Upload the ZIP from LinkedIn's “Get a copy of your data”, "
            "or at least Profile.csv and Positions.csv.",
            code="linkedin_data_missing",
            details={"found": sorted(members)},
        )
    parsed = parse_linkedin(members)
    display = _s(name) or (f"{parsed.name} - LinkedIn" if parsed.name else "LinkedIn import")
    resume = service.create_resume_from_parsed(
        db,
        user_id,
        parsed,
        name=display,
        kind=ResumeKind.CREATED,
        target_role=target_role,
        template=template or "classic",
        note="Imported from a LinkedIn data export",
        change_source=ResumeChangeSource.SYSTEM,
    )
    logger.info("LinkedIn import for user %s: %s", user_id, sorted(members))
    return resume


__all__ = [
    "LINKEDIN_FILES",
    "default_target_role",
    "import_linkedin",
    "import_text",
    "linkedin_members",
    "normalise_date",
    "parse_linkedin",
    "prefill_from_profile",
]
