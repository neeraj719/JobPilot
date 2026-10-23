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
from app.models.enums import Actor, ResumeParseStatus
from app.models.resume import Resume, ResumeVersion
from app.modules.ai import tasks as ai_tasks
from app.modules.ai.schemas import ParsedResume
from app.modules.resumes import recommendations, storage
from app.modules.resumes.extraction import try_extract_text
from app.modules.resumes.schemas import ResumeRead, ResumeRecommendations, ResumeVersionRead, VersionScore

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- reads


def list_resumes(db: Session, user_id: uuid.UUID) -> list[Resume]:
    stmt = (
        select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(Resume.is_default.desc(), Resume.created_at.desc())
    )
    return list(db.scalars(stmt))


def get_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    """The user's resume, or ``NotFoundError`` (also for another user's resume)."""
    resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id))
    if resume is None:
        raise NotFoundError("Resume not found")
    return resume


def get_default_resume(db: Session, user_id: uuid.UUID) -> Resume | None:
    """The user's default resume, falling back to the most recent one."""
    resume = db.scalar(
        select(Resume).where(Resume.user_id == user_id, Resume.is_default.is_(True)).order_by(Resume.created_at.desc())
    )
    if resume is not None:
        return resume
    return db.scalar(select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc()))


def list_versions(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> list[ResumeVersion]:
    resume = get_resume(db, user_id, resume_id)
    stmt = select(ResumeVersion).where(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc())
    return list(db.scalars(stmt))


def resume_to_read(resume: Resume) -> ResumeRead:
    return ResumeRead.model_validate(resume)


def version_to_read(version: ResumeVersion) -> ResumeVersionRead:
    return ResumeVersionRead.model_validate(version)


# --------------------------------------------------------------------------- helpers


def _count_resumes(db: Session, user_id: uuid.UUID) -> int:
    return len(list(db.scalars(select(Resume.id).where(Resume.user_id == user_id))))


def set_default_resume(db: Session, user_id: uuid.UUID, resume: Resume) -> Resume:
    """Make ``resume`` the default and unset every other resume of that user."""
    for other in db.scalars(select(Resume).where(Resume.user_id == user_id, Resume.id != resume.id)):
        if other.is_default:
            other.is_default = False
            db.add(other)
    resume.is_default = True
    db.add(resume)
    return resume


def _add_version(db: Session, resume: Resume, *, note: str, parsed_data: dict[str, Any] | None = None) -> ResumeVersion:
    version = ResumeVersion(
        resume_id=resume.id,
        version_number=resume.current_version,
        file_path=resume.file_path,
        parsed_data=parsed_data if parsed_data is not None else (resume.parsed_data or {}),
        note=note[:500],
        created_at=utcnow(),
    )
    db.add(version)
    return version


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

    if set_default or _count_resumes(db, user_id) <= 1:
        set_default_resume(db, user_id, resume)

    _add_version(db, resume, note="Initial upload")
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


def update_resume(
    db: Session,
    user_id: uuid.UUID,
    resume_id: uuid.UUID,
    *,
    name: str | None = None,
    target_role: str | None = None,
    is_default: bool | None = None,
) -> Resume:
    resume = get_resume(db, user_id, resume_id)
    changed: list[str] = []
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
) -> Resume:
    """Save user-edited parsed data as a **new version** of the resume."""
    resume = get_resume(db, user_id, resume_id)
    resume.parsed_data = parsed.model_dump(mode="json")
    resume.parse_status = ResumeParseStatus.PARSED
    resume.parse_error = None
    resume.parsed_at = utcnow()
    resume.current_version = int(resume.current_version or 1) + 1
    db.add(resume)
    _add_version(db, resume, note=note)
    audit(
        db,
        action="resume.parsed_data_updated",
        message=f"Parsed data edited for resume {resume.name} (v{resume.current_version})",
        user_id=user_id,
        actor=Actor.USER,
        meta={"resume_id": str(resume.id), "version": resume.current_version},
    )
    return resume


def reparse(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    """Re-run extraction + parsing on the stored file; a changed result is saved as a new version."""
    resume = get_resume(db, user_id, resume_id)
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
            resume.parsed_data = fresh
    if resume.parse_status == ResumeParseStatus.PARSED and (resume.parsed_data or {}) != before:
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
        promoted = db.scalar(select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc()))
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
    "create_resume_from_bytes",
    "delete_resume",
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
