"""Resumes router — mounted at ``/api/v1/resumes`` by ``app.main`` (CONTRACTS.md §7).

Thin by design: validation lives in ``storage``/``schemas`` and every write goes
through ``service`` (or ``importers`` / ``writing``, which call ``service``).

Static paths (``/templates``, ``/summary``, ``/history`` …) are declared before
``/{resume_id}`` so they are never read as an id.
"""
from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError, RateLimitedError, ValidationFailed
from app.core.rate_limit import rate_limiter
from app.models.enums import Actor, ResumeChangeSource
from app.models.user import User
from app.modules.resumes import apply, importers, service, storage, templates, writing
from app.modules.resumes.schemas import (
    AchievementRequest,
    ApplyPlan,
    ApplyRequest,
    ApplyResult,
    BulletSuggestions,
    DraftSummaryRequest,
    HistoryPage,
    ImprovedText,
    ImproveTextRequest,
    ParsedDataSave,
    ParsedResume,
    ResumeBuildRequest,
    ResumeDiff,
    ResumeDraftRead,
    ResumeDuplicateRequest,
    ResumeImportText,
    ResumeRead,
    ResumeRecommendations,
    ResumeSummary,
    ResumeUpdate,
    ResumeVersionRead,
    RewriteBulletRequest,
    SummaryDraft,
    VersionScore,
)
from app.modules.resumes.templates import ResumeTemplate

logger = logging.getLogger(__name__)

router = APIRouter()

#: Model-backed writing help and document rendering, per user per minute.
AI_HELP_PER_MINUTE = 30
EXPORTS_PER_MINUTE = 30
LINKEDIN_MAX_FILES = 12


def _limit(user: User, bucket: str, per_minute: int) -> None:
    allowed, _ = rate_limiter.check(f"resumes:{bucket}:{user.id}", per_minute, 60)
    if not allowed:
        raise RateLimitedError("Too many requests for this feature. Try again in a minute.")


def _draft_read(resume) -> ResumeDraftRead:  # noqa: ANN001
    return ResumeDraftRead(
        resume_id=resume.id,
        draft_data=resume.draft_data,
        draft_saved_at=resume.draft_saved_at,
        current_version=int(resume.current_version or 1),
    )


