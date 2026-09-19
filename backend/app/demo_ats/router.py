"""The demo ATS: a tiny Greenhouse-style careers site served by this backend.

It exists so the Playwright autofill flow can be demonstrated end to end -- detection,
field mapping, filling, the CAPTCHA pause and the confirmation email -- **without ever
touching a real employer website**. Every posting is fictional; the "(Demo Careers)"
entries are clearly labelled mirrors on ``*.example`` domains.

No authentication (it plays the part of a third-party site). Submissions are appended to
``UPLOAD_DIR/demo_ats_submissions.jsonl`` -- deliberately table-less so the demo ATS
shares nothing with the JobPilot schema.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.demo_ats.catalog import NOTICE_PERIOD_OPTIONS, demo_companies, get_demo_job, job_payload, list_demo_jobs
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_write_lock = threading.Lock()

#: (name, human label) of every non-custom field on the apply form.
FORM_FIELDS: list[tuple[str, str]] = [
    ("first_name", "First Name"),
    ("last_name", "Last Name"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("location", "Location (City)"),
    ("linkedin", "LinkedIn Profile"),
    ("github", "GitHub URL"),
    ("portfolio", "Portfolio"),
    ("total_experience", "Total Years of Experience"),
    ("react_experience", "Years of experience with React"),
    ("current_ctc", "Current CTC"),
    ("expected_ctc", "Expected CTC"),
    ("notice_period", "Notice Period"),
    ("work_authorization", "Are you legally authorized to work in India?"),
    ("why_company", "Why do you want to work here?"),
]
REQUIRED_FIELDS: list[tuple[str, str]] = [
    (name, label)
    for name, label in FORM_FIELDS
    if name not in ("linkedin", "github", "portfolio", "current_ctc")
]


def submissions_path() -> Path:
    return Path(settings.UPLOAD_DIR) / "demo_ats_submissions.jsonl"


def _empty_values(job: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {name: "" for name, _ in FORM_FIELDS}
    values["consent"] = False
    for question in job.get("custom_questions") or []:
        values[question["key"]] = ""
    return values


def _generate_application_id(slug: str, email: str, timestamp: str) -> str:
    digest = hashlib.sha256(f"{slug}|{email.lower()}|{timestamp}".encode("utf-8")).digest()
    number = int.from_bytes(digest[:8], "big")
    code = "".join(ID_ALPHABET[(number >> (6 * i)) % len(ID_ALPHABET)] for i in range(6))
    return f"DEMO-{code}"


def _render_job_not_found(slug: str) -> None:
    raise NotFoundError(f"No demo posting with slug {slug!r}")


# --------------------------------------------------------------------------- pages


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Landing page: every demo company and its open roles."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {"companies": demo_companies(), "total": len(list_demo_jobs())},
    )


@router.get("/jobs.json")
def jobs_json() -> list[dict[str, Any]]:
    """Machine-readable catalogue consumed by ``DemoAtsAdapter.search_jobs``."""
    return [job_payload(job) for job in list_demo_jobs()]


@router.get("/jobs/{slug}", response_class=HTMLResponse)
def job_page(slug: str, request: Request) -> HTMLResponse:
    job = get_demo_job(slug)
    if job is None:
        _render_job_not_found(slug)
    return templates.TemplateResponse(request, "job.html", {"job": job})


@router.get("/jobs/{slug}/apply", response_class=HTMLResponse)
def apply_form(slug: str, request: Request, captcha: int = 0) -> HTMLResponse:
    """The application form. ``?captcha=1`` renders a (never-solved) CAPTCHA widget."""
    job = get_demo_job(slug)
    if job is None:
        _render_job_not_found(slug)
    return templates.TemplateResponse(
        request,
        "apply.html",
        {
            "job": job,
            "values": _empty_values(job),
            "errors": [],
            "notice_periods": NOTICE_PERIOD_OPTIONS,
            "custom_questions": job.get("custom_questions") or [],
            "captcha": bool(captcha),
        },
    )


@router.post("/jobs/{slug}/apply", response_class=HTMLResponse)
async def submit_application(
    slug: str,
    request: Request,
    captcha: int = 0,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Validate, store the submission as JSONL and confirm -- plus a simulated email."""
    job = get_demo_job(slug)
    if job is None:
        _render_job_not_found(slug)

    form = await request.form()
    custom_questions = job.get("custom_questions") or []
    values = _empty_values(job)
    for name in list(values):
        if name == "consent":
            continue
        raw = form.get(name)
        values[name] = str(raw).strip() if raw is not None and not hasattr(raw, "filename") else ""
    values["consent"] = str(form.get("consent") or "").strip().lower() in ("true", "on", "yes", "1")

    upload = form.get("resume")
    resume_filename = getattr(upload, "filename", "") or ""
    resume_bytes = await upload.read() if resume_filename else b""

    errors: list[str] = []
    for name, label in REQUIRED_FIELDS:
        if not values.get(name):
            errors.append(f"{label} is required.")
    if not resume_filename:
        errors.append("Resume/CV is required.")
    for question in custom_questions:
        if question.get("required") and not values.get(question["key"]):
            errors.append(f"{question['label']} is required.")
    if not values["consent"]:
        errors.append("You must consent before submitting this application.")
    if values.get("email") and "@" not in values["email"]:
        errors.append("Email must be a valid address.")

    if errors:
        logger.info("Demo ATS rejected an incomplete application for %s (%d issue(s))", slug, len(errors))
        return templates.TemplateResponse(
            request,
            "apply.html",
            {
                "job": job,
                "values": values,
                "errors": errors,
                "notice_periods": NOTICE_PERIOD_OPTIONS,
                "custom_questions": custom_questions,
                "captcha": bool(captcha),
            },
            status_code=422,
        )

    submitted_at = datetime.now(timezone.utc)
    application_id = _generate_application_id(slug, values["email"], submitted_at.isoformat())
    resume_path = _store_resume(application_id, resume_filename, resume_bytes)
    record = {
        "application_id": application_id,
        "slug": slug,
        "job_title": job["title"],
        "company": job["company"],
        "company_domain": job["company_domain"],
        "submitted_at": submitted_at.isoformat(),
        "answers": {k: v for k, v in values.items()},
        "resume_filename": resume_filename,
        "resume_path": resume_path,
        "captcha_shown": bool(captcha),
    }
    _append_submission(record)
    logger.info("Demo ATS accepted application %s for %s (%s)", application_id, slug, values["email"])

    _send_confirmation_email(db, job, values["email"], application_id)

    labels = dict(FORM_FIELDS)
    summary = [(labels[name], values[name]) for name, _ in FORM_FIELDS if values.get(name)]
    summary.extend((q["label"], values[q["key"]]) for q in custom_questions if values.get(q["key"]))
    summary.append(("Resume/CV", resume_filename))
    return templates.TemplateResponse(
        request,
        "confirmation.html",
        {
            "job": job,
            "application_id": application_id,
            "email": values["email"],
            "submitted_at": submitted_at.strftime("%d %b %Y, %H:%M UTC"),
            "summary": summary,
        },
    )


