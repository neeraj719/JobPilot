"""ATS optimizer router - mounted at ``/api/v1/ats`` by ``app.main``.

Thin by design: every rule lives in ``jd`` / ``fetch`` / ``lookup`` / ``scoring`` /
``suggestions`` / ``service`` / ``targets``. Every score returned is an estimate
(``schemas.DISCLAIMER``).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import RateLimitedError, ValidationFailed
from app.core.rate_limit import rate_limiter
from app.models.enums import JdSource, JobTargetStatus
from app.models.user import User
from app.modules.ats import fetch as fetch_mod
from app.modules.ats import jd as jd_mod
from app.modules.ats import lookup as lookup_mod
from app.modules.ats import service, targets
from app.modules.ats.schemas import (
    AnalysisCreate,
    AnalysisListItem,
    AnalysisRead,
    ApplyRequest,
    ApplyResult,
    AtsSummary,
    AutoOptimizeRequest,
    AutoOptimizeResult,
    CompanyLookupResult,
    CompareResult,
    IgnoreRequest,
    JdFetchRequest,
    JdParseRequest,
    JdParseResult,
    Methodology,
    SnapshotCreate,
    SnapshotRead,
    TailorRequest,
    TailorResult,
    TargetCreate,
    TargetDetail,
    TargetRead,
    TargetUpdate,
    UndoResult,
)
from app.modules.ats.scoring import methodology as scoring_methodology
from app.modules.common.pagination import Pagination
from app.modules.common.schemas import PageResponse
from pydantic import BaseModel

router = APIRouter()

#: Model-backed JD refinement per user per minute (a local model is slow; a paid one costs).
AI_RATE_LIMIT_PER_MINUTE = 20


def _ai_rate_limit(user: User, use_ai: bool) -> None:
    if not use_ai:
        return
    allowed, _ = rate_limiter.check(f"ats-ai:{user.id}", AI_RATE_LIMIT_PER_MINUTE, 60)
    if not allowed:
        raise RateLimitedError("Too many AI refinements. Try again in a minute.")


def _read_upload(file: UploadFile) -> bytes:
    content = file.file.read(jd_mod.MAX_JD_UPLOAD_BYTES + 1)
    if len(content) > jd_mod.MAX_JD_UPLOAD_BYTES:
        raise ValidationFailed("The file is larger than 5 MB.", code="file_too_large")
    return content


def _parse_result(text: str, *, source: JdSource, confidence: str, title: str | None, company: str | None,
                  location: str | None = None, url: str | None = None, use_ai: bool = False,
                  warnings: list[str] | None = None, deadline=None) -> JdParseResult:
    clean = jd_mod.require_readable(jd_mod.normalize_jd_text(text))
    structured = jd_mod.build_structured(clean, title=title, company=company, location=location, use_ai=use_ai)
    if deadline is not None and structured.deadline is None:
        structured = structured.model_copy(update={"deadline": deadline})
    return JdParseResult(
        source=source,
        confidence=confidence,  # type: ignore[arg-type]
        title=structured.title,
        company=structured.company,
        location=structured.location,
        url=url,
        text=clean,
        structured=structured,
        warnings=warnings or [],
    )


# --------------------------------------------------------------------------- methodology + JD


@router.get("/methodology", response_model=Methodology, summary="How the estimated ATS score is computed")
def get_methodology(user: User = Depends(get_current_user)) -> Methodology:
    return scoring_methodology()


@router.post("/jd/parse", response_model=JdParseResult, summary="Structure a pasted job description")
def parse_jd(payload: JdParseRequest, user: User = Depends(get_current_user)) -> JdParseResult:
    _ai_rate_limit(user, payload.use_ai)
    return _parse_result(
        payload.text, source=JdSource.PASTED, confidence="high", title=payload.title, company=payload.company, use_ai=payload.use_ai
    )


@router.post("/jd/upload", response_model=JdParseResult, summary="Structure an uploaded job description (PDF, DOCX, TXT)")
def upload_jd(
    file: UploadFile = File(..., description="PDF, DOCX or TXT"),
    title: str | None = Form(default=None),
    company: str | None = Form(default=None),
    use_ai: bool = Form(default=False),
    user: User = Depends(get_current_user),
) -> JdParseResult:
    _ai_rate_limit(user, use_ai)
    text = jd_mod.extract_upload_text(file.filename or "", _read_upload(file))
    return _parse_result(text, source=JdSource.UPLOADED, confidence="medium", title=title, company=company, use_ai=use_ai)


@router.post("/jd/fetch", response_model=JdParseResult, summary="Read a job description from a posting URL or a board posting")
def fetch_jd(payload: JdFetchRequest, user: User = Depends(get_current_user)) -> JdParseResult:
    """Known vendors (Greenhouse, Lever, Ashby, SmartRecruiters) are read from their public APIs;
    other pages are fetched once under the SSRF and size guards. 422 ``jd_unreadable`` when
    nothing readable comes back - the user then pastes the text."""
    if not payload.url and payload.board is None:
        raise ValidationFailed("Give the job posting URL.", code="invalid_url")
    fetch_mod.enforce_rate_limit(user.id)
    _ai_rate_limit(user, payload.use_ai)
    if payload.board is not None:
        posting = fetch_mod.fetch_board_posting(payload.board.vendor, payload.board.token, payload.board.external_id)
    else:
        posting = fetch_mod.fetch_posting(payload.url or "")
    return _parse_result(
        posting.text, source=posting.source, confidence=posting.confidence, title=posting.title, company=posting.company,
        location=posting.location, url=posting.url, use_ai=payload.use_ai, warnings=posting.warnings, deadline=posting.deadline,
    )


@router.get("/companies/lookup", response_model=CompanyLookupResult, summary="A company's open roles from its public board")
def company_lookup(
    name: str = Query(min_length=1, max_length=255),
    role: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompanyLookupResult:
    fetch_mod.enforce_rate_limit(user.id, "lookup")
    return lookup_mod.lookup_company(db, user.id, name, role)


# --------------------------------------------------------------------------- analyses


@router.post("/analyses", response_model=AnalysisRead, status_code=status.HTTP_201_CREATED, summary="Analyse a resume against a job description")
def create_analysis(payload: AnalysisCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> AnalysisRead:
    """Deterministic estimate, returned at once. When a model is configured the suggestions are
    polished in the background: poll ``GET /ats/analyses/{id}`` while ``status`` is RUNNING."""
    return service.create_analysis(db, user.id, payload)


@router.get("/analyses", response_model=list[AnalysisListItem], summary="Your analyses")
def list_analyses(
    resume_id: uuid.UUID | None = Query(default=None),
    job_target_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AnalysisListItem]:
    return service.list_analyses(db, user.id, resume_id=resume_id, job_target_id=job_target_id, limit=limit)


@router.get("/analyses/{analysis_id}", response_model=AnalysisRead, summary="One analysis (poll while RUNNING)")
def get_analysis(analysis_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> AnalysisRead:
    return service.analysis_to_read(db, service.get_analysis(db, user.id, analysis_id))


@router.post("/analyses/{analysis_id}/apply", response_model=ApplyResult, summary="Apply suggestions (new resume version) and re-analyse")
def apply_suggestions(
    analysis_id: uuid.UUID, payload: ApplyRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ApplyResult:
    """Errors: 409 ``stale_resume``; 422 ``unknown_suggestion``, ``not_applicable``, ``edit_required``,
    ``placeholder_left``, ``invented_number``, ``empty_text`` (``details.id`` names the suggestion)."""
    return service.apply_suggestions(db, user.id, analysis_id, payload)


@router.post("/analyses/{analysis_id}/ignore", response_model=AnalysisRead, summary="Ignore (or un-ignore) suggestions")
def ignore_suggestions(
    analysis_id: uuid.UUID, payload: IgnoreRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> AnalysisRead:
    return service.ignore_suggestions(db, user.id, analysis_id, payload)


@router.post("/analyses/{analysis_id}/auto-optimize", response_model=AutoOptimizeResult, summary="Apply every safe suggestion")
def auto_optimize(
    analysis_id: uuid.UUID, payload: AutoOptimizeRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> AutoOptimizeResult:
    """``new_resume`` creates a TAILORED resume linked to its source; ``new_version`` saves a new
    version of the same resume. Suggestions that need confirmation are never applied here."""
    return service.auto_optimize(db, user.id, analysis_id, mode=payload.mode, name=payload.name)


@router.post("/analyses/{analysis_id}/undo", response_model=UndoResult, summary="Undo the apply that produced this analysis")
def undo(analysis_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> UndoResult:
    return service.undo_apply(db, user.id, analysis_id)


@router.post("/analyses/{analysis_id}/polish", response_model=AnalysisRead, summary="Retry the AI polish of the suggestions")
def retry_polish(analysis_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> AnalysisRead:
    return service.retry_polish(db, user.id, analysis_id)


# --------------------------------------------------------------------------- targets


class SnapshotResult(BaseModel):
    snapshot: SnapshotRead
    created: bool
    target: TargetRead


@router.get("/targets", response_model=PageResponse[TargetRead], summary="Your job targets")
def list_targets(
    status_filter: list[JobTargetStatus] | None = Query(default=None, alias="status"),
    company: str | None = Query(default=None, max_length=255),
    search: str | None = Query(default=None, max_length=255),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PageResponse[TargetRead]:
    return targets.list_targets(db, user.id, pagination, status=status_filter, company=company, search=search)


@router.post("/targets", response_model=TargetDetail, status_code=status.HTTP_201_CREATED, summary="Save a job target")
def create_target(payload: TargetCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> TargetDetail:
    """409 ``target_exists`` (``details.id``) when the same company, role and URL is already saved."""
    return targets.create_target(db, user.id, payload)


@router.get("/targets/{target_id}", response_model=TargetDetail, summary="One job target with its JD, analysis and activity")
def get_target(target_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> TargetDetail:
    return targets.get_detail(db, user.id, target_id)


@router.patch("/targets/{target_id}", response_model=TargetDetail, summary="Update a job target (status changes are audited)")
def update_target(
    target_id: uuid.UUID, payload: TargetUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> TargetDetail:
    return targets.update_target(db, user.id, target_id, payload)


@router.delete("/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a job target")
def delete_target(target_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    targets.delete_target(db, user.id, target_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/targets/{target_id}/snapshot", response_model=SnapshotResult, summary="Save a new job description for a target")
def add_snapshot(
    target_id: uuid.UUID, payload: SnapshotCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> SnapshotResult:
    target = service.get_target(db, user.id, target_id)
    _ai_rate_limit(user, payload.use_ai)
    snapshot, created = targets.add_snapshot(db, user.id, target, payload)
    return SnapshotResult(snapshot=SnapshotRead.model_validate(snapshot), created=created, target=targets.target_read(db, target))


@router.post("/targets/{target_id}/snapshot/upload", response_model=SnapshotResult, summary="Upload a job description for a target")
def upload_snapshot(
    target_id: uuid.UUID,
    file: UploadFile = File(...),
    use_ai: bool = Form(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SnapshotResult:
    target = service.get_target(db, user.id, target_id)
    _ai_rate_limit(user, use_ai)
    text = jd_mod.extract_upload_text(file.filename or "", _read_upload(file))
    snapshot, created = service.snapshot_from_text(
        db, user.id, text=text, source=JdSource.UPLOADED, title=target.role_title, company=target.company_name,
        url=target.job_url, location=target.location, use_ai=use_ai, target=target,
    )
    return SnapshotResult(snapshot=SnapshotRead.model_validate(snapshot), created=created, target=targets.target_read(db, target))


@router.post("/targets/{target_id}/refresh", response_model=SnapshotResult, summary="Re-fetch the job description from the posting URL")
def refresh_target(target_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> SnapshotResult:
    snapshot, created = targets.refresh_target(db, user.id, target_id)
    target = service.get_target(db, user.id, target_id)
    return SnapshotResult(snapshot=SnapshotRead.model_validate(snapshot), created=created, target=targets.target_read(db, target))


@router.post("/targets/{target_id}/tailor", response_model=TailorResult, summary="Tailor a resume to this target")
def tailor(
    target_id: uuid.UUID, payload: TailorRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> TailorResult:
    """Analysis of the source resume, then a TAILORED copy with every safe change applied and
    explained; the target moves Preparing → Ready."""
    return targets.tailor(db, user.id, target_id, payload)


@router.get("/targets/{target_id}/compare", response_model=CompareResult, summary="Source vs tailored resume, with the changes explained")
def compare(target_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> CompareResult:
    return targets.compare(db, user.id, target_id)


@router.get("/summary", response_model=AtsSummary, summary="Targets by status, recent analyses, tailoring in progress")
def get_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> AtsSummary:
    return targets.summary(db, user.id)
