"""Uploaded-resume endpoints — "upload my original resume and use it as-is".

Mounted at ``/api/v1/resumes`` next to ``resumes.router`` (same module gate). Everything
here is about the *original file* of an UPLOADED resume:

* ``GET  /{id}/file?disposition=inline|attachment`` — the stored file, inline for the
  in-app PDF preview (``/download`` in ``router.py`` always sends an attachment).
* ``GET  /{id}/file-info`` — file facts for the uploaded-resume page (name, size, type,
  pages, upload date, extracted text for the DOCX fallback).
* ``POST /{id}/file`` — replace the original file. The new file becomes a new version
  (``change_source=USER``); the previous version rows keep their ``file_path`` and the old
  file stays on disk, so nothing is lost.
* ``POST /{id}/edit-copy`` — a CREATED copy for the editor, so the original upload is never
  modified (``/duplicate`` keeps ``kind`` and the shared file).

Security: ownership through ``service.get_resume`` (another user's id is a 404), the file
path only ever comes from the database (never from the request) and must resolve inside the
upload root, uploads are size-capped while streaming and sniffed on magic bytes, not just
the extension (``storage.validate_upload``). No model change, no migration.
"""
from __future__ import annotations

import io
import logging
import re
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError, RateLimitedError, ValidationFailed
from app.core.rate_limit import rate_limiter
from app.models.enums import Actor, ResumeChangeSource, ResumeKind, ResumeParseStatus
from app.models.resume import Resume, ResumeVersion
from app.models.user import User
from app.modules.ai.schemas import ParsedResume
from app.modules.resumes import service, storage
from app.modules.resumes.schemas import ResumeRead

logger = logging.getLogger(__name__)

router = APIRouter()

#: Replacing a file re-runs extraction and parsing; per user per minute.
REPLACE_PER_MINUTE = 20
#: The DOCX fallback shows the extracted text; more than this is never useful on screen.
TEXT_PREVIEW_MAX_CHARS = 60_000


class ResumeFileInfo(BaseModel):
    """Facts about the original file of an uploaded resume."""

    resume_id: uuid.UUID
    has_file: bool
    #: The stored bytes are gone (deleted outside the app); download and preview will 404.
    file_missing: bool = False
    original_filename: str | None = None
    mime_type: str | None = None
    format: Literal["pdf", "docx"] | None = None
    size_bytes: int | None = None
    #: PDF: number of pages; DOCX: Word's own count from ``docProps/app.xml`` when present.
    page_count: int | None = None
    #: PDF protected with a password (or encryption the reader could not open).
    encrypted: bool = False
    #: When the current file was uploaded (the first version that carries it).
    uploaded_at: datetime | None = None
    #: How many earlier files this resume had (each replace keeps the previous one in its version).
    previous_files: int = 0
    #: True when a browser can show the file inline (PDF that is not password protected).
    previewable: bool = False
    parse_status: ResumeParseStatus
    #: Extracted plain text (capped) — what the DOCX fallback shows and what scoring reads.
    extracted_text: str | None = None
    text_truncated: bool = False


class EditCopyRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)


# --------------------------------------------------------------------------- helpers


def _limit(user: User, bucket: str, per_minute: int) -> None:
    allowed, _ = rate_limiter.check(f"resumes:{bucket}:{user.id}", per_minute, 60)
    if not allowed:
        raise RateLimitedError("Too many requests for this feature. Try again in a minute.")


def _stored_path(resume: Resume) -> Path:
    """The resume's file on disk, refusing anything outside the upload root.

    The path comes from the database, never from the request; the containment check is
    defence in depth against a row edited by hand or a changed ``UPLOAD_DIR``.
    """
    if not resume.file_path:
        raise NotFoundError("This resume has no uploaded file.", code="no_file")
    path = Path(resume.file_path).resolve()
    root = storage.upload_root()
    try:
        path.relative_to(root)
    except ValueError:
        logger.warning("Resume %s points outside the upload root; refusing to serve it", resume.id)
        raise NotFoundError("The stored resume file is missing; upload it again.", code="file_missing") from None
    if not path.is_file():
        raise NotFoundError("The stored resume file is missing; upload it again.", code="file_missing")
    return path


