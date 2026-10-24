"""Job targets: saved opportunities, their JD snapshots, tailoring and status tracking.

A target is one company + role (+ posting URL). Its uniqueness key is ``fingerprint``
(sha256 of the normalised company, the normalised role and the normalised URL), enforced by a
partial unique index, so the same posting is not saved twice but a deleted one can come back.

The one-screen flow (``quick_tailor``, ``POST /ats/targets/tailor``) creates the target from a
pasted job description: company and role come from the request, else from the JD (``Unknown
company`` / the JD title / ``Untitled role``). When either was derived, the JD text hash joins
the fingerprint, so two different pasted postings never collide while the same one pasted twice
is still ``target_exists``.

Status changes are audited (``ats.target_status_changed``). Moving to APPLIED records which
resume version was sent (``submitted_resume_version``: the tailored resume's current version,
else the source resume's) and links the JobPilot application for the same job when there is
one (read-only lookup; nothing in ``applications`` is changed).
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse, urlunparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.database import soft_delete
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.models.application import Application
from app.models.ats import AtsAnalysis, JobDescriptionSnapshot, JobTarget, OptimizationSuggestion
from app.models.audit import AuditLog
from app.models.base import utcnow
from app.models.enums import Actor, AtsAnalysisStatus, JdSource, JobTargetStatus, SuggestionKind
from app.models.job import Job
from app.models.resume import Resume
from app.modules.ats import fetch as fetch_mod
from app.modules.ats import llm
from app.modules.ats import service as ats
from app.modules.ats.schemas import (
    ActivityItem,
    AtsSummary,
    CompareResult,
    CompareSide,
    DiffSummary,
    Explanation,
    FieldChange,
    KeywordMiss,
    ResumeRef,
    SnapshotCreate,
    SnapshotRead,
    StructuredJD,
    QuickTailorRequest,
    TailorChange,
    TailorRequest,
    TailorResult,
    TargetCreate,
    TargetDetail,
    TargetRead,
    TargetUpdate,
)
from app.modules.common.pagination import Pagination, paginate_sequence
from app.modules.common.schemas import PageResponse
from app.modules.resumes import service as resumes

logger = logging.getLogger(__name__)

#: Status changes that mean "the tailored resume is being or has been prepared".
_PREP_STATUSES = (JobTargetStatus.SAVED, JobTargetStatus.PREPARING, JobTargetStatus.READY)
UPCOMING_DAYS = 14


# --------------------------------------------------------------------------- keys


def _normalize_company(name: str) -> str:
    from app.modules.companies.service import normalize_company_name

    return normalize_company_name(name)


def _normalize_url(url: str | None) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    path = parsed.path.rstrip("/")
    return urlunparse(("", host, path, "", parsed.query, "")).lstrip("/")


def fingerprint(company: str, role: str, url: str | None, extra: str | None = None) -> str:
    """Uniqueness key of a target. ``extra`` (the JD text hash) is added when company or role
    were derived from the posting rather than typed (``quick_tailor``)."""
    parts = [_normalize_company(company), " ".join(role.lower().split()), _normalize_url(url)]
    if extra:
        parts.append(f"jd:{extra}")
    key = "|".join(parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


#: Fallbacks of the one-screen flow when the job description names no company / no title.
UNKNOWN_COMPANY = "Unknown company"
UNTITLED_ROLE = "Untitled role"


def _clean_url(url: str | None) -> str | None:
    text = (url or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = f"https://{text}"
    if urlparse(text).scheme.lower() not in ("http", "https"):
        raise ValidationFailed("The job URL must be an http(s) link.", code="invalid_url")
    return text[:2048]


# --------------------------------------------------------------------------- reading


def _resume_ref(resume: Resume | None) -> ResumeRef | None:
    if resume is None:
        return None
    return ResumeRef(
        id=resume.id,
        name=resume.name,
        kind=str(getattr(resume.kind, "value", resume.kind)),
        current_version=int(resume.current_version or 1),
        archived=resume.archived_at is not None,
    )


def _missing_requirements(analysis: AtsAnalysis | None) -> list[str]:
    if analysis is None:
        return []
    out = []
    for item in analysis.missing_keywords or []:
        try:
            miss = KeywordMiss.model_validate(item)
        except Exception:  # noqa: BLE001
            continue
        if miss.kind == "skill" and miss.required:
            out.append(miss.keyword)
    return out[:12]


def to_read(target: JobTarget, *, resumes_by_id: dict[uuid.UUID, Resume], analyses_by_id: dict[uuid.UUID, AtsAnalysis]) -> TargetRead:
    analysis = analyses_by_id.get(target.last_analysis_id) if target.last_analysis_id else None
    return TargetRead(
        id=target.id,
        company_name=target.company_name,
        company_id=target.company_id,
        role_title=target.role_title,
        job_url=target.job_url,
        location=target.location,
        work_mode=target.work_mode,
        required_skills=[str(s) for s in target.required_skills or []],
        deadline=target.deadline,
        status=target.status,
        notes=target.notes,
        follow_up_at=target.follow_up_at,
        source_resume=_resume_ref(resumes_by_id.get(target.source_resume_id)) if target.source_resume_id else None,
        tailored_resume=_resume_ref(resumes_by_id.get(target.tailored_resume_id)) if target.tailored_resume_id else None,
        tailored_resume_version=target.tailored_resume_version,
        submitted_resume_version=target.submitted_resume_version,
        application_id=target.application_id,
        job_id=target.job_id,
        latest_snapshot_id=target.latest_snapshot_id,
        last_analysis_id=target.last_analysis_id,
        last_score=analysis.overall_score if analysis else None,
        last_analyzed_at=target.last_analyzed_at,
        missing_requirements=_missing_requirements(analysis),
        created_at=target.created_at,
        updated_at=target.updated_at,
    )


def reads(db: Session, targets: list[JobTarget]) -> list[TargetRead]:
    resume_ids = {i for t in targets for i in (t.source_resume_id, t.tailored_resume_id) if i}
    analysis_ids = {t.last_analysis_id for t in targets if t.last_analysis_id}
    resumes_by_id = {r.id: r for r in db.scalars(select(Resume).where(Resume.id.in_(resume_ids)))} if resume_ids else {}
    analyses_by_id = {a.id: a for a in db.scalars(select(AtsAnalysis).where(AtsAnalysis.id.in_(analysis_ids)))} if analysis_ids else {}
    return [to_read(t, resumes_by_id=resumes_by_id, analyses_by_id=analyses_by_id) for t in targets]


def target_read(db: Session, target: JobTarget) -> TargetRead:
    db.flush()
    db.refresh(target)
    return reads(db, [target])[0]


def list_targets(
    db: Session,
    user_id: uuid.UUID,
    pagination: Pagination,
    *,
    status: list[JobTargetStatus] | None = None,
    company: str | None = None,
    search: str | None = None,
) -> PageResponse[TargetRead]:
    stmt = select(JobTarget).where(JobTarget.user_id == user_id)
    if status:
        stmt = stmt.where(JobTarget.status.in_(status))
    if company and company.strip():
        key = _normalize_company(company)
        stmt = stmt.where(JobTarget.normalized_company == key) if key else stmt
    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(JobTarget.company_name).like(like), func.lower(JobTarget.role_title).like(like)))
    rows = list(db.scalars(stmt.order_by(JobTarget.updated_at.desc(), JobTarget.id)))
    page = paginate_sequence(rows, pagination)
    return PageResponse[TargetRead](items=reads(db, list(page.items)), total=page.total, page=page.page, page_size=page.page_size)


def _snapshot_read(snapshot: JobDescriptionSnapshot) -> SnapshotRead:
    return SnapshotRead.model_validate(snapshot)


def _activity(db: Session, user_id: uuid.UUID, target: JobTarget, snapshots: list[JobDescriptionSnapshot]) -> list[ActivityItem]:
    items: list[ActivityItem] = [ActivityItem(at=target.created_at, kind="created", message=f"Saved {target.role_title} at {target.company_name}")]
    for snap in snapshots:
        if snap.changed_from_previous:
            changes = snap.changes or {}
            moved = sum(len(changes.get(k) or []) for k in ("added_required", "removed_required", "added_preferred", "removed_preferred"))
            message = f"Job description updated ({snap.source.value.lower()}): {moved} requirement change{'s' if moved != 1 else ''}"
        else:
            message = f"Job description saved ({snap.source.value.lower()})"
        items.append(ActivityItem(at=snap.created_at, kind="snapshot", message=message, ref_id=snap.id))
    analyses = db.scalars(
        select(AtsAnalysis).where(AtsAnalysis.user_id == user_id, AtsAnalysis.job_target_id == target.id).order_by(AtsAnalysis.created_at.desc()).limit(30)
    )
    names = {}
    for analysis in analyses:
        if analysis.resume_id not in names:
            resume = db.get(Resume, analysis.resume_id)
            names[analysis.resume_id] = resume.name if resume else "a resume"
        items.append(
            ActivityItem(
                at=analysis.created_at,
                kind="analysis",
                message=f"Analysed {names[analysis.resume_id]} v{analysis.resume_version}: {analysis.overall_score}/100 (estimated)",
                ref_id=analysis.id,
            )
        )
    logs = db.scalars(
        select(AuditLog)
        .where(AuditLog.user_id == user_id, AuditLog.action.in_(("ats.target_status_changed", "ats.target_tailored", "ats.target_updated")))
        .order_by(AuditLog.created_at.desc())
        .limit(300)
    )
    kinds = {"ats.target_status_changed": "status", "ats.target_tailored": "tailored", "ats.target_updated": "note"}
    for log in logs:
        if (log.meta or {}).get("target_id") == str(target.id):
            items.append(ActivityItem(at=log.created_at, kind=kinds.get(log.action, "note"), message=log.message))  # type: ignore[arg-type]
    items.sort(key=lambda item: item.at, reverse=True)
    return items[:60]


def get_detail(db: Session, user_id: uuid.UUID, target_id: uuid.UUID) -> TargetDetail:
    target = ats.get_target(db, user_id, target_id)
    base = reads(db, [target])[0]
    snapshots = list(
        db.scalars(
            select(JobDescriptionSnapshot)
            .where(JobDescriptionSnapshot.user_id == user_id, JobDescriptionSnapshot.job_target_id == target.id)
            .order_by(JobDescriptionSnapshot.created_at.desc())
            .limit(20)
        )
    )
    latest = next((s for s in snapshots if s.id == target.latest_snapshot_id), None)
    if latest is None and target.latest_snapshot_id:
        latest = db.get(JobDescriptionSnapshot, target.latest_snapshot_id)
    analysis = db.get(AtsAnalysis, target.last_analysis_id) if target.last_analysis_id else None
    return TargetDetail(
        **base.model_dump(),
        latest_snapshot=_snapshot_read(latest) if latest else None,
        snapshots=[_snapshot_read(s) for s in snapshots],
        last_analysis=ats.analysis_to_read(db, analysis) if analysis else None,
        activity=_activity(db, user_id, target, snapshots),
    )


# --------------------------------------------------------------------------- writes


def _check_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID | None) -> uuid.UUID | None:
    if resume_id is None:
        return None
    return resumes.get_resume(db, user_id, resume_id).id


def _ensure_unique(db: Session, user_id: uuid.UUID, key: str, *, exclude: uuid.UUID | None = None) -> None:
    stmt = select(JobTarget).where(JobTarget.user_id == user_id, JobTarget.fingerprint == key)
    if exclude:
        stmt = stmt.where(JobTarget.id != exclude)
    existing = db.scalar(stmt)
    if existing is not None:
        raise ConflictError(
            f"You already saved {existing.role_title} at {existing.company_name}.",
            code="target_exists",
            details={"id": str(existing.id)},
        )


def add_snapshot(
    db: Session, user_id: uuid.UUID, target: JobTarget, payload: SnapshotCreate
) -> tuple[JobDescriptionSnapshot, bool]:
    """A snapshot from pasted text, the posting URL or a board posting (fetched now)."""
    if payload.source == "PASTED":
        if not (payload.text or "").strip():
            raise ValidationFailed("Paste the job description text.", code="jd_required")
        return ats.snapshot_from_text(
            db, user_id, text=payload.text or "", source=JdSource.PASTED, title=payload.title or target.role_title,
            company=target.company_name, url=target.job_url, location=target.location, structured=payload.structured,
            use_ai=payload.use_ai, target=target,
        )
    fetch_mod.enforce_rate_limit(user_id)
    if payload.source == "BOARD":
        if payload.board is None:
            raise ValidationFailed("Choose a posting from the company's board.", code="board_required")
        posting = fetch_mod.fetch_board_posting(payload.board.vendor, payload.board.token, payload.board.external_id)
    else:
        url = payload.url or target.job_url
        if not url:
            raise ValidationFailed("Give the job posting's URL.", code="invalid_url")
        posting = fetch_mod.fetch_posting(url)
    snapshot, created = ats.snapshot_from_text(
        db, user_id, text=posting.text, source=posting.source, title=payload.title or posting.title or target.role_title,
        company=posting.company or target.company_name, url=posting.url, location=posting.location or target.location,
        use_ai=payload.use_ai, target=target,
    )
    if created and posting.deadline and target.deadline is None:
        target.deadline = posting.deadline
    if not target.job_url and posting.url:
        target.job_url = posting.url[:2048]
    db.add(target)
    return snapshot, created


def create_target(
    db: Session,
    user_id: uuid.UUID,
    payload: TargetCreate,
    *,
    fingerprint_extra: str | None = None,
    link_company: bool = True,
) -> TargetDetail:
    """Save a target. ``fingerprint_extra`` / ``link_company`` serve :func:`quick_tailor` (a derived
    company/role adds the JD hash to the key; ``Unknown company`` is never linked to a company row)."""
    job: Job | None = None
    company_name = " ".join((payload.company_name or "").split())
    role = " ".join((payload.role_title or "").split())
    job_url = _clean_url(payload.job_url)
    location, work_mode = payload.location, payload.work_mode
    required = list(payload.required_skills or [])
    if payload.job_id:
        job = db.get(Job, payload.job_id)
        if job is None:
            raise NotFoundError("Job not found")
        company_name = company_name or (job.company.name if job.company is not None else "")
        role = role or job.title
        job_url = job_url or _clean_url(job.canonical_url or job.apply_url)
        location = location or job.location
        work_mode = work_mode or job.work_mode
        required = required or [str(s) for s in job.required_skills or []]
    snapshot = ats.get_snapshot(db, user_id, payload.snapshot_id) if payload.snapshot_id else None
    analysis = ats.get_analysis(db, user_id, payload.analysis_id) if payload.analysis_id else None
    if snapshot is not None:
        company_name = company_name or " ".join((snapshot.company or "").split())
        role = role or " ".join((snapshot.title or "").split())
        job_url = job_url or _clean_url(snapshot.url)
    if not company_name or not role:
        raise ValidationFailed("Give the company name and the role.", code="target_incomplete")
    normalized = _normalize_company(company_name)
    if not normalized:
        raise ValidationFailed("Company name is required", code="invalid_company_name")
    key = fingerprint(company_name, role, job_url, fingerprint_extra)
    _ensure_unique(db, user_id, key)
    from app.modules.companies.service import find_company_by_name

    company = find_company_by_name(db, company_name) if link_company else None
    target = JobTarget(
        user_id=user_id,
        company_name=company_name[:255],
        normalized_company=normalized[:255],
        company_id=company.id if company else None,
        role_title=role[:255],
        job_url=job_url,
        fingerprint=key,
        location=(location or "")[:255] or None,
        work_mode=work_mode,
        required_skills=required[:60],
        deadline=payload.deadline,
        status=payload.status,
        notes=payload.notes,
        follow_up_at=payload.follow_up_at,
        source_resume_id=_check_resume(db, user_id, payload.source_resume_id or (analysis.resume_id if analysis else None)),
        job_id=job.id if job else None,
    )
    db.add(target)
    db.flush()
    if snapshot is not None:
        if snapshot.job_target_id is None:
            snapshot.job_target_id = target.id
            structured = StructuredJD.model_validate(snapshot.structured or {})
            target.latest_snapshot_id = snapshot.id
            target.required_skills = list(structured.required_skills)
            target.location = target.location or structured.location
            target.work_mode = target.work_mode or structured.work_mode
            target.deadline = target.deadline or structured.deadline
            db.add(snapshot)
        else:  # the snapshot belongs to another target: this one gets its own copy
            ats.create_snapshot(
                db, user_id, text=snapshot.raw_text, source=snapshot.source,
                structured=StructuredJD.model_validate(snapshot.structured or {}), url=snapshot.url,
                title=snapshot.title, company=snapshot.company, target=target,
            )
    if analysis is not None:
        if analysis.job_target_id is None:
            analysis.job_target_id = target.id
            db.add(analysis)
        target.last_analysis_id = analysis.id
        target.last_analyzed_at = analysis.created_at
    db.add(target)
    db.flush()
    audit(
        db,
        action="ats.target_created",
        message=f"Job target saved: {target.role_title} at {target.company_name}",
        user_id=user_id,
        actor=Actor.USER,
        meta={"target_id": str(target.id), "job_id": str(job.id) if job else None},
    )
    if payload.jd is not None:
        add_snapshot(db, user_id, target, payload.jd)
    elif job is not None and len((job.description or "").strip()) >= 120:
        ats.snapshot_from_job(db, user_id, job, target=target)
    return get_detail(db, user_id, target.id)


def _submitted_version(db: Session, target: JobTarget) -> int | None:
    resume_id = target.tailored_resume_id or target.source_resume_id
    resume = db.get(Resume, resume_id) if resume_id else None
    return int(resume.current_version or 1) if resume else None


def _find_application(db: Session, user_id: uuid.UUID, target: JobTarget) -> uuid.UUID | None:
    if not target.job_id:
        return None
    return db.scalar(
        select(Application.id).where(Application.user_id == user_id, Application.job_id == target.job_id).order_by(Application.created_at.desc())
    )


def set_status(db: Session, user_id: uuid.UUID, target: JobTarget, status: JobTargetStatus, *, reason: str | None = None) -> None:
    if target.status == status:
        return
    before = target.status
    target.status = status
    if status == JobTargetStatus.APPLIED:
        target.submitted_resume_version = _submitted_version(db, target)
        target.application_id = target.application_id or _find_application(db, user_id, target)
    db.add(target)
    sent = f" (resume v{target.submitted_resume_version} sent)" if status == JobTargetStatus.APPLIED and target.submitted_resume_version else ""
    audit(
        db,
        action="ats.target_status_changed",
        message=f"{target.company_name} {target.role_title}: {before.value.title()} → {status.value.title()}{sent}" + (f" — {reason}" if reason else ""),
        user_id=user_id,
        actor=Actor.USER,
        meta={"target_id": str(target.id), "from": before.value, "to": status.value, "submitted_resume_version": target.submitted_resume_version},
    )


def update_target(db: Session, user_id: uuid.UUID, target_id: uuid.UUID, payload: TargetUpdate) -> TargetDetail:
    target = ats.get_target(db, user_id, target_id)
    fields = payload.model_fields_set
    changed: list[str] = []
    if "company_name" in fields and payload.company_name:
        target.company_name = " ".join(payload.company_name.split())[:255]
        target.normalized_company = _normalize_company(target.company_name)[:255]
        changed.append("company_name")
    if "role_title" in fields and payload.role_title:
        target.role_title = " ".join(payload.role_title.split())[:255]
        changed.append("role_title")
    if "job_url" in fields:
        target.job_url = _clean_url(payload.job_url)
        changed.append("job_url")
    if {"company_name", "role_title", "job_url"} & set(changed):
        key = fingerprint(target.company_name, target.role_title, target.job_url)
        _ensure_unique(db, user_id, key, exclude=target.id)
        target.fingerprint = key
    for name in ("location", "work_mode", "deadline", "notes", "follow_up_at"):
        if name in fields:
            setattr(target, name, getattr(payload, name))
            changed.append(name)
    if "source_resume_id" in fields:
        target.source_resume_id = _check_resume(db, user_id, payload.source_resume_id)
        changed.append("source_resume_id")
    if "application_id" in fields:
        if payload.application_id is not None:
            owned = db.scalar(select(Application.id).where(Application.id == payload.application_id, Application.user_id == user_id))
            if owned is None:
                raise NotFoundError("Application not found")
        target.application_id = payload.application_id
        changed.append("application_id")
    db.add(target)
    if changed:
        audit(
            db,
            action="ats.target_updated",
            message=f"Updated {target.company_name} {target.role_title}: {', '.join(changed)}",
            user_id=user_id,
            actor=Actor.USER,
            meta={"target_id": str(target.id), "fields": changed},
        )
    if "status" in fields and payload.status is not None:
        set_status(db, user_id, target, payload.status)
    db.flush()
    return get_detail(db, user_id, target.id)


def delete_target(db: Session, user_id: uuid.UUID, target_id: uuid.UUID) -> None:
    target = ats.get_target(db, user_id, target_id)
    soft_delete(target)
    audit(
        db,
        action="ats.target_deleted",
        message=f"Job target deleted: {target.role_title} at {target.company_name}",
        user_id=user_id,
        actor=Actor.USER,
        meta={"target_id": str(target.id)},
    )


def refresh_target(db: Session, user_id: uuid.UUID, target_id: uuid.UUID, *, use_ai: bool = False) -> tuple[JobDescriptionSnapshot, bool]:
    target = ats.get_target(db, user_id, target_id)
    latest = db.get(JobDescriptionSnapshot, target.latest_snapshot_id) if target.latest_snapshot_id else None
    url = target.job_url or (latest.url if latest else None)
    if not url:
        raise ValidationFailed(
            "This target has no posting URL to refresh from. Paste the updated job description instead.", code="no_url"
        )
    return add_snapshot(db, user_id, target, SnapshotCreate(source="URL", url=url, use_ai=use_ai))


# --------------------------------------------------------------------------- tailoring + compare


def tailor(db: Session, user_id: uuid.UUID, target_id: uuid.UUID, payload: TailorRequest) -> TailorResult:
    target = ats.get_target(db, user_id, target_id)
    if not target.latest_snapshot_id:
        raise ValidationFailed(
            "Add the job description to this target first (paste, upload or fetch it).", code="target_has_no_jd"
        )
    snapshot = ats.get_snapshot(db, user_id, target.latest_snapshot_id)
    source_id = payload.source_resume_id or target.source_resume_id
    source = resumes.get_resume(db, user_id, source_id) if source_id else resumes.get_default_resume(db, user_id)
    if source is None:
        raise ValidationFailed("Upload or create a resume first.", code="resume_required")
    target.source_resume_id = source.id
    if target.status in _PREP_STATUSES:
        set_status(db, user_id, target, JobTargetStatus.PREPARING, reason=f"tailoring {source.name}")
    analysis = ats.run_analysis(db, user_id, source, snapshot, target=target, schedule_polish=False)
    # the tailored analysis is polished as part of tailoring (workflow ``generation``)
    result = ats.auto_optimize(db, user_id, analysis.id, mode="new_resume", name=payload.name, polish_task=llm.TASK_TAILOR)
    db.flush()
    if target.status in _PREP_STATUSES:
        set_status(db, user_id, target, JobTargetStatus.READY, reason="tailored resume ready")
    audit(
        db,
        action="ats.target_tailored",
        message=(
            f"Tailored resume “{result.resume.name}” created from {source.name}: estimated {analysis.overall_score} → "
            f"{result.analysis.overall_score} ({len(result.applied)} safe changes)"
        ),
        user_id=user_id,
        actor=Actor.USER,
        meta={"target_id": str(target.id), "resume_id": str(result.resume.id), "source_resume_id": str(source.id)},
    )
    return TailorResult(
        target=target_read(db, target),
        resume=result.resume,
        analysis=result.analysis,
        source_analysis_id=analysis.id,
        source_score=analysis.overall_score,
        explanations=result.explanations,
        target_id=target.id,
        tailored_resume_id=result.resume.id,
        analysis_id=result.analysis.id,
        ai_pass="running" if result.analysis.status == AtsAnalysisStatus.RUNNING else "rules_only",
    )


def _one_line(value: str | None) -> str:
    return " ".join((value or "").split())


def _quick_snapshot(db: Session, user_id: uuid.UUID, jd: SnapshotCreate) -> JobDescriptionSnapshot:
    """A target-less snapshot from the request: pasted text (with an optional posting URL, e.g. text
    the client already fetched or uploaded), a posting URL fetched now, or a board posting."""
    if jd.source == "PASTED":
        if not (jd.text or "").strip():
            raise ValidationFailed("Paste the job description text.", code="jd_required")
        snapshot, _ = ats.snapshot_from_text(
            db, user_id, text=jd.text or "", source=JdSource.PASTED, title=jd.title, url=_clean_url(jd.url),
            structured=jd.structured, use_ai=jd.use_ai,
        )
        return snapshot
    fetch_mod.enforce_rate_limit(user_id)
    if jd.source == "BOARD":
        if jd.board is None:
            raise ValidationFailed("Choose a posting from the company's board.", code="board_required")
        posting = fetch_mod.fetch_board_posting(jd.board.vendor, jd.board.token, jd.board.external_id)
    else:
        if not (jd.url or "").strip():
            raise ValidationFailed("Give the job posting's URL.", code="invalid_url")
        posting = fetch_mod.fetch_posting(jd.url or "")
    snapshot, _ = ats.snapshot_from_text(
        db, user_id, text=posting.text, source=posting.source, title=jd.title or posting.title, company=posting.company,
        url=posting.url, location=posting.location, use_ai=jd.use_ai,
    )
    return snapshot


def quick_tailor(db: Session, user_id: uuid.UUID, payload: QuickTailorRequest) -> TailorResult:
    """The one-screen flow: job description + resume -> target + tailored copy (one transaction).

    The resume is resolved first (``resume_required`` when the user has none, 404 for another
    user's), then the snapshot, then the target (company/role: request -> JD -> fallbacks), then
    the same :func:`tailor` run as ``POST /targets/{id}/tailor``."""
    source = (
        resumes.get_resume(db, user_id, payload.source_resume_id)
        if payload.source_resume_id
        else resumes.get_default_resume(db, user_id)
    )
    if source is None:
        raise ValidationFailed("Upload or create a resume first.", code="resume_required")
    ats._require_analysable(source)
    snapshot = _quick_snapshot(db, user_id, payload.jd)
    parsed_company, parsed_role = _one_line(snapshot.company), _one_line(snapshot.title)
    typed_company, typed_role = _one_line(payload.company_name), _one_line(payload.role_title)
    company = typed_company or parsed_company
    role = typed_role or parsed_role
    # Derived = not typed, or typed exactly as the posting says (the form prefills from the parse).
    derived = (
        not typed_company or not typed_role
        or typed_company.lower() == parsed_company.lower() or typed_role.lower() == parsed_role.lower()
    )
    unknown = not company or _normalize_company(company) == ""
    company = UNKNOWN_COMPANY if unknown else company
    role = role or UNTITLED_ROLE
    detail = create_target(
        db,
        user_id,
        TargetCreate(
            company_name=company[:255], role_title=role[:255], job_url=snapshot.url, source_resume_id=source.id,
            snapshot_id=snapshot.id,
        ),
        fingerprint_extra=snapshot.text_sha256 if derived else None,
        link_company=not unknown,
    )
    label = " ".join(p for p in (company if not unknown else "", role if role != UNTITLED_ROLE else "") if p)
    name = payload.name or f"{source.name} — {label or 'tailored copy'}"
    return tailor(db, user_id, detail.id, TailorRequest(source_resume_id=source.id, name=name[:255]))


def _flatten(value: Any, path: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            out.update(_flatten(item, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        for index, item in enumerate(value):
            out.update(_flatten(item, f"{path}[{index}]"))
    elif value not in (None, "", [], {}):
        out[path] = value
    return out


def field_diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[list[FieldChange], DiffSummary]:
    """Flat field diff for the source-vs-tailored view.

    Kept separate from ``resumes.diff.diff_parsed`` on purpose: the compare view pairs each
    change with the suggestion that caused it (``explanations``), which needs stable flat
    paths; the builder's diff (entry matching, line diffs) serves the version history.
    """
    a, b = _flatten(before or {}), _flatten(after or {})
    changes: list[FieldChange] = []
    for path in sorted(set(a) | set(b)):
        old, new = a.get(path), b.get(path)
        if old == new:
            continue
        if isinstance(old, list) or isinstance(new, list):
            old_items = [str(x) for x in old or []] if isinstance(old, list) or old is None else [str(old)]
            new_items = [str(x) for x in new or []] if isinstance(new, list) or new is None else [str(new)]
            added = [x for x in new_items if x not in old_items]
            removed = [x for x in old_items if x not in new_items]
            if added:
                changes.append(FieldChange(path=path, before=None, after=added, kind="added"))
            if removed:
                changes.append(FieldChange(path=path, before=removed, after=None, kind="removed"))
            if not added and not removed:
                changes.append(FieldChange(path=path, before=old_items, after=new_items, kind="changed"))
            continue
        kind = "added" if old is None else "removed" if new is None else "changed"
        changes.append(FieldChange(path=path, before=old, after=new, kind=kind))  # type: ignore[arg-type]
    summary = DiffSummary(
        added=sum(1 for c in changes if c.kind == "added"),
        removed=sum(1 for c in changes if c.kind == "removed"),
        changed=sum(1 for c in changes if c.kind == "changed"),
    )
    return changes, summary


def compare(db: Session, user_id: uuid.UUID, target_id: uuid.UUID) -> CompareResult:
    target = ats.get_target(db, user_id, target_id)
    if not target.tailored_resume_id or not target.source_resume_id:
        raise ValidationFailed("Tailor a resume for this target first.", code="not_tailored")
    source = resumes.get_resume(db, user_id, target.source_resume_id)
    tailored = resumes.get_resume(db, user_id, target.tailored_resume_id)
    changes, summary = field_diff(source.parsed_data or {}, tailored.parsed_data or {})

    def latest_score(resume_id: uuid.UUID) -> int | None:
        return db.scalar(
            select(AtsAnalysis.overall_score)
            .where(AtsAnalysis.user_id == user_id, AtsAnalysis.resume_id == resume_id, AtsAnalysis.job_target_id == target.id)
            .order_by(AtsAnalysis.created_at.desc())
        )

    explanations: list[Explanation] = []
    applied: list[OptimizationSuggestion] = []
    rejected = 0
    # The source's analyses carry the rule-based changes; the tailored copy's carry the AI pass's.
    analyses = db.scalars(
        select(AtsAnalysis)
        .where(
            AtsAnalysis.user_id == user_id,
            AtsAnalysis.resume_id.in_((source.id, tailored.id)),
            AtsAnalysis.job_target_id == target.id,
        )
        .order_by(AtsAnalysis.created_at, AtsAnalysis.id)
    )
    # Rule-based changes (the source's analyses) before the AI pass's (the copy's): one transaction
    # can stamp both with the same time.
    for analysis in sorted(analyses, key=lambda a: 0 if a.resume_id == source.id else 1):
        for suggestion in sorted(analysis.suggestions, key=lambda s: s.ordinal):
            checks = suggestion.checks or {}
            if checks.get("applied_to_resume_id") == str(tailored.id):
                explanations.append(ats._explanation(suggestion))
                applied.append(suggestion)
            elif analysis.resume_id == tailored.id and checks.get("tailor_pass") and checks.get("ai_rejected"):
                rejected += 1
    return CompareResult(
        source=CompareSide(id=source.id, name=source.name, version=int(source.current_version or 1), parsed_data=source.parsed_data or {}, score=latest_score(source.id)),
        tailored=CompareSide(
            id=tailored.id, name=tailored.name, version=int(tailored.current_version or 1), parsed_data=tailored.parsed_data or {},
            score=latest_score(tailored.id),
        ),
        fields=changes,
        summary=summary,
        explanations=explanations,
        changes=tailor_changes(applied),
        ai_rejected=rejected,
    )


_GROUPS = {
    SuggestionKind.ADD_SKILL: "skills",
    SuggestionKind.REPLACE_SUMMARY: "summary",
    SuggestionKind.REPLACE_BULLET: "bullets",
    SuggestionKind.REORDER_SECTION: "sections",
}


def tailor_changes(applied: list[OptimizationSuggestion]) -> list[TailorChange]:
    """Applied suggestions (in the order they were applied) as "what changed" entries.

    A text the rules changed and the AI later rewrote again (same path, the AI's ``before`` is the
    rules' ``after``) becomes one entry: original -> final, with the AI's rationale."""
    out: list[TailorChange] = []
    for suggestion in applied:
        group = _GROUPS.get(suggestion.kind)
        if group is None and suggestion.kind == SuggestionKind.ADD_KEYWORD_CONTEXT:
            group = "summary" if suggestion.target_path == "summary" else "bullets"
        if group is None:
            continue
        ai = bool((suggestion.checks or {}).get("ai_polished"))
        if group in ("summary", "bullets"):
            chained = next(
                (
                    c for c in reversed(out)
                    if c.group == group and c.target_path == suggestion.target_path and c.after == suggestion.before
                ),
                None,
            )
            if chained is not None:
                chained.after = suggestion.after
                chained.rationale = suggestion.rationale or chained.rationale
                chained.source = "AI" if ai else chained.source
                chained.applied_version = suggestion.applied_version or chained.applied_version
                chained.suggestion_ids.append(suggestion.id)
                continue
        if group == "sections" and any(c.group == "sections" and c.target_path == suggestion.target_path for c in out):
            continue  # the AI pass re-checks the skills order; the rules already moved them
        out.append(
            TailorChange(
                group=group,  # type: ignore[arg-type]
                kind=suggestion.kind,
                title=suggestion.title,
                before=suggestion.before,
                after=suggestion.after,
                rationale=suggestion.rationale,
                source="AI" if ai else "SYSTEM",
                target_path=suggestion.target_path,
                applied_version=suggestion.applied_version,
                suggestion_ids=[suggestion.id],
            )
        )
    return out


# --------------------------------------------------------------------------- summary


def summary(db: Session, user_id: uuid.UUID) -> AtsSummary:
    counts = dict(
        db.execute(select(JobTarget.status, func.count()).where(JobTarget.user_id == user_id).group_by(JobTarget.status)).all()
    )
    by_status = {status.value: int(counts.get(status, 0)) for status in JobTargetStatus}
    in_progress = list(
        db.scalars(
            select(JobTarget)
            .where(JobTarget.user_id == user_id, JobTarget.status.in_((JobTargetStatus.PREPARING, JobTargetStatus.READY)))
            .order_by(JobTarget.updated_at.desc())
            .limit(8)
        )
    )
    now = utcnow()
    soon = now + timedelta(days=UPCOMING_DAYS)
    upcoming = list(
        db.scalars(
            select(JobTarget)
            .where(
                JobTarget.user_id == user_id,
                JobTarget.status.not_in((JobTargetStatus.ARCHIVED, JobTargetStatus.REJECTED)),
                or_(JobTarget.deadline.between(now, soon), JobTarget.follow_up_at.between(now - timedelta(days=1), soon)),
            )
            .order_by(func.coalesce(JobTarget.follow_up_at, JobTarget.deadline))
            .limit(8)
        )
    )
    return AtsSummary(
        total_targets=sum(by_status.values()),
        targets_by_status=by_status,
        recent_analyses=ats.list_analyses(db, user_id, limit=5),
        in_progress=reads(db, in_progress),
        upcoming=reads(db, upcoming),
    )


__all__ = [
    "add_snapshot",
    "compare",
    "create_target",
    "delete_target",
    "field_diff",
    "fingerprint",
    "get_detail",
    "list_targets",
    "quick_tailor",
    "tailor_changes",
    "refresh_target",
    "set_status",
    "summary",
    "tailor",
    "update_target",
]
