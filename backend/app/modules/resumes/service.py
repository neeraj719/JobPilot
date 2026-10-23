"""Resume business logic (CONTRACTS.md §7).

Everything is scoped to a user: :func:`get_resume` raises ``NotFoundError`` for a row
that belongs to somebody else, so ownership is enforced in exactly one place.

Services never commit — the ``get_db`` dependency (or ``session_scope`` in background
jobs and the seed script) owns the transaction.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.database import soft_delete
from app.core.exceptions import NotFoundError, ValidationFailed
from app.models.base import utcnow
from app.models.enums import Actor, ResumeChangeSource, ResumeKind, ResumeParseStatus
from app.models.resume import Resume, ResumeVersion
from app.modules.ai import tasks as ai_tasks
from app.modules.ai.schemas import ParsedResume
from app.modules.resumes import recommendations, storage
from app.modules.resumes.extraction import try_extract_text
from app.modules.resumes.schemas import ResumeRead, ResumeRecommendations, ResumeVersionRead, VersionScore

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- reads


def list_resumes(db: Session, user_id: uuid.UUID, *, include_archived: bool = False) -> list[Resume]:
    """The user's resumes, default first. Archived ones only when asked for."""
    stmt = select(Resume).where(Resume.user_id == user_id)
    if not include_archived:
        stmt = stmt.where(Resume.archived_at.is_(None))
    stmt = stmt.order_by(Resume.is_default.desc(), Resume.created_at.desc())
    return list(db.scalars(stmt))


def get_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    """The user's resume, or ``NotFoundError`` (also for another user's resume)."""
    resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id))
    if resume is None:
        raise NotFoundError("Resume not found")
    return resume


def get_default_resume(db: Session, user_id: uuid.UUID) -> Resume | None:
    """The user's default resume, falling back to the most recent one. Archived resumes are
    never picked: matching, autofill and the application pipeline call this."""
    active = (Resume.user_id == user_id, Resume.archived_at.is_(None))
    resume = db.scalar(select(Resume).where(*active, Resume.is_default.is_(True)).order_by(Resume.created_at.desc()))
    if resume is not None:
        return resume
    return db.scalar(select(Resume).where(*active).order_by(Resume.created_at.desc()))


