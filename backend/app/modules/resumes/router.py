"""Resumes router — mounted at ``/api/v1/resumes`` by ``app.main`` (CONTRACTS.md §7).

Thin by design: validation lives in ``storage``/``schemas`` and every write goes
through ``service``.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.models.enums import Actor
from app.models.user import User
from app.modules.resumes import service, storage
from app.modules.resumes.schemas import ParsedResume, ResumeRead, ResumeUpdate, ResumeVersionRead

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ResumeRead, status_code=status.HTTP_201_CREATED, summary="Upload a resume")
@router.post("/", response_model=ResumeRead, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def upload_resume(
    file: UploadFile = File(..., description="PDF or DOCX resume"),
    name: str | None = Form(default=None),
    target_role: str | None = Form(default=None),
    set_default: bool = Form(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    """Store, extract and parse a resume. Parsing failures still return 201 with
    ``parse_status=FAILED`` so the user can edit the data by hand."""
    content = file.file.read()
    resume = service.create_resume_from_bytes(
        db,
        user.id,
        file.filename or "resume",
        content,
        name=name,
        target_role=target_role,
        set_default=set_default,
    )
    db.flush()
    return service.resume_to_read(resume)


@router.get("", response_model=list[ResumeRead], summary="List your resumes")
@router.get("/", response_model=list[ResumeRead], include_in_schema=False)
def list_resumes(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ResumeRead]:
    return [service.resume_to_read(r) for r in service.list_resumes(db, user.id)]


@router.get("/{resume_id}", response_model=ResumeRead, summary="Get one resume")
def get_resume(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    return service.resume_to_read(service.get_resume(db, user.id, resume_id))


@router.patch("/{resume_id}", response_model=ResumeRead, summary="Rename / retarget / set default")
def patch_resume(
    resume_id: uuid.UUID,
    payload: ResumeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    resume = service.update_resume(
        db,
        user.id,
        resume_id,
        name=payload.name,
        target_role=payload.target_role,
        is_default=payload.is_default,
    )
    return service.resume_to_read(resume)


@router.put("/{resume_id}/parsed-data", response_model=ResumeRead, summary="Save edited parsed data (new version)")
def put_parsed_data(
    resume_id: uuid.UUID,
    payload: ParsedResume,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    return service.resume_to_read(service.update_parsed_data(db, user.id, resume_id, payload))


@router.post("/{resume_id}/reparse", response_model=ResumeRead, summary="Re-run extraction and parsing")
def reparse_resume(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    return service.resume_to_read(service.reparse(db, user.id, resume_id))


@router.get("/{resume_id}/versions", response_model=list[ResumeVersionRead], summary="Version history")
def list_versions(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ResumeVersionRead]:
    return [service.version_to_read(v) for v in service.list_versions(db, user.id, resume_id)]


@router.get("/{resume_id}/download", summary="Download the original file")
def download_resume(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    """Stream the stored file. Owner-only: another user's id returns 404."""
    resume = service.get_resume(db, user.id, resume_id)
    if not storage.file_exists(resume.file_path):
        raise NotFoundError("The stored resume file is missing; upload it again.")
    audit(
        db,
        action="resume.downloaded",
        message=f"Resume downloaded: {resume.name}",
        user_id=user.id,
        actor=Actor.USER,
        meta={"resume_id": str(resume.id)},
    )
    return FileResponse(
        path=resume.file_path,
        media_type=resume.mime_type or "application/octet-stream",
        filename=storage.safe_download_name(resume.original_filename),
    )


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a resume")
def delete_resume(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    service.delete_resume(db, user.id, resume_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