def _format_of(resume: Resume) -> Literal["pdf", "docx"] | None:
    mime = (resume.mime_type or "").lower()
    if mime == storage.PDF_MIME:
        return "pdf"
    if mime == storage.DOCX_MIME:
        return "docx"
    suffix = Path(resume.original_filename or resume.file_path or "").suffix.lower()
    return "pdf" if suffix == ".pdf" else "docx" if suffix == ".docx" else None


def pdf_facts(content: bytes) -> tuple[int | None, bool]:
    """``(page_count, locked)`` — ``locked`` when the PDF needs a password to open.

    A PDF with only an *owner* password (print/copy restrictions, empty user password) opens
    in every viewer, so it is not locked.
    """
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - dependency is pinned
        return None, False
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    return None, True
            except Exception:  # noqa: BLE001 - unsupported crypto: treat as locked
                return None, True
        return len(reader.pages), False
    except Exception:  # noqa: BLE001 - pypdf raises many error types; facts are best effort
        return None, False


_DOCX_PAGES_RE = re.compile(rb"<(?:\w+:)?Pages>\s*(\d{1,5})\s*</(?:\w+:)?Pages>")


def docx_page_count(content: bytes) -> int | None:
    """Word's own page count (``docProps/app.xml``), when the file carries one."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            info = archive.getinfo("docProps/app.xml")
            if info.file_size > 512 * 1024:  # a real app.xml is a few kB; refuse zip bombs
                return None
            match = _DOCX_PAGES_RE.search(archive.read(info))
    except (KeyError, zipfile.BadZipFile, OSError):
        return None
    if not match:
        return None
    pages = int(match.group(1))
    return pages if pages > 0 else None


def _first_upload_of_current_file(db: Session, resume: Resume) -> datetime | None:
    stmt = (
        select(ResumeVersion.created_at)
        .where(ResumeVersion.resume_id == resume.id, ResumeVersion.file_path == resume.file_path)
        .order_by(ResumeVersion.version_number.asc())
        .limit(1)
    )
    return db.scalar(stmt) or resume.created_at


def _previous_file_count(db: Session, resume: Resume) -> int:
    paths = {
        p
        for p in db.scalars(select(ResumeVersion.file_path).where(ResumeVersion.resume_id == resume.id))
        if p and p != resume.file_path
    }
    return len(paths)


def _content_disposition(kind: str, filename: str) -> str:
    ascii_name = filename.encode("ascii", "ignore").decode("ascii").replace('"', "").strip() or "resume"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


# --------------------------------------------------------------------------- endpoints


@router.get("/{resume_id}/file", summary="The original uploaded file (inline preview or download)")
def get_original_file(
    resume_id: uuid.UUID,
    disposition: Literal["inline", "attachment"] = Query(
        default="inline", description="`inline` for the in-app preview, `attachment` to download"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Owner-only (another user's id is a 404). Only the stored PDF/DOCX is ever served, with
    its stored content type and ``nosniff``; a resume without a file is a 404 ``no_file``."""
    resume = service.get_resume(db, user.id, resume_id)
    path = _stored_path(resume)
    fmt = _format_of(resume)
    mime = storage.ALLOWED_EXTENSIONS.get(fmt or "", "application/octet-stream")
    filename = storage.safe_download_name(resume.original_filename, fmt)
    if disposition == "attachment":
        audit(
            db,
            action="resume.downloaded",
            message=f"Resume downloaded: {resume.name}",
            user_id=user.id,
            actor=Actor.USER,
            meta={"resume_id": str(resume.id), "via": "file"},
        )
    return Response(
        content=path.read_bytes(),
        media_type=mime,
        headers={
            "Content-Disposition": _content_disposition(disposition, filename),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{resume_id}/file-info", response_model=ResumeFileInfo, summary="Facts about the original file")
def get_file_info(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeFileInfo:
    resume = service.get_resume(db, user.id, resume_id)
    text = resume.text_content or None
    truncated = bool(text and len(text) > TEXT_PREVIEW_MAX_CHARS)
    info = ResumeFileInfo(
        resume_id=resume.id,
        has_file=bool(resume.file_path),
        original_filename=resume.original_filename,
        mime_type=resume.mime_type,
        format=_format_of(resume) if resume.file_path else None,
        size_bytes=resume.size_bytes,
        parse_status=resume.parse_status,
        extracted_text=text[:TEXT_PREVIEW_MAX_CHARS] if text else None,
        text_truncated=truncated,
    )
    if not resume.file_path:
        return info
    info.uploaded_at = _first_upload_of_current_file(db, resume)
    info.previous_files = _previous_file_count(db, resume)
    try:
        content = _stored_path(resume).read_bytes()
    except NotFoundError:
        info.file_missing = True
        return info
    if info.format == "pdf":
        info.page_count, info.encrypted = pdf_facts(content)
        info.previewable = not info.encrypted
    elif info.format == "docx":
        info.page_count = docx_page_count(content)
    return info


@router.post("/{resume_id}/file", response_model=ResumeRead, summary="Replace the original file (new version)")
def replace_original_file(
    resume_id: uuid.UUID,
    file: UploadFile = File(..., description="The new PDF or DOCX"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    """Store the new file, read and parse it, and save it as a new version (``USER``). The
    previous version keeps the previous file, so restoring that version restores its data and
    the old file stays downloadable from the history."""
    resume = service.get_resume(db, user.id, resume_id)
    if resume.kind != ResumeKind.UPLOADED:
        raise ValidationFailed(
            "Only an uploaded resume has an original file to replace. Upload the new file as a new resume instead.",
            code="not_uploaded",
        )
    _limit(user, "replace-file", REPLACE_PER_MINUTE)
    filename = file.filename or "resume"
    content = storage.read_within_limit(file.file)
    ext, _mime = storage.validate_upload(filename, content)  # extension + magic bytes + size
    if ext == "pdf" and pdf_facts(content)[1]:
        raise ValidationFailed(
            "That PDF is password protected. Save an unprotected copy (Print → Save as PDF) and upload that.",
            code="encrypted_pdf",
        )
    sha = storage.sha256_bytes(content)
    if resume.sha256 and sha == resume.sha256:
        raise ValidationFailed("That is the file you already uploaded.", code="same_file")

    stored = storage.save_resume_file(user.id, content, ext)
    old_name = resume.original_filename or "the previous file"
    resume.file_path = stored.path
    resume.original_filename = Path(filename).name[:255]
    resume.mime_type = stored.mime_type
    resume.size_bytes = stored.size_bytes
    resume.sha256 = stored.sha256
    service._parse_into(resume, content, ext)  # noqa: SLF001 - same package; records parse failures on the row
    resume.current_version = int(resume.current_version or 1) + 1
    db.add(resume)
    db.flush()
    service._add_version(  # noqa: SLF001 - same package
        db,
        resume,
        note=f"Replaced the original file: {old_name} → {resume.original_filename}",
        change_source=ResumeChangeSource.USER,
    )
    service._invalidate(resume.id)  # noqa: SLF001 - same package
    audit(
        db,
        action="resume.file_replaced",
        message=f"Resume file replaced: {resume.name} ({resume.original_filename})",
        user_id=user.id,
        actor=Actor.USER,
        meta={
            "resume_id": str(resume.id),
            "version": resume.current_version,
            "size_bytes": resume.size_bytes,
            "parse_status": resume.parse_status.value,
        },
    )
    db.flush()
    return service.resume_to_read(resume)


@router.post(
    "/{resume_id}/edit-copy",
    response_model=ResumeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Copy an uploaded resume into the editor (the original stays untouched)",
)
def edit_copy(
    resume_id: uuid.UUID,
    payload: EditCopyRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    """A CREATED resume with the original's structured data, template and target role,
    linked back through ``source_resume_id``. Editing it never touches the uploaded file or
    the uploaded resume's versions."""
    source = service.get_resume(db, user.id, resume_id)
    parsed = ParsedResume.model_validate(source.parsed_data or {})
    name = ((payload.name if payload else None) or "").strip() or f"{source.name} (edited copy)"
    copy_ = service.create_resume_from_parsed(
        db,
        user.id,
        parsed,
        name=name[:255],
        kind=ResumeKind.CREATED,
        target_role=source.target_role,
        template=source.template or "classic",
        source_resume_id=source.id,
        set_default=False,
        note=f"Copied from {source.name} v{int(source.current_version or 1)} for editing",
        change_source=ResumeChangeSource.SYSTEM,
    )
    audit(
        db,
        action="resume.copied_for_editing",
        message=f"Resume copied for editing: {source.name} -> {copy_.name}",
        user_id=user.id,
        actor=Actor.USER,
        meta={"resume_id": str(copy_.id), "source_resume_id": str(source.id), "source_version": source.current_version},
    )
    db.flush()
    return service.resume_to_read(copy_)