def list_versions(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> list[ResumeVersion]:
    resume = get_resume(db, user_id, resume_id)
    stmt = select(ResumeVersion).where(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc())
    return list(db.scalars(stmt))


def resume_to_read(resume: Resume) -> ResumeRead:
    read = ResumeRead.model_validate(resume)
    read.has_file = bool(resume.file_path)
    return read


def version_to_read(version: ResumeVersion) -> ResumeVersionRead:
    return ResumeVersionRead.model_validate(version)


# --------------------------------------------------------------------------- helpers


def _count_resumes(db: Session, user_id: uuid.UUID) -> int:
    return len(list(db.scalars(select(Resume.id).where(Resume.user_id == user_id))))


def _has_default(db: Session, user_id: uuid.UUID, *, excluding: uuid.UUID | None = None) -> bool:
    stmt = select(Resume.id).where(Resume.user_id == user_id, Resume.is_default.is_(True), Resume.archived_at.is_(None))
    if excluding is not None:
        stmt = stmt.where(Resume.id != excluding)
    return db.scalar(stmt.limit(1)) is not None


def _validate_template(template: str | None) -> str:
    from app.modules.resumes.templates import DEFAULT_TEMPLATE_ID, TEMPLATES

    key = (template or DEFAULT_TEMPLATE_ID).strip().lower()
    if key not in TEMPLATES:
        raise ValidationFailed(
            f"Unknown template “{template}”.", code="unknown_template", details={"allowed": sorted(TEMPLATES)}
        )
    return key


def set_default_resume(db: Session, user_id: uuid.UUID, resume: Resume) -> Resume:
    """Make ``resume`` the default and unset every other resume of that user."""
    if resume.archived_at is not None:
        raise ValidationFailed("Restore this resume from the archive before making it the default.", code="archived_resume")
    for other in db.scalars(select(Resume).where(Resume.user_id == user_id, Resume.id != resume.id)):
        if other.is_default:
            other.is_default = False
            db.add(other)
    resume.is_default = True
    db.add(resume)
    return resume


def _add_version(
    db: Session,
    resume: Resume,
    *,
    note: str,
    parsed_data: dict[str, Any] | None = None,
    change_source: ResumeChangeSource = ResumeChangeSource.USER,
) -> ResumeVersion:
    version = ResumeVersion(
        resume_id=resume.id,
        version_number=resume.current_version,
        file_path=resume.file_path,
        parsed_data=parsed_data if parsed_data is not None else (resume.parsed_data or {}),
        note=note[:500],
        change_source=change_source,
        created_at=utcnow(),
    )
    db.add(version)
    return version


def plain_text_of(parsed: ParsedResume) -> str:
    """A plain-text rendering of structured resume data.

    Resumes built in the editor have no uploaded document, yet matching, keyword checks
    and the "no invented numbers" guard all read ``text_content``. For those resumes the
    structured data *is* the source of truth, so its text rendering stands in for the file.
    """
    lines: list[str] = []
    for value in (parsed.name, parsed.headline, parsed.email, parsed.phone, parsed.location):
        if value:
            lines.append(str(value))
    for link in (parsed.links.linkedin, parsed.links.github, parsed.links.portfolio):
        if link:
            lines.append(link)
    if parsed.summary:
        lines += ["", "Summary", parsed.summary]
    if parsed.skills:
        lines += ["", "Skills", ", ".join(str(s) for s in parsed.skills)]
    if parsed.experience:
        lines += ["", "Experience"]
        for entry in parsed.experience:
            head = " | ".join(p for p in (entry.title, entry.company, " - ".join(p for p in (entry.start, entry.end) if p)) if p)
            if head:
                lines.append(head)
            if entry.description:
                lines.append(entry.description)
            if entry.technologies:
                lines.append("Technologies: " + ", ".join(str(t) for t in entry.technologies))
    if parsed.projects:
        lines += ["", "Projects"]
        for project in parsed.projects:
            if project.name:
                lines.append(project.name)
            if project.description:
                lines.append(project.description)
            if project.technologies:
                lines.append("Technologies: " + ", ".join(str(t) for t in project.technologies))
    if parsed.education:
        lines += ["", "Education"]
        for edu in parsed.education:
            head = " | ".join(p for p in (edu.degree, edu.field, edu.institution, " - ".join(p for p in (edu.start, edu.end) if p)) if p)
            if head:
                lines.append(head)
    if parsed.certifications:
        lines += ["", "Certifications"]
        for cert in parsed.certifications:
            head = " | ".join(p for p in (cert.name, cert.issuer, cert.year) if p)
            if head:
                lines.append(head)
    # Optional list-of-text sections added later (achievements, languages, ...) render generically.
    extras = parsed.model_dump(
        mode="json",
        exclude={
            "name", "email", "phone", "links", "summary", "skills", "experience", "projects", "education",
            "certifications", "total_experience_years", "headline", "location", "section_order",
        },
    )
    for key, value in extras.items():
        if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            lines += ["", key.replace("_", " ").title(), *value]
    return "\n".join(lines).strip()


def _parse_into(resume: Resume, content: bytes, ext: str) -> None:
    """Extract text + run ``ai.tasks.parse_resume``, recording failures on the row."""
    text, error = try_extract_text(content, ext)
    if error or not text:
        resume.text_content = text
        resume.parsed_data = {}
        resume.parse_status = ResumeParseStatus.FAILED
        resume.parse_error = error or "No text could be extracted from the document."
        resume.parsed_at = None
        return

    resume.text_content = text
    try:
        parsed: ParsedResume = ai_tasks.parse_resume(text)
    except Exception as exc:  # noqa: BLE001 - parsing must never break an upload
        logger.exception("Resume parsing failed")
        resume.parsed_data = {}
        resume.parse_status = ResumeParseStatus.FAILED
        resume.parse_error = f"Could not parse the resume: {exc}"
        resume.parsed_at = None
        return

    resume.parsed_data = parsed.model_dump(mode="json")
    resume.parse_status = ResumeParseStatus.PARSED
    resume.parse_error = None
    resume.parsed_at = utcnow()


# --------------------------------------------------------------------------- writes


def create_resume_from_bytes(
    db: Session,
    user_id: uuid.UUID,
    filename: str,
    content: bytes,
    name: str | None = None,
    target_role: str | None = None,
    set_default: bool = False,
) -> Resume:
    """Validate, store, extract and parse an uploaded resume.

    Used by the upload endpoint and by the seed script. The first resume a user
    uploads always becomes the default.
    """
    stored = storage.store_upload(user_id, filename, content)
    display_name = (name or Path(filename or "").stem or "Resume").strip()[:255]

    resume = Resume(
        user_id=user_id,
        name=display_name,
        target_role=(target_role or None),
        is_default=False,
        file_path=stored.path,
        original_filename=Path(filename or f"resume.{stored.ext}").name[:255],
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        parsed_data={},
        parse_status=ResumeParseStatus.PENDING,
        current_version=1,
    )
    _parse_into(resume, content, stored.ext)
    db.add(resume)
    db.flush()

    if set_default or not _has_default(db, user_id, excluding=resume.id):
        set_default_resume(db, user_id, resume)

    _add_version(db, resume, note="Initial upload", change_source=ResumeChangeSource.SYSTEM)
    audit(
        db,
        action="resume.uploaded",
        message=f"Resume uploaded: {resume.name} ({resume.original_filename})",
        user_id=user_id,
        actor=Actor.USER,
        meta={
            "resume_id": str(resume.id),
            "size_bytes": resume.size_bytes,
            "parse_status": resume.parse_status.value,
            "is_default": resume.is_default,
        },
    )
    logger.info("Resume %s created for user %s (parse_status=%s)", resume.id, user_id, resume.parse_status)
    return resume


def create_resume_from_parsed(
    db: Session,
    user_id: uuid.UUID,
    parsed: ParsedResume,
    *,
    name: str,
    kind: ResumeKind = ResumeKind.CREATED,
    target_role: str | None = None,
    template: str = "classic",
    source_resume_id: uuid.UUID | None = None,
    set_default: bool = False,
    note: str = "Created in the editor",
    change_source: ResumeChangeSource = ResumeChangeSource.USER,
) -> Resume:
    """A resume made from structured data (editor, import, tailoring) — there is no original file.

    ``text_content`` is rendered from the data so matching and the fact checks work the
    same way as for an upload. A TAILORED resume names its ``source_resume_id`` (which must
    belong to the same user) so every generated version stays linked to where it came from.
    """
    if source_resume_id is not None:
        get_resume(db, user_id, source_resume_id)  # ownership check: 404 for another user's resume
    display_name = (name or "").strip()[:255] or "Resume"
    resume = Resume(
        user_id=user_id,
        name=display_name,
        target_role=(target_role or "").strip()[:255] or None,
        kind=kind,
        template=_validate_template(template),
        source_resume_id=source_resume_id,
        is_default=False,
        file_path=None,
        original_filename=None,
        mime_type=None,
        size_bytes=None,
        sha256=None,
        text_content=plain_text_of(parsed),
        parsed_data=parsed.model_dump(mode="json"),
        parse_status=ResumeParseStatus.PARSED,
        parse_error=None,
        parsed_at=utcnow(),
        current_version=1,
    )
    db.add(resume)
    db.flush()

    if set_default or not _has_default(db, user_id, excluding=resume.id):
        set_default_resume(db, user_id, resume)

    _add_version(db, resume, note=note, change_source=change_source)
    audit(
        db,
        action="resume.created",
        message=f"Resume created: {resume.name} ({kind.value.lower()})",
        user_id=user_id,
        actor=Actor.USER if change_source == ResumeChangeSource.USER else Actor.SYSTEM,
        meta={
            "resume_id": str(resume.id),
            "kind": kind.value,
            "template": resume.template,
            "source_resume_id": str(source_resume_id) if source_resume_id else None,
            "is_default": resume.is_default,
        },
    )
    logger.info("Resume %s (%s) created for user %s", resume.id, kind.value, user_id)
    return resume


def update_resume(
    db: Session,
    user_id: uuid.UUID,
    resume_id: uuid.UUID,
    *,
    name: str | None = None,
    target_role: str | None = None,
    is_default: bool | None = None,
    template: str | None = None,
) -> Resume:
    resume = get_resume(db, user_id, resume_id)
    changed: list[str] = []
    if template is not None:
        resume.template = _validate_template(template)
        changed.append("template")
    if name is not None:
        resume.name = name.strip()[:255]
        changed.append("name")
    if target_role is not None:
        resume.target_role = target_role.strip()[:255] or None
        changed.append("target_role")
    if is_default is True:
        set_default_resume(db, user_id, resume)
        changed.append("is_default")
    elif is_default is False and resume.is_default:
        raise ValidationFailed(
            "Set another resume as default instead of unsetting this one.",
            code="default_required",
        )
    db.add(resume)
    if changed:
        audit(
            db,
            action="resume.updated",
            message=f"Resume updated: {', '.join(changed)}",
            user_id=user_id,
            actor=Actor.USER,
            meta={"resume_id": str(resume.id), "fields": changed},
        )
    return resume


def update_parsed_data(
    db: Session,
    user_id: uuid.UUID,
    resume_id: uuid.UUID,
    parsed: ParsedResume,
    *,
    note: str = "Edited by user",
    change_source: ResumeChangeSource = ResumeChangeSource.USER,
) -> Resume:
    """Save edited parsed data as a **new version** of the resume.

    ``change_source`` records who made the change (USER / AI / SYSTEM) so the history can
    tell AI-generated versions from the user's own edits.
    """
    resume = get_resume(db, user_id, resume_id)
    resume.parsed_data = parsed.model_dump(mode="json")
    if resume.kind != ResumeKind.UPLOADED or not resume.text_content:
        # No original document: the structured data is the text the checks read.
        resume.text_content = plain_text_of(parsed)
    resume.parse_status = ResumeParseStatus.PARSED
    resume.parse_error = None
    resume.parsed_at = utcnow()
    resume.current_version = int(resume.current_version or 1) + 1
    resume.draft_data = None
    resume.draft_saved_at = None
    db.add(resume)
    _add_version(db, resume, note=note, change_source=change_source)
    audit(
        db,
        action="resume.parsed_data_updated",
        message=f"Parsed data edited for resume {resume.name} (v{resume.current_version})",
        user_id=user_id,
        actor=Actor.USER if change_source != ResumeChangeSource.SYSTEM else Actor.SYSTEM,
        meta={"resume_id": str(resume.id), "version": resume.current_version, "change_source": change_source.value},
    )
    _invalidate(resume.id)
    return resume


def _invalidate(resume_id: uuid.UUID) -> None:
    try:
        recommendations.invalidate_resume(resume_id)
    except Exception:  # noqa: BLE001 - a stale cache entry expires on its own
        logger.debug("Could not invalidate recommendations for %s", resume_id)


def _same_data(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    """Equal once both are normalised (older JSON lacks keys added to ``ParsedResume`` later)."""
    try:
        left = ParsedResume.model_validate(a or {}).model_dump(mode="json")
        right = ParsedResume.model_validate(b or {}).model_dump(mode="json")
        return left == right
    except Exception:  # noqa: BLE001
        return (a or {}) == (b or {})


def reparse(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    """Re-run extraction + parsing on the stored file; a changed result is saved as a new version."""
    resume = get_resume(db, user_id, resume_id)
    if not resume.file_path:
        raise ValidationFailed(
            "This resume was built in JobPilot, so there is no uploaded file to read again.", code="no_file"
        )
    path = Path(resume.file_path)
    if not path.is_file():
        resume.parse_status = ResumeParseStatus.FAILED
        resume.parse_error = "The stored resume file is missing; upload it again."
        resume.parsed_at = None
        db.add(resume)
        logger.warning("Reparse failed: file missing for resume %s", resume.id)
        return resume

    before = resume.parsed_data or {}
    _parse_into(resume, path.read_bytes(), path.suffix.lstrip("."))
    if resume.parse_status == ResumeParseStatus.PARSED:
        # Skills the user added (by hand or through "Apply suggestions") are confirmed facts that
        # the file does not contain; a re-parse must not silently drop them.
        fresh = dict(resume.parsed_data or {})
        skills = [str(s) for s in fresh.get("skills") or []]
        seen = {s.lower() for s in skills}
        kept = [str(s) for s in before.get("skills") or [] if str(s).strip() and str(s).lower() not in seen]
        if kept:
            fresh["skills"] = skills + kept
        # Fields a file never carries (headline, section order, ...) were typed in the editor.
        for key in ("headline", "location", "achievements", "languages", "section_order"):
            if before.get(key) and not fresh.get(key):
                fresh[key] = before[key]
        resume.parsed_data = fresh
    if resume.parse_status == ResumeParseStatus.PARSED and not _same_data(resume.parsed_data, before):
        # Saved as a new version, so a re-parse never silently replaces the user's edits:
        # the previous version stays in the history and can be restored.
        resume.current_version = int(resume.current_version or 1) + 1
        _add_version(db, resume, note="Re-parsed from the uploaded file")
        try:
            from app.modules.resumes.recommendations import invalidate_resume

            invalidate_resume(resume.id)
        except Exception:  # noqa: BLE001 - a stale cache entry expires on its own
            logger.debug("Could not invalidate recommendations for %s", resume.id)
    db.add(resume)
    audit(
        db,
        action="resume.reparsed",
        message=f"Resume re-parsed: {resume.name} ({resume.parse_status.value})",
        user_id=user_id,
        actor=Actor.USER,
        meta={"resume_id": str(resume.id), "parse_status": resume.parse_status.value},
    )
    return resume


def delete_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> None:
    """Tombstone the row; promote the newest remaining resume if needed.

    The uploaded file is deliberately **left on disk**. The row is soft-deleted, so the
    delete is reversible, and throwing the bytes away would make it reversible in name
    only. ``storage`` is pruned separately, not from a user-facing endpoint.
    """
    resume = get_resume(db, user_id, resume_id)
    was_default = resume.is_default
    name = resume.name

    # Soft delete: the row is tombstoned but the uploaded file stays on disk, so a
    # resume deleted by mistake is still recoverable by clearing ``deleted_at``.
    soft_delete(resume)
    db.flush()

    promoted: Resume | None = None
    if was_default:
        promoted = db.scalar(
            select(Resume)
            .where(Resume.user_id == user_id, Resume.archived_at.is_(None))
            .order_by(Resume.created_at.desc())
        )
        if promoted is not None:
            set_default_resume(db, user_id, promoted)

    audit(
        db,
        action="resume.deleted",
        message=f"Resume deleted: {name}",
        user_id=user_id,
        actor=Actor.USER,
        meta={
            "resume_id": str(resume_id),
            "was_default": was_default,
            "promoted_resume_id": str(promoted.id) if promoted else None,
        },
    )
    logger.info("Resume %s deleted for user %s (promoted=%s)", resume_id, user_id, promoted.id if promoted else None)


# --------------------------------------------------------------------------- resume studio
#
# Drafts (editor autosave), duplicate, archive, versions (one / diff / restore), the
# cross-resume history, the dashboard summary and export. Every function takes the
# user id and resolves the resume through ``get_resume`` (404 for anyone else's).


def get_draft(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    return get_resume(db, user_id, resume_id)


def save_draft(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID, parsed: ParsedResume) -> Resume:
    """Autosave: keep the editor's unsaved data without making a version."""
    resume = get_resume(db, user_id, resume_id)
    resume.draft_data = parsed.model_dump(mode="json")
    resume.draft_saved_at = utcnow()
    db.add(resume)
    return resume


def discard_draft(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    resume = get_resume(db, user_id, resume_id)
    if resume.draft_data is not None or resume.draft_saved_at is not None:
        resume.draft_data = None
        resume.draft_saved_at = None
        db.add(resume)
        audit(
            db,
            action="resume.draft_discarded",
            message=f"Unsaved draft discarded: {resume.name}",
            user_id=user_id,
            actor=Actor.USER,
            meta={"resume_id": str(resume.id)},
        )
    return resume


def duplicate_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID, *, name: str | None = None) -> Resume:
    """A full copy (same kind, data, template, target role) linked back to its source.

    An uploaded resume's copy points at the same stored file, so it can still be
    re-parsed; files are never deleted from a user-facing endpoint, so sharing is safe.
    """
    source = get_resume(db, user_id, resume_id)
    parsed = ParsedResume.model_validate(source.parsed_data or {})
    display = (name or "").strip()[:255] or f"{source.name} (copy)"[:255]
    copy_ = Resume(
        user_id=user_id,
        name=display,
        target_role=source.target_role,
        kind=source.kind,
        template=source.template or "classic",
        source_resume_id=source.id,
        is_default=False,
        file_path=source.file_path,
        original_filename=source.original_filename,
        mime_type=source.mime_type,
        size_bytes=source.size_bytes,
        sha256=source.sha256,
        text_content=source.text_content or plain_text_of(parsed),
        parsed_data=parsed.model_dump(mode="json"),
        parse_status=source.parse_status,
        parse_error=source.parse_error,
        parsed_at=source.parsed_at or utcnow(),
        current_version=1,
    )
    db.add(copy_)
    db.flush()
    _add_version(
        db,
        copy_,
        note=f"Duplicated from {source.name} v{int(source.current_version or 1)}",
        change_source=ResumeChangeSource.SYSTEM,
    )
    audit(
        db,
        action="resume.duplicated",
        message=f"Resume duplicated: {source.name} -> {copy_.name}",
        user_id=user_id,
        actor=Actor.USER,
        meta={"resume_id": str(copy_.id), "source_resume_id": str(source.id), "source_version": source.current_version},
    )
    return copy_


def archive_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    """Hide a resume from lists, matching and the pipeline without deleting it."""
    resume = get_resume(db, user_id, resume_id)
    if resume.archived_at is not None:
        return resume
    was_default = resume.is_default
    resume.archived_at = utcnow()
    resume.is_default = False
    db.add(resume)
    db.flush()
    promoted = None
    if was_default:
        promoted = db.scalar(
            select(Resume)
            .where(Resume.user_id == user_id, Resume.archived_at.is_(None), Resume.id != resume.id)
            .order_by(Resume.created_at.desc())
        )
        if promoted is not None:
            set_default_resume(db, user_id, promoted)
    audit(
        db,
        action="resume.archived",
        message=f"Resume archived: {resume.name}",
        user_id=user_id,
        actor=Actor.USER,
        meta={"resume_id": str(resume.id), "was_default": was_default, "promoted_resume_id": str(promoted.id) if promoted else None},
    )
    return resume


def unarchive_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    resume = get_resume(db, user_id, resume_id)
    if resume.archived_at is None:
        return resume
    resume.archived_at = None
    db.add(resume)
    db.flush()
    if not _has_default(db, user_id, excluding=resume.id):
        set_default_resume(db, user_id, resume)
    audit(
        db,
        action="resume.unarchived",
        message=f"Resume restored from the archive: {resume.name}",
        user_id=user_id,
        actor=Actor.USER,
        meta={"resume_id": str(resume.id), "is_default": resume.is_default},
    )
    return resume


def get_version(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID, version_number: int) -> ResumeVersion:
    resume = get_resume(db, user_id, resume_id)
    version = db.scalar(
        select(ResumeVersion).where(ResumeVersion.resume_id == resume.id, ResumeVersion.version_number == int(version_number))
    )
    if version is None:
        raise NotFoundError(f"Version {version_number} not found")
    return version


def restore_version(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID, version_number: int) -> Resume:
    """Make an old version current again — as a **new** version, so nothing is lost."""
    version = get_version(db, user_id, resume_id, version_number)
    parsed = ParsedResume.model_validate(version.parsed_data or {})
    resume = update_parsed_data(
        db,
        user_id,
        resume_id,
        parsed,
        note=f"Restored from v{version.version_number}",
        change_source=ResumeChangeSource.SYSTEM,
    )
    audit(
        db,
        action="resume.version_restored",
        message=f"Resume {resume.name}: v{version.version_number} restored as v{resume.current_version}",
        user_id=user_id,
        actor=Actor.USER,
        meta={"resume_id": str(resume.id), "restored_version": version.version_number, "new_version": resume.current_version},
    )
    return resume


def diff_versions(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID, version_number: int, against: int | None):
    """What changed from ``against`` (default: the previous version) to ``version_number``."""
    from app.modules.resumes.diff import diff_parsed

    target = get_version(db, user_id, resume_id, version_number)
    base_number = int(against) if against is not None else int(version_number) - 1
    base_data: dict[str, Any] = {}
    base_label = "nothing (first version)"
    if base_number >= 1:
        base = get_version(db, user_id, resume_id, base_number)
        base_data = base.parsed_data or {}
        base_label = f"v{base.version_number}"
    return diff_parsed(base_data, target.parsed_data or {}, before_label=base_label, after_label=f"v{target.version_number}")


def diff_resumes(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID, other_id: uuid.UUID):
    """Current ``other_id`` (before, e.g. the source) vs current ``resume_id`` (after, e.g. the tailored copy)."""
    from app.modules.resumes.diff import diff_parsed

    after = get_resume(db, user_id, resume_id)
    before = get_resume(db, user_id, other_id)
    return diff_parsed(
        before.parsed_data or {},
        after.parsed_data or {},
        before_label=f"{before.name} v{before.current_version}",
        after_label=f"{after.name} v{after.current_version}",
    )


HISTORY_MAX_LIMIT = 100


def history(
    db: Session,
    user_id: uuid.UUID,
    *,
    limit: int = 30,
    cursor: str | None = None,
    resume_id: uuid.UUID | None = None,
    change_source: ResumeChangeSource | None = None,
):
    """Versions across all of the user's resumes, newest first, with a change summary each."""
    from sqlalchemy import tuple_

    from app.modules.resumes.diff import content_summary, diff_parsed
    from app.modules.resumes.schemas import HistoryItem, HistoryPage

    limit = max(1, min(int(limit or 30), HISTORY_MAX_LIMIT))
    try:
        offset = max(0, int(cursor)) if cursor else 0
    except ValueError as exc:
        raise ValidationFailed("Invalid cursor.", code="invalid_cursor") from exc
    if resume_id is not None:
        get_resume(db, user_id, resume_id)  # 404 for another user's resume
    stmt = (
        select(ResumeVersion, Resume)
        .join(Resume, Resume.id == ResumeVersion.resume_id)
        .where(Resume.user_id == user_id)
    )
    if resume_id is not None:
        stmt = stmt.where(Resume.id == resume_id)
    if change_source is not None:
        stmt = stmt.where(ResumeVersion.change_source == change_source)
    stmt = stmt.order_by(ResumeVersion.created_at.desc(), ResumeVersion.version_number.desc()).offset(offset).limit(limit + 1)
    rows = list(db.execute(stmt).all())
    page, more = rows[:limit], len(rows) > limit

    wanted = {(version.resume_id, version.version_number - 1) for version, _ in page if version.version_number > 1}
    previous: dict[tuple[uuid.UUID, int], dict[str, Any]] = {}
    if wanted:
        for prev in db.scalars(
            select(ResumeVersion).where(tuple_(ResumeVersion.resume_id, ResumeVersion.version_number).in_(list(wanted)))
        ):
            previous[(prev.resume_id, prev.version_number)] = prev.parsed_data or {}

    items = []
    for version, resume in page:
        key = (version.resume_id, version.version_number - 1)
        if version.version_number > 1 and key in previous:
            summary = diff_parsed(previous[key], version.parsed_data or {}).description
        else:
            summary = content_summary(version.parsed_data)
        items.append(
            HistoryItem(
                id=version.id,
                resume_id=resume.id,
                resume_name=resume.name,
                resume_kind=resume.kind,
                resume_archived=resume.archived_at is not None,
                version_number=version.version_number,
                is_current=version.version_number == int(resume.current_version or 1),
                note=version.note,
                change_source=version.change_source,
                change_summary=summary,
                created_at=version.created_at,
            )
        )
    return HistoryPage(items=items, next_cursor=str(offset + limit) if more else None)


def summary(db: Session, user_id: uuid.UUID):
    """Cheap dashboard numbers (plan §4.6)."""
    from app.modules.resumes.schemas import RecentResume, ResumeSummary

    resumes = list(db.scalars(select(Resume).where(Resume.user_id == user_id)))
    active = [r for r in resumes if r.archived_at is None]
    by_kind: dict[str, int] = {kind.value: 0 for kind in ResumeKind}
    for resume in active:
        by_kind[resume.kind.value] = by_kind.get(resume.kind.value, 0) + 1
    ai_current = 0
    if active:
        ai_current = len(
            list(
                db.scalars(
                    select(ResumeVersion.id)
                    .join(Resume, Resume.id == ResumeVersion.resume_id)
                    .where(
                        Resume.user_id == user_id,
                        Resume.archived_at.is_(None),
                        ResumeVersion.version_number == Resume.current_version,
                        ResumeVersion.change_source == ResumeChangeSource.AI,
                    )
                )
            )
        )
    recent = sorted(active, key=lambda r: max(r.updated_at, r.draft_saved_at or r.updated_at), reverse=True)[:5]
    default = next((r for r in active if r.is_default), None)
    return ResumeSummary(
        total=len(active),
        archived=len(resumes) - len(active),
        by_kind=by_kind,
        recently_edited=[
            RecentResume(
                id=r.id,
                name=r.name,
                kind=r.kind,
                target_role=r.target_role,
                current_version=int(r.current_version or 1),
                has_draft=r.draft_saved_at is not None,
                updated_at=max(r.updated_at, r.draft_saved_at or r.updated_at),
            )
            for r in recent
        ],
        drafts_pending=sum(1 for r in active if r.draft_saved_at is not None),
        ai_versions_to_review=ai_current,
        default_resume_id=default.id if default else None,
    )


def export_resume(
    db: Session,
    user_id: uuid.UUID,
    resume_id: uuid.UUID,
    *,
    fmt: str,
    template: str | None = None,
    version: int | None = None,
) -> tuple[bytes, str, str]:
    """``(bytes, mime type, download filename)`` rendered from ``parsed_data`` (or one version's)."""
    from app.modules.resumes import render

    resume = get_resume(db, user_id, resume_id)
    data = resume.parsed_data or {}
    suffix = ""
    if version is not None:
        data = get_version(db, user_id, resume_id, version).parsed_data or {}
        suffix = f" v{int(version)}"
    template_id = _validate_template(template or resume.template)
    content, mime = render.render(ParsedResume.model_validate(data), fmt, template_id)
    filename = storage.safe_download_name(f"{resume.name}{suffix}.{fmt}", fmt)
    audit(
        db,
        action="resume.exported",
        message=f"Resume exported: {resume.name} ({fmt.upper()}, {template_id})",
        user_id=user_id,
        actor=Actor.USER,
        meta={"resume_id": str(resume.id), "format": fmt, "template": template_id, "version": version or resume.current_version},
    )
    return content, mime, filename


# --------------------------------------------------------------------------- recommendations


def get_recommendations(
    db: Session,
    user_id: uuid.UUID,
    resume_id: uuid.UUID,
    *,
    refresh: bool = False,
) -> ResumeRecommendations:
    """Improvement advice for one of the user's resumes (computed on demand, cached).

    Read-only: nothing is written, so ``refresh=True`` only bypasses the in-process cache.
    """
    resume = get_resume(db, user_id, resume_id)
    return recommendations.build_recommendations(db, user_id, resume, refresh=refresh)


def get_recommendation_history(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> list[VersionScore]:
    """Overall and average match score per stored version, for the before/after chart."""
    resume = get_resume(db, user_id, resume_id)
    return recommendations.build_version_history(db, user_id, resume)


__all__ = [
    "archive_resume",
    "create_resume_from_bytes",
    "create_resume_from_parsed",
    "delete_resume",
    "diff_resumes",
    "diff_versions",
    "discard_draft",
    "duplicate_resume",
    "export_resume",
    "get_draft",
    "get_version",
    "history",
    "plain_text_of",
    "restore_version",
    "save_draft",
    "summary",
    "unarchive_resume",
    "get_default_resume",
    "get_recommendation_history",
    "get_recommendations",
    "get_resume",
    "list_resumes",
    "list_versions",
    "reparse",
    "resume_to_read",
    "set_default_resume",
    "update_parsed_data",
    "update_resume",
    "version_to_read",
]