def _file_response(content: bytes, mime: str, filename: str) -> Response:
    from urllib.parse import quote

    ascii_name = filename.encode("ascii", "ignore").decode("ascii").strip() or "resume"
    return Response(
        content=content,
        media_type=mime,
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# --------------------------------------------------------------------------- collection


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
    # Streamed with a hard cap: reading the whole body first would let one request
    # pin an unbounded amount of memory before the size check ever runs.
    content = storage.read_within_limit(file.file)
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
    include_archived: bool = Query(default=False, description="Include archived resumes"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ResumeRead]:
    return [service.resume_to_read(r) for r in service.list_resumes(db, user.id, include_archived=include_archived)]


@router.get("/templates", response_model=list[ResumeTemplate], summary="Resume templates (layout definitions)")
def list_templates(user: User = Depends(get_current_user)) -> list[ResumeTemplate]:
    """Data definitions shared by the live preview and the PDF/DOCX exporters."""
    return templates.list_templates()


@router.get("/prefill", response_model=ParsedResume, summary="Resume data from your profile")
def prefill(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ParsedResume:
    """Your master profile and job preferences (verified facts) as resume data, for
    "Create from profile". Nothing is saved."""
    return importers.prefill_from_profile(db, user.id)


@router.get("/summary", response_model=ResumeSummary, summary="Resume dashboard numbers")
def resume_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ResumeSummary:
    return service.summary(db, user.id)


@router.get("/history", response_model=HistoryPage, summary="Versions across all your resumes")
def resume_history(
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=20),
    resume_id: uuid.UUID | None = Query(default=None),
    change_source: ResumeChangeSource | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HistoryPage:
    """Newest first, with a one-line change summary per version (``+2 skills, 1 bullet changed``)."""
    return service.history(db, user.id, limit=limit, cursor=cursor, resume_id=resume_id, change_source=change_source)


@router.post("/build", response_model=ResumeRead, status_code=status.HTTP_201_CREATED, summary="Create a resume in the editor")
def build_resume(
    payload: ResumeBuildRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    resume = service.create_resume_from_parsed(
        db,
        user.id,
        payload.parsed_data,
        name=payload.name,
        target_role=payload.target_role,
        template=payload.template or templates.DEFAULT_TEMPLATE_ID,
        set_default=payload.set_default,
        note="Created in the editor",
    )
    db.flush()
    return service.resume_to_read(resume)


@router.post(
    "/import/text", response_model=ResumeRead, status_code=status.HTTP_201_CREATED, summary="Create a resume from pasted text"
)
def import_text(
    payload: ResumeImportText,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    _limit(user, "import", AI_HELP_PER_MINUTE)
    resume = importers.import_text(
        db, user.id, payload.text, name=payload.name, target_role=payload.target_role, template=payload.template
    )
    db.flush()
    return service.resume_to_read(resume)


@router.post(
    "/import/linkedin",
    response_model=ResumeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a resume from a LinkedIn data export",
)
def import_linkedin(
    files: list[UploadFile] = File(..., description="The LinkedIn export ZIP, or its CSV files"),
    name: str | None = Form(default=None, max_length=255),
    target_role: str | None = Form(default=None, max_length=255),
    template: str | None = Form(default=None, max_length=40),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    """Reads LinkedIn's "Get a copy of your data" export in memory. No scraping, no
    LinkedIn login; the files are not stored."""
    _limit(user, "import", AI_HELP_PER_MINUTE)
    if len(files) > LINKEDIN_MAX_FILES:
        raise ValidationFailed(f"Upload at most {LINKEDIN_MAX_FILES} files.", code="too_many_files")
    loaded = [(upload.filename or "file", storage.read_within_limit(upload.file)) for upload in files]
    resume = importers.import_linkedin(db, user.id, loaded, name=name, target_role=target_role, template=template)
    db.flush()
    return service.resume_to_read(resume)


# --------------------------------------------------------------------------- one resume


@router.get("/{resume_id}", response_model=ResumeRead, summary="Get one resume")
def get_resume(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    return service.resume_to_read(service.get_resume(db, user.id, resume_id))


@router.patch("/{resume_id}", response_model=ResumeRead, summary="Rename / retarget / set default / template")
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
        template=payload.template,
    )
    return service.resume_to_read(resume)


@router.put("/{resume_id}/parsed-data", response_model=ResumeRead, summary="Save edited parsed data (new version)")
def put_parsed_data(
    resume_id: uuid.UUID,
    payload: ParsedDataSave,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    """Saves a new version and clears the editor draft. ``note`` / ``change_source`` are optional
    (defaults: "Edited by user" / USER)."""
    resume = service.update_parsed_data(
        db,
        user.id,
        resume_id,
        payload.resume_data(),
        note=(payload.note or "").strip() or "Edited by user",
        change_source=payload.change_source or ResumeChangeSource.USER,
    )
    return service.resume_to_read(resume)


@router.get("/{resume_id}/draft", response_model=ResumeDraftRead, summary="The editor's autosaved draft")
def get_draft(resume_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ResumeDraftRead:
    return _draft_read(service.get_draft(db, user.id, resume_id))


@router.put("/{resume_id}/draft", response_model=ResumeDraftRead, summary="Autosave the editor draft (no version)")
def put_draft(
    resume_id: uuid.UUID,
    payload: ParsedResume,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeDraftRead:
    return _draft_read(service.save_draft(db, user.id, resume_id, payload))


@router.delete("/{resume_id}/draft", response_model=ResumeDraftRead, summary="Discard the editor draft")
def delete_draft(resume_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ResumeDraftRead:
    return _draft_read(service.discard_draft(db, user.id, resume_id))


@router.post(
    "/{resume_id}/duplicate", response_model=ResumeRead, status_code=status.HTTP_201_CREATED, summary="Duplicate a resume"
)
def duplicate_resume(
    resume_id: uuid.UUID,
    payload: ResumeDuplicateRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    resume = service.duplicate_resume(db, user.id, resume_id, name=payload.name if payload else None)
    db.flush()
    return service.resume_to_read(resume)


@router.post("/{resume_id}/archive", response_model=ResumeRead, summary="Archive a resume")
def archive_resume(resume_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ResumeRead:
    return service.resume_to_read(service.archive_resume(db, user.id, resume_id))


@router.post("/{resume_id}/unarchive", response_model=ResumeRead, summary="Restore a resume from the archive")
def unarchive_resume(resume_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ResumeRead:
    return service.resume_to_read(service.unarchive_resume(db, user.id, resume_id))


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


@router.get("/{resume_id}/versions/{version_number}", response_model=ResumeVersionRead, summary="One version")
def get_version(
    resume_id: uuid.UUID,
    version_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeVersionRead:
    return service.version_to_read(service.get_version(db, user.id, resume_id, version_number))


@router.get("/{resume_id}/versions/{version_number}/diff", response_model=ResumeDiff, summary="Compare two versions")
def diff_versions(
    resume_id: uuid.UUID,
    version_number: int,
    against: int | None = Query(default=None, ge=1, description="Base version (default: the previous one)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeDiff:
    """Field-level changes from ``against`` to ``version_number``."""
    return service.diff_versions(db, user.id, resume_id, version_number, against)


@router.post("/{resume_id}/versions/{version_number}/restore", response_model=ResumeRead, summary="Restore a version")
def restore_version(
    resume_id: uuid.UUID,
    version_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRead:
    """Copies that version's data into a **new** version ("Restored from v<n>"); nothing is overwritten."""
    return service.resume_to_read(service.restore_version(db, user.id, resume_id, version_number))


@router.get("/{resume_id}/diff", response_model=ResumeDiff, summary="Compare with another resume")
def diff_resumes(
    resume_id: uuid.UUID,
    against: uuid.UUID = Query(..., description="The other resume (e.g. the source of a tailored copy)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeDiff:
    """Current version of ``against`` (before) vs current version of this resume (after)."""
    return service.diff_resumes(db, user.id, resume_id, against)


@router.get("/{resume_id}/export", summary="Export as PDF or DOCX")
def export_resume(
    resume_id: uuid.UUID,
    format: Literal["pdf", "docx"] = Query(default="pdf"),  # noqa: A002 - public query name
    template: str | None = Query(default=None, max_length=40),
    version: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Rendered from the structured data with the resume's template (or ``template``)."""
    _limit(user, "export", EXPORTS_PER_MINUTE)
    content, mime, filename = service.export_resume(db, user.id, resume_id, fmt=format, template=template, version=version)
    return _file_response(content, mime, filename)


@router.get(
    "/{resume_id}/recommendations",
    response_model=ResumeRecommendations,
    summary="Resume improvement recommendations",
)
def get_recommendations(
    resume_id: uuid.UUID,
    refresh: bool = Query(default=False, description="Bypass the 10-minute cache"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeRecommendations:
    """Prioritised advice computed from the parsed resume and the user's target jobs."""
    return service.get_recommendations(db, user.id, resume_id, refresh=refresh)


@router.get(
    "/{resume_id}/recommendations/history",
    response_model=list[VersionScore],
    summary="Resume health and match score per version",
)
def get_recommendation_history(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[VersionScore]:
    return service.get_recommendation_history(db, user.id, resume_id)


@router.get(
    "/{resume_id}/recommendations/apply-plan",
    response_model=ApplyPlan,
    summary="Suggestions that can be applied to the resume",
)
def get_apply_plan(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplyPlan:
    """Applicable changes (skills, summary, bullets) and the advice that needs the user's own work.

    Changes edit the structured resume data (``parsed_data``) that matching, autofill and
    the recommendations read. The uploaded original file (PDF/DOCX) is never modified.
    """
    return apply.build_apply_plan(db, user.id, resume_id)


@router.post(
    "/{resume_id}/recommendations/apply",
    response_model=ApplyResult,
    summary="Apply selected suggestions and save a new resume version",
)
def apply_suggestions(
    resume_id: uuid.UUID,
    payload: ApplyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplyResult:
    """Apply the chosen plan changes to ``parsed_data`` and save them as a new version.

    Only the ids sent are applied, each checked against a plan rebuilt on the server.
    Errors: 409 ``stale_plan`` when ``resume_version`` is not the current version; 422
    ``unknown_change``, ``placeholder_left``, ``invented_number`` (summary text with a
    number the resume does not contain) or ``empty_text``, with ``details.id`` naming the
    change. The uploaded original file (PDF/DOCX) is not modified.
    """
    return apply.apply_changes(db, user.id, resume_id, payload)


# --------------------------------------------------------------------------- writing help


@router.post("/{resume_id}/ai/rewrite-bullet", response_model=BulletSuggestions, summary="Rewrite one bullet")
def ai_rewrite_bullet(
    resume_id: uuid.UUID,
    payload: RewriteBulletRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BulletSuggestions:
    """Up to three rewrites that keep the bullet's facts; each carries its checks. Nothing is saved."""
    _limit(user, "ai", AI_HELP_PER_MINUTE)
    resume = service.get_resume(db, user.id, resume_id)
    return writing.rewrite_bullet(db, user.id, resume, payload.text, role=payload.role, company=payload.company)


@router.post(
    "/{resume_id}/ai/responsibility-to-achievement",
    response_model=BulletSuggestions,
    summary="Turn a responsibility into an achievement bullet",
)
def ai_achievement(
    resume_id: uuid.UUID,
    payload: AchievementRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BulletSuggestions:
    """Ends in a ``[result]`` placeholder when the text states no result — never a made-up number."""
    _limit(user, "ai", AI_HELP_PER_MINUTE)
    resume = service.get_resume(db, user.id, resume_id)
    return writing.responsibility_to_achievement(db, user.id, resume, payload.text)


@router.post("/{resume_id}/ai/improve-text", response_model=ImprovedText, summary="Fix grammar and clarity")
def ai_improve_text(
    resume_id: uuid.UUID,
    payload: ImproveTextRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ImprovedText:
    """Grammar, clarity and tone only; a version that adds numbers, skills, names or dates is refused."""
    _limit(user, "ai", AI_HELP_PER_MINUTE)
    service.get_resume(db, user.id, resume_id)
    return writing.improve_text(payload.text, payload.field)


@router.post("/{resume_id}/ai/draft-summary", response_model=SummaryDraft, summary="Draft a summary from your facts")
def ai_draft_summary(
    resume_id: uuid.UUID,
    payload: DraftSummaryRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SummaryDraft:
    _limit(user, "ai", AI_HELP_PER_MINUTE)
    resume = service.get_resume(db, user.id, resume_id)
    return writing.draft_summary(db, user.id, resume, payload.parsed_data if payload else None)


# --------------------------------------------------------------------------- file


@router.get("/{resume_id}/download", summary="Download the original file")
def download_resume(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream the stored file. A resume built in JobPilot (no file) downloads as a DOCX
    rendered from its data. Owner-only: another user's id returns 404."""
    resume = service.get_resume(db, user.id, resume_id)
    if not resume.file_path:
        _limit(user, "export", EXPORTS_PER_MINUTE)
        content, mime, filename = service.export_resume(db, user.id, resume_id, fmt="docx")
        return _file_response(content, mime, filename)
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