@router.get("/submissions.json")
def submissions_json(limit: int = 50) -> JSONResponse:
    """The most recent submissions (newest first) - for debugging and the demo script."""
    path = submissions_path()
    records: list[dict[str, Any]] = []
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()[-max(1, min(limit, 500)) :]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:  # pragma: no cover - defensive
                logger.warning("Skipping malformed submission line in %s", path)
    return JSONResponse(list(reversed(records)))


# --------------------------------------------------------------------------- helpers


def _store_resume(application_id: str, filename: str, payload: bytes) -> str | None:
    if not filename or not payload:
        return None
    folder = Path(settings.UPLOAD_DIR) / "demo_ats_uploads"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        safe = _SAFE_FILENAME.sub("_", filename)[-80:]
        path = folder / f"{application_id}_{safe}"
        path.write_bytes(payload)
        return str(path)
    except OSError as exc:  # pragma: no cover - defensive
        logger.warning("Could not store demo ATS upload %s: %s", filename, exc)
        return None


def _append_submission(record: dict[str, Any]) -> None:
    path = submissions_path()
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _send_confirmation_email(db: Session, job: dict[str, Any], email: str, application_id: str) -> None:
    """Best effort: if the applicant is a JobPilot user, simulate the ATS confirmation email.

    Imported lazily and fully guarded so the demo form keeps working while the emails
    module is still being written.
    """
    try:
        user = db.scalars(select(User).where(func.lower(User.email) == email.lower())).first()
        if user is None:
            logger.debug("No JobPilot user for %s - skipping simulated confirmation email", email)
            return
        from app.modules.emails.service import ingest_simulated_email

        subject = f"Thank you for applying to {job['company']} — {job['title']}"
        body = (
            f"Hi {user.full_name or 'there'},\n\n"
            f"Thank you for applying to the {job['title']} role at {job['company']}.\n"
            f"Your application has been received and is being reviewed by our recruiting team.\n\n"
            f"Application ID: {application_id}\n"
            f"Role: {job['title']}\n"
            f"Location: {job['location']}\n\n"
            f"We will be in touch if your profile matches what we are looking for.\n\n"
            f"-- {job['company']} Recruiting (demo ATS)\n"
        )
        ingest_simulated_email(
            db,
            user.id,
            subject=subject,
            body=body,
            sender=f"no-reply@{job['company_domain']}",
        )
        logger.info("Simulated confirmation email queued for %s (%s)", email, application_id)
    except Exception as exc:  # noqa: BLE001 - never break the demo form
        logger.warning("Simulated confirmation email skipped (%s): %s", exc.__class__.__name__, exc)
        try:
            db.rollback()  # keep the request session usable for the dependency commit
        except Exception:  # pragma: no cover - defensive
            logger.debug("Rollback after failed confirmation email also failed")
