"""Demo data seeder — ``python -m app.seed`` (contract §14).

Creates the demo account described in the spec and makes the whole product look alive on
first login: a complete profile, a *real* parsed PDF resume, company priorities, a skill
taxonomy, jobs discovered through every mock adapter plus the demo ATS, and roughly three
weeks of fabricated-but-plausible history (applications, events, emails, interviews,
notifications, audit trail and one finished automation run).

Idempotent: it exits early when the demo user already exists. ``--force`` deletes that
user's data first and rebuilds everything. Works on SQLite (tests) and PostgreSQL.
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import configure_logging
from app.models.application import Application, ApplicationAnswer, ApplicationDocument, ApplicationEvent
from app.models.audit import AuditLog
from app.models.automation import AutomationConfig, AutomationRun, BrowserSession, ConnectedAccount
from app.models.base import utcnow
from app.models.email import EmailIntegration, EmailMessage
from app.models.enums import (
    Actor,
    AnswerSource,
    AnswerStatus,
    ApplicationEventType,
    ApplicationStatus,
    AuditLevel,
    AutomationRunStatus,
    AutomationRunTrigger,
    AutomationState,
    CompanyPriority,
    DocumentType,
    EmailClassification,
    EmploymentType,
    FieldType,
    InterviewStatus,
    InterviewType,
    JobSourceType,
    NotificationType,
    PauseReason,
    WorkMode,
)
from app.models.interview import Interview
from app.models.job import Job, JobMatch
from app.models.notification import Notification
from app.models.profile import CompanyPreference, JobPreference, UserProfile
from app.models.resume import Resume, Skill
from app.models.user import User

logger = logging.getLogger(__name__)

SEED_RANDOM = 20240917
HISTORY_DAYS = 21
DEMO_FULL_NAME = "Aarav Sharma"

#: P1 / P3 / AVOID company priorities from the spec.
PRIORITY_COMPANIES: tuple[tuple[str, CompanyPriority, str], ...] = (
    ("Google", CompanyPriority.P1, "Dream company - apply to everything that fits"),
    ("Microsoft", CompanyPriority.P1, "Strong platform teams in Hyderabad and Bangalore"),
    ("Amazon", CompanyPriority.P1, "SDE-I / SDE-II openings"),
    ("Meta", CompanyPriority.P1, "Product engineering"),
    ("Apple", CompanyPriority.P1, "Services engineering"),
    ("Netflix", CompanyPriority.P1, "Very selective, still worth trying"),
    ("Northwind Labs", CompanyPriority.P3, "Current employer - only for a big step up"),
    ("Peakform Systems", CompanyPriority.P3, "Small B2B SaaS startup"),
    ("Wipro", CompanyPriority.AVOID, "Not looking for service-based roles"),
)

DEMO_RESUME_TEXT = """Aarav Sharma
Bangalore, Karnataka, India | +91 98765 43210 | demo@jobpilot.ai
linkedin.com/in/aarav-sharma | github.com/aarav-sharma | https://aaravsharma.dev

Summary
Full Stack Developer with 2 years of professional experience building React and Node.js
products on AWS. Comfortable owning a feature end to end, from PostgreSQL schema design
to Dockerised production deployment.

Technical Skills
Languages: JavaScript, TypeScript, Python, SQL
Frontend: React, Redux, Tailwind CSS, HTML, CSS
Backend: Node.js, Express.js, FastAPI, REST APIs, GraphQL
Databases: PostgreSQL, MongoDB, Redis
Cloud and Tools: AWS, Docker, Git, CI/CD, Jest

Work Experience
Software Engineer - Northwind Labs
Bangalore, India | 03/2023 - Present
- Built a React and TypeScript dashboard used by 4,000 internal users.
- Designed PostgreSQL schemas and Node.js services behind versioned REST APIs.
- Added Docker based CI/CD pipelines that cut deployment time in half.

Junior Software Engineer - Acme Cloud
Pune, India | 07/2022 - 02/2023
- Maintained Express.js microservices and MongoDB data pipelines.
- Wrote Jest unit tests raising coverage from 40% to 82%.

Education
B.Tech in Computer Science - VIT University, Vellore
2018 - 2022 | CGPA 8.6/10

Projects
JobTracker - A Next.js and FastAPI app that tracks job applications end to end.
Technologies: Next.js, FastAPI, PostgreSQL
Kanban Lite - Real-time board with WebSockets and Redis pub/sub.

Certifications
AWS Certified Developer - Associate, 2023
MongoDB Associate Developer (2022)
"""

#: (status, count) — the realistic mix the dashboard is built to show.
HISTORY_MIX: tuple[tuple[ApplicationStatus, int], ...] = (
    (ApplicationStatus.APPLIED, 12),
    (ApplicationStatus.APPLICATION_RECEIVED, 8),
    (ApplicationStatus.RECRUITER_CONTACTED, 4),
    (ApplicationStatus.ASSESSMENT, 3),
    (ApplicationStatus.INTERVIEW, 3),
    (ApplicationStatus.REJECTED, 6),
    (ApplicationStatus.OFFER, 1),
    (ApplicationStatus.NO_RESPONSE, 2),
    (ApplicationStatus.WITHDRAWN, 1),
)
QUEUE_SIZE = 6

__all__ = ["SeedSummary", "seed_demo_data", "main"]


# --------------------------------------------------------------------------- minimal PDF writer


_PDF_PAGE = (612, 792)
_PDF_LINE_HEIGHT = 12
_PDF_FONT_SIZE = 9
_PDF_LINES_PER_PAGE = 58


def _escape_pdf(line: str) -> bytes:
    return line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)").encode("latin-1", errors="replace")


def build_resume_pdf(text: str = DEMO_RESUME_TEXT) -> bytes:
    """A small, standards-correct PDF whose text ``pypdf`` can extract again.

    Hand-written (catalog / pages / Helvetica font / content streams / xref) so the repo
    needs no binary fixture and the demo resume really is parsed by the resume pipeline.
    """
    lines = (text or "").replace("\r\n", "\n").split("\n")
    pages = [lines[i : i + _PDF_LINES_PER_PAGE] for i in range(0, len(lines), _PDF_LINES_PER_PAGE)] or [[""]]

    objects: dict[int, bytes] = {}
    page_numbers: list[int] = []
    next_number = 4
    for page_lines in pages:
        page_number, content_number = next_number, next_number + 1
        next_number += 2
        page_numbers.append(page_number)
        parts = [
            b"BT",
            f"/F1 {_PDF_FONT_SIZE} Tf".encode("latin-1"),
            f"{_PDF_LINE_HEIGHT} TL".encode("latin-1"),
            f"40 {_PDF_PAGE[1] - 42} Td".encode("latin-1"),
        ]
        for line in page_lines:
            parts.append(b"(" + _escape_pdf(line) + b") Tj T*")
        parts.append(b"ET")
        stream = b"\n".join(parts)
        objects[page_number] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PDF_PAGE[0]} {_PDF_PAGE[1]}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>"
        ).encode("latin-1")
        objects[content_number] = f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream"

    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{n} 0 R" for n in page_numbers)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_numbers)} >>".encode("latin-1")
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode("latin-1") + objects[number] + b"\nendobj\n"
    xref_offset = len(out)
    size = max(objects) + 1
    out += f"xref\n0 {size}\n".encode("latin-1") + b"0000000000 65535 f \n"
    for number in range(1, size):
        out += f"{offsets[number]:010d} 00000 n \n".encode("latin-1")
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    return bytes(out)


# --------------------------------------------------------------------------- summary


@dataclass
class SeedSummary:
    created: bool = False
    user_id: uuid.UUID | None = None
    email: str = ""
    jobs: int = 0
    jobs_new: int = 0
    duplicates_merged: int = 0
    matches: int = 0
    applications: int = 0
    queued: int = 0
    interviews: int = 0
    emails: int = 0
    notifications: int = 0
    audit_entries: int = 0
    automation_runs: int = 0
    skills: int = 0
    messages: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "user_id": str(self.user_id) if self.user_id else None,
            "email": self.email,
            "jobs": self.jobs,
            "jobs_new": self.jobs_new,
            "duplicates_merged": self.duplicates_merged,
            "matches": self.matches,
            "applications": self.applications,
            "queued": self.queued,
            "interviews": self.interviews,
            "emails": self.emails,
            "notifications": self.notifications,
            "audit_entries": self.audit_entries,
            "automation_runs": self.automation_runs,
            "skills": self.skills,
        }


# --------------------------------------------------------------------------- purge


def _purge_user(db: Session, user: User) -> None:
    """Remove every row belonging to ``user`` (jobs/companies are global and stay)."""
    user_id = user.id
    for resume in db.scalars(select(Resume).where(Resume.user_id == user_id)):
        try:
            Path(resume.file_path).unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - a stale file must not stop a rebuild
            logger.warning("Could not delete %s: %s", resume.file_path, exc)
    applications = list(db.scalars(select(Application).where(Application.user_id == user_id)).unique())
    for application in applications:
        db.delete(application)
    db.flush()
    for model in (EmailMessage, Interview, JobMatch, AutomationRun, AuditLog, BrowserSession, ConnectedAccount,
                  Notification, CompanyPreference, EmailIntegration):
        db.execute(delete(model).where(model.user_id == user_id))
    db.flush()
    db.delete(user)
    db.flush()
    logger.info("Removed the previous demo user %s and %d applications", user.email, len(applications))


# --------------------------------------------------------------------------- profile / preferences


def _fill_profile(db: Session, user: User) -> UserProfile:
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == user.id)).first()
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    profile.full_name = DEMO_FULL_NAME
    profile.first_name = "Aarav"
    profile.last_name = "Sharma"
    profile.email = user.email
    profile.phone = "+91 98765 43210"
    profile.address = "42, 9th Main, Indiranagar"
    profile.city = "Bangalore"
    profile.state = "Karnataka"
    profile.country = "India"
    profile.postal_code = "560038"
    profile.linkedin_url = "https://www.linkedin.com/in/aarav-sharma"
    profile.github_url = "https://github.com/aarav-sharma"
    profile.portfolio_url = "https://aaravsharma.dev"
    profile.headline = "Full Stack Developer | React - Node.js - TypeScript - AWS"
    profile.summary = (
        "Full Stack Developer with 2 years of experience shipping React and Node.js products on AWS. "
        "I own features end to end: PostgreSQL schema design, typed REST APIs, and Dockerised deploys."
    )
    profile.current_designation = "Software Engineer"
    profile.current_company = "Northwind Labs"
    profile.years_of_experience = 2.0
    profile.current_salary = 800_000
    profile.previous_companies = [
        {
            "company": "Northwind Labs",
            "title": "Software Engineer",
            "start": "2023-03",
            "end": None,
            "description": "React + TypeScript dashboard, Node.js services, PostgreSQL, Docker CI/CD.",
        },
        {
            "company": "Acme Cloud",
            "title": "Junior Software Engineer",
            "start": "2022-07",
            "end": "2023-02",
            "description": "Express.js microservices, MongoDB pipelines, Jest test coverage.",
        },
    ]
    profile.education = [
        {
            "institution": "VIT University, Vellore",
            "degree": "B.Tech",
            "field": "Computer Science",
            "start": "2018",
            "end": "2022",
            "grade": "8.6/10",
        }
    ]
    profile.skills = ["React", "Node.js", "TypeScript", "PostgreSQL", "Docker", "AWS", "JavaScript", "Express.js", "Redis", "Git"]
    profile.technologies = ["Next.js", "Tailwind CSS", "FastAPI", "MongoDB", "Jest", "REST APIs", "GraphQL", "CI/CD"]
    profile.certifications = [
        {"name": "AWS Certified Developer - Associate", "issuer": "Amazon Web Services", "year": 2023},
        {"name": "MongoDB Associate Developer", "issuer": "MongoDB", "year": 2022},
    ]
    profile.projects = [
        {
            "name": "JobTracker",
            "description": "Next.js + FastAPI app that tracks job applications end to end.",
            "technologies": ["Next.js", "FastAPI", "PostgreSQL"],
            "url": "https://github.com/aarav-sharma/jobtracker",
        },
        {
            "name": "Kanban Lite",
            "description": "Real-time collaborative board built with WebSockets and Redis pub/sub.",
            "technologies": ["React", "Node.js", "Redis"],
        },
    ]
    profile.achievements = [
        "Cut deployment time by 50% by introducing Docker based CI/CD at Northwind Labs.",
        "Raised backend test coverage from 40% to 82% at Acme Cloud.",
    ]
    profile.languages = ["English", "Hindi", "Kannada"]
    profile.skill_experience = {
        "React": 2.0,
        "Node.js": 2.0,
        "TypeScript": 1.5,
        "PostgreSQL": 2.0,
        "Docker": 1.5,
        "AWS": 1.5,
        "Python": 1.0,
    }
    profile.work_authorization = {"IN": True, "US": False, "EU": False}
    profile.requires_sponsorship = False
    profile.willing_to_relocate = True
    profile.canonical_answers = {
        "custom:why_us": (
            "I want to work on products used at scale, and this team's focus on developer experience "
            "matches the work I already enjoy most."
        ),
        "notice_period_text": "30 days",
    }
    db.flush()
    return profile


def _fill_preferences(db: Session, user: User) -> JobPreference:
    preference = db.scalars(select(JobPreference).where(JobPreference.user_id == user.id)).first()
    if preference is None:
        preference = JobPreference(user_id=user.id)
        db.add(preference)
    preference.desired_titles = ["Software Engineer", "Full Stack Developer", "Backend Engineer"]
    preference.min_salary = 1_000_000
    preference.desired_salary = 1_200_000
    preference.currency = "INR"
    preference.notice_period_days = 30
    preference.preferred_locations = ["Bangalore", "Hyderabad", "Pune", "Delhi NCR", "Remote"]
    preference.work_modes = [WorkMode.REMOTE.value, WorkMode.HYBRID.value, WorkMode.ONSITE.value]
    preference.employment_types = [EmploymentType.FULL_TIME.value]
    preference.experience_min = 1.0
    preference.experience_max = 5.0
    preference.preferred_technologies = ["React", "Node.js", "TypeScript", "PostgreSQL", "Docker", "AWS"]
    preference.excluded_keywords = ["unpaid", "commission only", "sales executive"]
    preference.min_match_score = 75
    preference.only_posted_within_hours = 24 * 7
    db.flush()
    return preference


def _fill_company_preferences(db: Session, user: User) -> int:
    from app.modules.companies.service import upsert_preference

    for name, priority, notes in PRIORITY_COMPANIES:
        upsert_preference(db, user.id, name, priority, notes=notes)
    db.flush()
    return len(PRIORITY_COMPANIES)


def _seed_skill_taxonomy(db: Session) -> int:
    """Populate the global :class:`Skill` table from the canonical alias map."""
    from app.modules.ai.skills import SKILL_ALIASES, skill_category

    existing = {row for row in db.scalars(select(Skill.normalized_name)).all()}
    created = 0
    for canonical, aliases in SKILL_ALIASES.items():
        normalized = canonical.strip().lower()
        if normalized in existing:
            continue
        db.add(
            Skill(
                name=canonical,
                normalized_name=normalized,
                aliases=list(aliases),
                category=skill_category(canonical),
            )
        )
        existing.add(normalized)
        created += 1
    db.flush()
    logger.info("Skill taxonomy: %d new skills", created)
    return created


# --------------------------------------------------------------------------- resume


def _create_resume(db: Session, user: User) -> Resume | None:
    from app.modules.resumes.service import create_resume_from_bytes

    try:
        resume = create_resume_from_bytes(
            db,
            user.id,
            "aarav-sharma-resume.pdf",
            build_resume_pdf(),
            name="Software Engineer - Full Stack",
            target_role="Software Engineer",
            set_default=True,
        )
    except Exception as exc:  # pragma: no cover - never abort the seed on the resume
        logger.exception("Could not create the demo resume: %s", exc)
        return None
    logger.info("Demo resume created (parse_status=%s)", resume.parse_status)
    return resume


# --------------------------------------------------------------------------- discovery


def _discover_jobs(db: Session, user: User, preference: JobPreference) -> tuple[int, int, int, list[Job]]:
    from app.modules.adapters.registry import DISCOVERY_SOURCES, get_enabled_adapters
    from app.modules.jobs.service import build_search_query, ingest_discovered

    query = build_search_query(preference, limit=60)
    query.posted_within_hours = preference.only_posted_within_hours
    discovered: list[Any] = []
    for adapter in get_enabled_adapters(list(DISCOVERY_SOURCES)):
        try:
            found = adapter.search_jobs(query)
        except Exception as exc:  # pragma: no cover - a broken adapter must not stop the seed
            logger.warning("Adapter %s failed during seeding: %s", adapter.source.value, exc)
            continue
        logger.info("  %-18s %3d jobs", adapter.source.value, len(found))
        discovered.extend(found)

    result = ingest_discovered(db, user.id, discovered)
    jobs = list(db.scalars(select(Job).where(Job.id.in_(result.job_ids_all))).unique()) if result.job_ids_all else []
    return result.jobs_found, result.jobs_new, result.duplicates_merged, jobs


def _analyze(db: Session, user: User, jobs: list[Job]) -> list[JobMatch]:
    from app.modules.matching.service import analyze_jobs

    matches = analyze_jobs(db, user.id, jobs)
    logger.info("Analyzed %d jobs for the demo user", len(matches))
    return matches


# --------------------------------------------------------------------------- history helpers


def _weekday_biased_day(rng: random.Random, today: datetime, days_back_max: int) -> datetime:
    """A datetime in the last ``days_back_max`` days, weighted towards weekdays."""
    for _ in range(12):
        days_back = rng.randint(1, days_back_max)
        moment = today - timedelta(days=days_back)
        if moment.weekday() < 5 or rng.random() < 0.25:
            return moment.replace(
                hour=rng.choice([9, 10, 11, 12, 14, 15, 16, 17, 18]),
                minute=rng.choice([5, 12, 18, 24, 31, 39, 47, 53]),
                second=0,
                microsecond=0,
            )
    return today - timedelta(days=rng.randint(1, days_back_max))


def _event(
    db: Session,
    application: Application,
    event_type: ApplicationEventType,
    message: str,
    *,
    created_at: datetime,
    actor: Actor = Actor.AUTOMATION,
    from_status: ApplicationStatus | None = None,
    to_status: ApplicationStatus | None = None,
    meta: dict[str, Any] | None = None,
) -> ApplicationEvent:
    row = ApplicationEvent(
        application_id=application.id,
        event_type=event_type,
        actor=actor,
        from_status=from_status,
        to_status=to_status,
        message=message,
        meta=meta or {},
        created_at=created_at,
    )
    db.add(row)
    return row


def _primary_source(job: Job) -> JobSourceType:
    from app.modules.jobs.service import apply_rank

    sources = sorted(job.sources or [], key=lambda s: apply_rank(s.source))
    return sources[0].source if sources else JobSourceType.OTHER


def _match_score(matches: dict[uuid.UUID, JobMatch], job: Job) -> int:
    match = matches.get(job.id)
    return int(match.match_score) if match is not None else 70


def _priority_for(db: Session, user_id: uuid.UUID, job: Job) -> CompanyPriority:
    from app.modules.jobs.service import get_company_priority

    return get_company_priority(db, user_id, job.company)


# --------------------------------------------------------------------------- history


def _build_history(
    db: Session,
    user: User,
    resume: Resume | None,
    jobs: list[Job],
    matches: dict[uuid.UUID, JobMatch],
    rng: random.Random,
    summary: SeedSummary,
) -> list[Application]:
    """~40 applications spread over the last three weeks with events for each transition."""
    now = utcnow()
    ranked = sorted(
        (job for job in jobs if _priority_for(db, user.id, job) != CompanyPriority.AVOID),
        key=lambda job: (-_match_score(matches, job), job.title),
    )
    wanted = sum(count for _status, count in HISTORY_MIX) + QUEUE_SIZE
    pool = ranked[: max(wanted, len(ranked) // 2)]
    rng.shuffle(pool)
    if len(pool) < wanted:
        logger.warning("Only %d jobs available for %d demo applications", len(pool), wanted)

    applications: list[Application] = []
    index = 0
    for status, count in HISTORY_MIX:
        for _ in range(count):
            if index >= len(pool):
                break
            job = pool[index]
            index += 1
            applications.append(_create_history_application(db, user, resume, job, matches, status, rng, now))
    summary.applications = len(applications)
    db.flush()
    return applications


def _create_history_application(
    db: Session,
    user: User,
    resume: Resume | None,
    job: Job,
    matches: dict[uuid.UUID, JobMatch],
    status: ApplicationStatus,
    rng: random.Random,
    now: datetime,
) -> Application:
    applied_at = _weekday_biased_day(rng, now, HISTORY_DAYS)
    score = _match_score(matches, job)
    source = _primary_source(job)
    application = Application(
        user_id=user.id,
        job_id=job.id,
        resume_id=resume.id if resume is not None else None,
        status=status,
        priority=_priority_for(db, user.id, job),
        match_score=score,
        source=source,
        automation_state=AutomationState.SUCCESS,
        review_required=True,
        approved_at=applied_at,
        applied_at=applied_at,
        submitted_via="AUTOMATION" if rng.random() < 0.7 else "MANUAL",
        external_application_id=f"APP-{rng.randint(100000, 999999)}",
        last_update_at=applied_at,
        cover_letter=None,
    )
    db.add(application)
    db.flush()

    _event(
        db,
        application,
        ApplicationEventType.CREATED,
        f"Queued from {source.value.replace('_', ' ').title()} ({score}% match)",
        created_at=applied_at - timedelta(minutes=12),
        to_status=ApplicationStatus.QUEUED,
    )
    _event(
        db,
        application,
        ApplicationEventType.ANSWERS_GENERATED,
        "Answers prepared from your profile and resume",
        created_at=applied_at - timedelta(minutes=8),
    )
    _event(
        db,
        application,
        ApplicationEventType.SUBMITTED,
        f"Application submitted to {job.company.name}",
        created_at=applied_at,
        from_status=ApplicationStatus.IN_PROGRESS,
        to_status=ApplicationStatus.APPLIED,
    )

    if status != ApplicationStatus.APPLIED:
        response_at = applied_at + timedelta(days=rng.randint(1, 6), hours=rng.randint(0, 8))
        response_at = min(response_at, now - timedelta(hours=1))
        if status == ApplicationStatus.NO_RESPONSE:
            application.applied_at = now - timedelta(days=rng.randint(22, 30))
            application.approved_at = application.applied_at
            _event(
                db,
                application,
                ApplicationEventType.STATUS_CHANGED,
                "No response after 21 days",
                created_at=now - timedelta(days=1),
                actor=Actor.SCHEDULER,
                from_status=ApplicationStatus.APPLIED,
                to_status=ApplicationStatus.NO_RESPONSE,
            )
        elif status == ApplicationStatus.WITHDRAWN:
            _event(
                db,
                application,
                ApplicationEventType.STATUS_CHANGED,
                "Withdrawn - accepted another process",
                created_at=response_at,
                actor=Actor.USER,
                from_status=ApplicationStatus.APPLIED,
                to_status=ApplicationStatus.WITHDRAWN,
            )
            application.last_update_at = response_at
        else:
            application.last_response_at = response_at
            application.last_update_at = response_at
            _event(
                db,
                application,
                ApplicationEventType.STATUS_CHANGED,
                _response_message(status, job),
                created_at=response_at,
                actor=Actor.EMAIL,
                from_status=ApplicationStatus.APPLIED,
                to_status=status,
            )
            if status in (ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER):
                application.next_action = "Prepare for the next round"
                application.next_action_due = now + timedelta(days=rng.randint(1, 6))
                _add_cover_letter(db, application, job, applied_at)
    db.flush()
    return application


def _add_cover_letter(db: Session, application: Application, job: Job, created_at: datetime) -> None:
    """Attach the generated cover letter so ``ApplicationDetail.documents`` is not empty."""
    content = (
        f"Dear {job.company.name} hiring team,\n\n"
        f"I am applying for the {job.title} role. Over the last two years I have shipped React and "
        "Node.js features end to end at Northwind Labs, owning PostgreSQL schema design, typed REST "
        "APIs and the Docker based CI/CD pipeline that halved our deploy time.\n\n"
        "I would love to bring that ownership to your team.\n\nBest regards,\nAarav Sharma"
    )
    application.cover_letter = content
    db.add(
        ApplicationDocument(
            application_id=application.id,
            resume_id=application.resume_id,
            document_type=DocumentType.COVER_LETTER,
            filename=f"cover-letter-{job.company.normalized_name or 'company'}.txt",
            content=content,
            created_at=created_at,
        )
    )


def _response_message(status: ApplicationStatus, job: Job) -> str:
    company = job.company.name
    return {
        ApplicationStatus.APPLICATION_RECEIVED: f"{company} confirmed they received your application",
        ApplicationStatus.RECRUITER_CONTACTED: f"A recruiter from {company} reached out",
        ApplicationStatus.ASSESSMENT: f"{company} sent an online assessment",
        ApplicationStatus.INTERVIEW: f"{company} scheduled an interview",
        ApplicationStatus.REJECTED: f"{company} decided not to move forward",
        ApplicationStatus.OFFER: f"{company} extended an offer",
    }.get(status, f"{company} updated your application")


# --------------------------------------------------------------------------- queue


def _standard_questions() -> list[dict[str, Any]]:
    return [
        {"key": "full_name", "text": "Full name", "type": FieldType.TEXT, "required": True},
        {"key": "email", "text": "Email address", "type": FieldType.EMAIL, "required": True},
        {"key": "phone", "text": "Mobile number", "type": FieldType.PHONE, "required": True},
        {"key": "linkedin_url", "text": "LinkedIn profile", "type": FieldType.URL, "required": False},
        {"key": "github_url", "text": "GitHub URL", "type": FieldType.URL, "required": False},
        {"key": "years_of_experience", "text": "Total years of experience", "type": FieldType.NUMBER, "required": True},
        {"key": "expected_salary", "text": "Expected CTC", "type": FieldType.NUMBER, "required": True},
        {"key": "notice_period_days", "text": "Notice period", "type": FieldType.SELECT, "required": True},
        {"key": "resume_file", "text": "Resume / CV", "type": FieldType.FILE, "required": True},
        {"key": "custom:why_us", "text": "Why do you want to work here?", "type": FieldType.TEXTAREA, "required": True},
    ]


def _generate_answers(db: Session, application: Application, job: Job, user: User) -> int:
    """Use ``applications.answers.generate_answers`` when it exists, else a faithful fallback."""
    try:
        from app.modules.applications.answers import generate_answers
        from app.modules.profiles.service import build_candidate_context
    except Exception as exc:
        logger.debug("applications.answers.generate_answers unavailable: %s", exc)
    else:
        try:
            candidate = build_candidate_context(db, user.id, application.resume_id)
            answers = generate_answers(db, application, candidate)
            db.flush()
            return len(answers)
        except Exception as exc:  # pragma: no cover - fall back to the local generator
            logger.warning("generate_answers failed during seeding: %s", exc)
    return _fallback_answers(db, application, user)


def _fallback_answers(db: Session, application: Application, user: User) -> int:
    from app.modules.profiles.service import build_candidate_context

    candidate = build_candidate_context(db, user.id, application.resume_id)
    flat = candidate.flat
    created = 0
    for order, question in enumerate(_standard_questions()):
        key = question["key"]
        value = flat.get(key)
        if key == "notice_period_days" and value is not None:
            value = f"{int(value)} days"
        answered = value not in (None, "", [], {})
        db.add(
            ApplicationAnswer(
                application_id=application.id,
                order=order,
                question_key=key,
                question_text=question["text"],
                field_type=question["type"],
                options=["Immediate", "15 days", "30 days", "60 days", "90 days"] if key == "notice_period_days" else [],
                required=bool(question["required"]),
                answer=str(value) if answered else None,
                answer_source=AnswerSource.PROFILE if answered else None,
                status=AnswerStatus.ANSWERED if answered else AnswerStatus.NEEDS_USER_INPUT,
                confidence=0.95 if answered else 0.0,
                rationale="Taken from your profile" if answered else "Not present in your profile",
                is_sensitive=False,
                mapped_profile_field=f"profile.{key}" if answered else None,
            )
        )
        created += 1
    db.flush()
    return created


def _build_queue(
    db: Session,
    user: User,
    resume: Resume | None,
    jobs: list[Job],
    matches: dict[uuid.UUID, JobMatch],
    used_job_ids: set[uuid.UUID],
    rng: random.Random,
    summary: SeedSummary,
) -> list[Application]:
    """Six items in the approval queue, including a DEMO_ATS one and a REQUIRES_USER one."""
    now = utcnow()
    demo_jobs = [j for j in jobs if j.id not in used_job_ids and _primary_source(j) == JobSourceType.DEMO_ATS]
    other_jobs = [
        j
        for j in jobs
        if j.id not in used_job_ids
        and _primary_source(j) != JobSourceType.DEMO_ATS
        and _priority_for(db, user.id, j) != CompanyPriority.AVOID
    ]
    other_jobs.sort(key=lambda job: -_match_score(matches, job))

    chosen: list[Job] = []
    if demo_jobs:
        chosen.append(demo_jobs[0])
    chosen.extend(other_jobs[: QUEUE_SIZE - len(chosen)])

    queue: list[Application] = []
    for position, job in enumerate(chosen):
        application = Application(
            user_id=user.id,
            job_id=job.id,
            resume_id=resume.id if resume is not None else None,
            status=ApplicationStatus.QUEUED,
            priority=_priority_for(db, user.id, job),
            match_score=_match_score(matches, job),
            source=_primary_source(job),
            queue_position=position + 1,
            automation_state=AutomationState.IDLE,
            review_required=True,
            created_at=now - timedelta(hours=position + 1),
        )
        db.add(application)
        db.flush()
        _event(
            db,
            application,
            ApplicationEventType.CREATED,
            f"Queued by the daily automation ({application.match_score}% match)",
            created_at=now - timedelta(hours=position + 1),
            to_status=ApplicationStatus.QUEUED,
        )
        queue.append(application)
        used_job_ids.add(job.id)

    if queue:
        _prepare_ready_item(db, queue[0], user, now)
    if len(queue) > 1:
        _prepare_requires_user_item(db, queue[1], user, now)

    summary.queued = len(queue)
    db.flush()
    return queue


def _prepare_ready_item(db: Session, application: Application, user: User, now: datetime) -> None:
    """The DEMO_ATS item: answers generated, form filled, waiting for approval."""
    job = application.job
    count = _generate_answers(db, application, job, user)
    application.automation_state = AutomationState.PAUSED
    application.pause_reason = PauseReason.USER_REVIEW
    application.pause_message = "Form filled and ready for your review"
    application.form_snapshot = {
        "url": job.apply_url or job.canonical_url,
        "submit_selector": "button[type=submit]",
        "fields": [
            {"key": "first_name", "label": "First Name", "value": "Aarav", "status": "ANSWERED", "required": True},
            {"key": "last_name", "label": "Last Name", "value": "Sharma", "status": "ANSWERED", "required": True},
            {"key": "email", "label": "Email", "value": user.email, "status": "ANSWERED", "required": True},
            {"key": "phone", "label": "Phone", "value": "+91 98765 43210", "status": "ANSWERED", "required": True},
            {"key": "expected_salary", "label": "Expected CTC", "value": "1200000", "status": "ANSWERED", "required": True},
            {"key": "resume_file", "label": "Resume/CV", "value": "aarav-sharma-resume.pdf", "status": "ANSWERED", "required": True},
        ],
        "blockers": [],
    }
    _event(
        db,
        application,
        ApplicationEventType.ANSWERS_GENERATED,
        f"{count} answers prepared from your profile",
        created_at=now - timedelta(minutes=40),
    )
    _event(
        db,
        application,
        ApplicationEventType.FORM_FILLED,
        "Application form detected and filled - ready for your review",
        created_at=now - timedelta(minutes=35),
    )
    db.flush()


def _prepare_requires_user_item(db: Session, application: Application, user: User, now: datetime) -> None:
    """The REQUIRES_USER example: one unanswerable question, nothing invented."""
    count = _generate_answers(db, application, application.job, user)
    db.add(
        ApplicationAnswer(
            application_id=application.id,
            order=count + 1,
            question_key="custom:preferred_start_date",
            question_text="What is your preferred start date?",
            field_type=FieldType.TEXT,
            required=True,
            answer=None,
            answer_source=None,
            status=AnswerStatus.NEEDS_USER_INPUT,
            confidence=0.0,
            rationale="This fact is not in your profile - the assistant will never guess a date.",
            is_sensitive=False,
        )
    )
    application.automation_state = AutomationState.REQUIRES_USER
    application.pause_reason = PauseReason.UNKNOWN_QUESTION
    application.pause_message = "The form asks for your preferred start date"
    _event(
        db,
        application,
        ApplicationEventType.PAUSED,
        "Paused: the form asks a question your profile cannot answer",
        created_at=now - timedelta(minutes=20),
        meta={"pause_reason": PauseReason.UNKNOWN_QUESTION.value},
    )
    db.flush()


# --------------------------------------------------------------------------- interviews


def _build_interviews(db: Session, user: User, applications: list[Application], rng: random.Random) -> list[Interview]:
    now = utcnow()
    targets = [a for a in applications if a.status in (ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER)][:2]
    interviews: list[Interview] = []
    for position, application in enumerate(targets):
        scheduled_at = now + timedelta(days=position + 2, hours=rng.randint(0, 6))
        interview = Interview(
            application_id=application.id,
            user_id=user.id,
            interview_type=InterviewType.TECHNICAL if position == 0 else InterviewType.PHONE_SCREEN,
            status=InterviewStatus.SCHEDULED,
            round_number=position + 1,
            scheduled_at=scheduled_at,
            duration_minutes=60 if position == 0 else 30,
            location_or_link="https://meet.example.com/jobpilot-demo",
            interviewer="Priya Nair" if position == 0 else "Rahul Verma",
            notes="Focus on system design and React internals." if position == 0 else None,
        )
        db.add(interview)
        db.flush()
        if position == 0:
            interview.prep_material = _interview_prep(db, user, application, interview)
        interviews.append(interview)
    db.flush()
    return interviews


def _interview_prep(db: Session, user: User, application: Application, interview: Interview) -> dict[str, Any]:
    try:
        from app.modules.ai.schemas import JobContext
        from app.modules.ai.tasks import generate_interview_prep
        from app.modules.profiles.service import build_candidate_context

        candidate = build_candidate_context(db, user.id, application.resume_id)
        prep = generate_interview_prep(
            JobContext.from_job(application.job), candidate, interview.interview_type.value
        )
        data = prep.model_dump(mode="json") if hasattr(prep, "model_dump") else dict(prep)
        data["generated_at"] = utcnow().isoformat()
        return data
    except Exception as exc:  # pragma: no cover - static fallback keeps the demo intact
        logger.warning("Could not generate interview prep: %s", exc)
        return {
            "technical": ["Explain how React reconciliation works.", "Design a rate limiter for a REST API."],
            "behavioral": ["Tell me about a production incident you handled."],
            "company_specific": [f"Why {application.job.company.name}?"],
            "job_specific": ["How would you structure a PostgreSQL schema for this product?"],
            "resume_based": ["Walk me through the JobTracker project."],
            "generated_at": utcnow().isoformat(),
        }


# --------------------------------------------------------------------------- emails


EMAIL_TEMPLATES: tuple[tuple[EmailClassification, str, str], ...] = (
    (
        EmailClassification.APPLICATION_RECEIVED,
        "We received your application for {title}",
        "Hi Aarav,\n\nThanks for applying to the {title} role at {company}. Our team is reviewing your "
        "application and we will be in touch shortly.\n\n- {company} Talent Team",
    ),
    (
        EmailClassification.RECRUITER_MESSAGE,
        "Quick chat about the {title} role at {company}?",
        "Hi Aarav,\n\nI came across your profile and think you could be a great fit for our {title} "
        "opening. Do you have 20 minutes this week for an intro call?\n\nBest,\nRecruiting at {company}",
    ),
    (
        EmailClassification.ASSESSMENT,
        "{company} coding assessment - {title}",
        "Hi Aarav,\n\nPlease complete the online coding assessment for the {title} position within the "
        "next 5 days. The link is in your candidate portal.\n\n- {company} Hiring",
    ),
    (
        EmailClassification.INTERVIEW,
        "Interview scheduled: {title} at {company}",
        "Hi Aarav,\n\nYour technical interview for the {title} role is confirmed. Please join the video "
        "call at the scheduled time.\n\n- {company} Recruiting",
    ),
    (
        EmailClassification.REJECTION,
        "Update on your {company} application",
        "Hi Aarav,\n\nThank you for your interest in the {title} role. After careful review we have "
        "decided to move forward with other candidates.\n\n- {company} Talent Team",
    ),
    (
        EmailClassification.OFFER,
        "Your offer from {company}",
        "Hi Aarav,\n\nWe are delighted to offer you the {title} position at {company}. The full details "
        "are attached - please let us know by the end of the week.\n\n- {company} Talent Team",
    ),
)

CLASSIFICATION_BY_STATUS: dict[ApplicationStatus, EmailClassification] = {
    ApplicationStatus.APPLICATION_RECEIVED: EmailClassification.APPLICATION_RECEIVED,
    ApplicationStatus.RECRUITER_CONTACTED: EmailClassification.RECRUITER_MESSAGE,
    ApplicationStatus.ASSESSMENT: EmailClassification.ASSESSMENT,
    ApplicationStatus.INTERVIEW: EmailClassification.INTERVIEW,
    ApplicationStatus.REJECTED: EmailClassification.REJECTION,
    ApplicationStatus.OFFER: EmailClassification.OFFER,
}


def _build_emails(db: Session, user: User, applications: list[Application], rng: random.Random) -> int:
    """~10 simulated emails linked to the applications that actually got a reply."""
    templates = {classification: (subject, body) for classification, subject, body in EMAIL_TEMPLATES}
    candidates = [a for a in applications if a.status in CLASSIFICATION_BY_STATUS][:10]
    created = 0
    for position, application in enumerate(candidates):
        classification = CLASSIFICATION_BY_STATUS[application.status]
        subject_tpl, body_tpl = templates[classification]
        job = application.job
        company = job.company
        subject = subject_tpl.format(title=job.title, company=company.name)
        body = body_tpl.format(title=job.title, company=company.name)
        domain = company.domain or f"{company.normalized_name or 'company'}.example"
        sender = f"talent@{domain}"
        received_at = application.last_response_at or (application.applied_at or utcnow()) + timedelta(days=1)

        if _ingest_simulated(db, user, application, subject, body, sender):
            created += 1
            continue

        db.add(
            EmailMessage(
                user_id=user.id,
                application_id=application.id,
                provider_message_id=f"demo-{application.id.hex[:10]}-{position}",
                thread_id=f"thread-{application.id.hex[:8]}",
                sender=f"{company.name} Talent <{sender}>",
                sender_domain=domain,
                recipient=user.email,
                subject=subject,
                snippet=body[:140],
                body_text=body,
                received_at=received_at,
                classification=classification,
                classification_confidence=0.92,
                classified_by="RULES",
                classification_reason=f"Subject and sender match the {classification.value} pattern",
                matched_by="DOMAIN",
                is_simulated=True,
                is_read=rng.random() < 0.5,
                status_applied=True,
                raw_headers={"From": sender, "To": user.email, "Subject": subject},
                created_at=received_at,
            )
        )
        created += 1
    db.flush()
    return created


def _ingest_simulated(db: Session, user: User, application: Application, subject: str, body: str, sender: str) -> bool:
    """Prefer the real emails pipeline when that module is available."""
    try:
        from app.modules.emails.service import ingest_simulated_email
    except Exception as exc:
        logger.debug("emails.service.ingest_simulated_email unavailable: %s", exc)
        return False
    try:
        ingest_simulated_email(db, user.id, subject=subject, body=body, sender=sender, application_id=application.id)
    except TypeError:
        try:
            ingest_simulated_email(db, user.id, subject, body, sender, application.id)
        except Exception as exc:  # pragma: no cover - fall back to the direct row
            logger.warning("ingest_simulated_email failed: %s", exc)
            return False
    except Exception as exc:  # pragma: no cover - fall back to the direct row
        logger.warning("ingest_simulated_email failed: %s", exc)
        return False
    db.flush()
    return True


# --------------------------------------------------------------------------- notifications & audit


def _build_notifications(db: Session, user: User, applications: list[Application], queue: list[Application], interviews: list[Interview]) -> int:
    from app.modules.notifications.service import notify

    now = utcnow()
    created = 0
    offers = [a for a in applications if a.status == ApplicationStatus.OFFER]
    rejected = [a for a in applications if a.status == ApplicationStatus.REJECTED]
    payload: list[tuple[NotificationType, str, str, str, bool]] = []

    if offers:
        payload.append(
            (
                NotificationType.OFFER,
                f"Offer from {offers[0].job.company.name}",
                f"{offers[0].job.company.name} extended an offer for {offers[0].job.title}.",
                f"/applications/{offers[0].id}",
                False,
            )
        )
    if interviews:
        payload.append(
            (
                NotificationType.INTERVIEW_SCHEDULED,
                f"Interview scheduled with {interviews[0].application.job.company.name}",
                "Your technical interview is confirmed. Preparation material is ready.",
                "/interviews",
                False,
            )
        )
    requires_user = [a for a in queue if a.automation_state == AutomationState.REQUIRES_USER]
    if requires_user:
        payload.append(
            (
                NotificationType.INPUT_REQUIRED,
                "One application needs your input",
                f"{requires_user[0].job.company.name} asks for your preferred start date.",
                "/queue",
                False,
            )
        )
    ready = [a for a in queue if a.automation_state == AutomationState.PAUSED]
    if ready:
        payload.append(
            (
                NotificationType.SYSTEM,
                "An application is ready for review",
                f"{ready[0].job.company.name} - {ready[0].job.title} is filled in and waiting for approval.",
                "/queue",
                True,
            )
        )
    if rejected:
        payload.append(
            (
                NotificationType.REJECTION,
                f"{rejected[0].job.company.name} passed on your application",
                "Keep going - your pipeline still looks healthy.",
                f"/applications/{rejected[0].id}",
                True,
            )
        )
    payload.append(
        (
            NotificationType.AUTOMATION_COMPLETED,
            "Daily automation finished",
            "Found 62 jobs, 24 matched, 9 high-match, 6 queued, 1 ready for review, 1 needs your input",
            "/automation",
            True,
        )
    )
    payload.append(
        (
            NotificationType.JOB_FOUND,
            "New high-match jobs found",
            "Several new roles above your 75% threshold were discovered this morning.",
            "/jobs",
            True,
        )
    )

    for notification_type, title, body, link, is_read in payload:
        row = notify(db, user.id, notification_type, title, body=body, link=link, meta={"seed": True})
        row.is_read = is_read
        row.created_at = now - timedelta(hours=created + 1)
        created += 1
    db.flush()
    return created


def _build_audit_story(db: Session, user: User, application: Application) -> int:
    """The §27 audit story for one application, end to end."""
    job = application.job
    base = application.applied_at or utcnow()
    company = job.company.name
    entries: tuple[tuple[str, str, int, AuditLevel], ...] = (
        ("job.found", f"{company} - {job.title} found on {(application.source or JobSourceType.OTHER).value}", -70, AuditLevel.INFO),
        ("job.analyzed", f"{company} - {job.title}: {application.match_score}% match", -65, AuditLevel.INFO),
        ("application.created", f"Queued {company} - {job.title}", -60, AuditLevel.INFO),
        ("application.answers_generated", "10 answers generated from the profile and resume", -45, AuditLevel.INFO),
        ("application.form_detected", "Application form detected: 12 fields, 0 blockers", -30, AuditLevel.INFO),
        ("application.field_filled", "Filled 11/12 fields; 1 left for the user", -25, AuditLevel.INFO),
        ("application.paused", "Paused for review before submitting", -20, AuditLevel.WARN),
        ("application.resumed", "User approved the prepared answers", -10, AuditLevel.INFO),
        ("application.approved", "Application approved by the user", -5, AuditLevel.INFO),
        ("application.submitted", f"Application submitted to {company}", 0, AuditLevel.INFO),
    )
    for action, message, offset_minutes, level in entries:
        entry = audit(
            db,
            action=action,
            message=message,
            user_id=user.id,
            application_id=application.id,
            actor=Actor.AUTOMATION if action.startswith(("job.", "application.form", "application.field", "application.answers")) else Actor.USER,
            level=level,
            meta={"seed": True},
        )
        entry.created_at = base + timedelta(minutes=offset_minutes)
    db.flush()
    return len(entries)


# --------------------------------------------------------------------------- automation


def _build_automation_run(db: Session, user: User, config: AutomationConfig, summary: SeedSummary) -> AutomationRun:
    """One finished run from yesterday, with realistic steps and stats."""
    from app.modules.automation.service import config_snapshot

    started = utcnow() - timedelta(days=1, hours=2)
    stats = {
        "jobs_found": 62,
        "jobs_new": 18,
        "duplicates_merged": 9,
        "jobs_analyzed": 18,
        "jobs_matched": 24,
        "high_match": 9,
        "queued": summary.queued or 6,
        "prepared": 4,
        "submitted": 0,
        "requires_user": 1,
        "ready_for_review": 1,
        "failed": 0,
        "skipped_limit": 2,
        "filtered_out": 38,
        "filter_reasons": {
            "below_min_score": 24,
            "too_old": 5,
            "avoid_company": 2,
            "excluded_keyword": 1,
            "already_applied": 4,
            "already_skipped": 0,
            "limit_reached": 2,
        },
    }
    step_plan: tuple[tuple[str, str, str], ...] = (
        ("search", "SUCCESS", "10 sources enabled"),
        ("collect", "SUCCESS", "62 listings collected"),
        ("dedupe", "SUCCESS", "18 new, 9 merged"),
        ("analyze", "SUCCESS", "18 jobs analyzed"),
        ("filter", "SUCCESS", "8/46 jobs passed the filters"),
        ("prioritize", "SUCCESS", "8 jobs prioritized"),
        ("enforce_limits", "SUCCESS", "6 within today's budget of 20"),
        ("queue", "SUCCESS", "6 applications queued"),
        ("generate_answers", "SUCCESS", "4 applications prepared"),
        ("autofill", "SUCCESS", "1 form filled, 1 needs a human"),
        ("approval_queue", "SUCCESS", "1 ready for review, 1 needs your input"),
        ("auto_submit", "SKIPPED", "Auto-submit is disabled; applications wait for your approval"),
        ("finish", "SUCCESS", "Found 62 jobs, 24 matched, 9 high-match, 6 queued, 1 ready for review, 1 need your input"),
    )
    steps: list[dict[str, Any]] = []
    cursor = started
    for name, status, message in step_plan:
        finished = cursor + timedelta(seconds=6)
        steps.append(
            {
                "step": name,
                "status": status,
                "started_at": cursor.isoformat(),
                "finished_at": finished.isoformat(),
                "duration_ms": 6000,
                "message": message,
                "data": {},
            }
        )
        cursor = finished

    run = AutomationRun(
        user_id=user.id,
        trigger=AutomationRunTrigger.SCHEDULED,
        status=AutomationRunStatus.SUCCESS,
        started_at=started,
        finished_at=cursor,
        current_step=None,
        stats=stats,
        steps=steps,
        config_snapshot=config_snapshot(config),
    )
    db.add(run)
    db.flush()
    audit(
        db,
        action="automation.run_finished",
        message="Automation run success: " + step_plan[-1][2],
        user_id=user.id,
        automation_run_id=run.id,
        actor=Actor.AUTOMATION,
        meta={"status": run.status.value, "seed": True},
    )
    db.flush()
    return run


def _configure_automation(db: Session, user: User) -> AutomationConfig:
    from app.modules.automation.service import compute_next_run_at, get_config

    config = get_config(db, user.id)
    config.enabled = True
    config.schedule_time = "09:00"
    config.timezone = "Asia/Kolkata"
    config.daily_application_limit = 20
    config.per_platform_limit = {JobSourceType.LINKEDIN.value: 8, JobSourceType.NAUKRI.value: 8}
    config.min_match_score = 75
    config.prioritize_priority_companies = True
    config.only_posted_within_hours = 72
    config.enabled_sources = []
    config.delay_between_actions_seconds = 2.0
    config.retry_limit = 3
    config.auto_submit_enabled = False
    config.auto_submit_sources = []
    config.auto_generate_cover_letters = True
    config.notify_on_input_required = True
    config.next_run_at = compute_next_run_at(config)
    db.flush()
    return config


# --------------------------------------------------------------------------- entry points


def seed_demo_data(db: Session, *, force: bool = False) -> SeedSummary:
    """Create (or recreate with ``force``) the whole demo dataset. Idempotent."""
    from app.modules.auth.service import create_user, get_user_by_email

    summary = SeedSummary(email=settings.DEMO_USER_EMAIL)
    rng = random.Random(SEED_RANDOM)

    existing = get_user_by_email(db, settings.DEMO_USER_EMAIL)
    if existing is not None and not force:
        summary.user_id = existing.id
        summary.messages.append("Demo user already exists - nothing to do (pass --force to rebuild).")
        logger.info("Demo user %s already exists; skipping seed", settings.DEMO_USER_EMAIL)
        return summary
    if existing is not None:
        _purge_user(db, existing)

    user = create_user(db, settings.DEMO_USER_EMAIL, settings.DEMO_USER_PASSWORD, DEMO_FULL_NAME)
    user.is_verified = True
    user.last_login_at = utcnow() - timedelta(hours=3)
    db.flush()
    summary.created = True
    summary.user_id = user.id

    _fill_profile(db, user)
    preference = _fill_preferences(db, user)
    _fill_company_preferences(db, user)
    summary.skills = _seed_skill_taxonomy(db)
    resume = _create_resume(db, user)

    logger.info("Discovering demo jobs...")
    jobs_found, jobs_new, duplicates, jobs = _discover_jobs(db, user, preference)
    summary.jobs = len(jobs)
    summary.jobs_new = jobs_new
    summary.duplicates_merged = duplicates
    logger.info("Discovery: %d listings, %d jobs, %d merged duplicates", jobs_found, len(jobs), duplicates)

    match_rows = _analyze(db, user, jobs)
    matches = {m.job_id: m for m in match_rows}
    summary.matches = len(match_rows)

    applications = _build_history(db, user, resume, jobs, matches, rng, summary)
    used = {a.job_id for a in applications}
    queue = _build_queue(db, user, resume, jobs, matches, used, rng, summary)
    interviews = _build_interviews(db, user, applications, rng)
    summary.interviews = len(interviews)
    summary.emails = _build_emails(db, user, applications, rng)
    summary.notifications = _build_notifications(db, user, applications, queue, interviews)
    if applications:
        summary.audit_entries = _build_audit_story(db, user, applications[0])

    config = _configure_automation(db, user)
    _build_automation_run(db, user, config, summary)
    summary.automation_runs = 1

    audit(
        db,
        action="system.seeded",
        message="Demo data seeded",
        user_id=user.id,
        actor=Actor.SYSTEM,
        meta=summary.as_dict(),
    )
    db.flush()

    logger.info(
        "Seed complete: user=%s jobs=%d matches=%d applications=%d queued=%d interviews=%d emails=%d "
        "notifications=%d audit=%d runs=%d skills=%d",
        summary.email,
        summary.jobs,
        summary.matches,
        summary.applications,
        summary.queued,
        summary.interviews,
        summary.emails,
        summary.notifications,
        summary.audit_entries,
        summary.automation_runs,
        summary.skills,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.seed", description="Seed the JobPilot AI demo data.")
    parser.add_argument("--force", action="store_true", help="delete the demo user's data and rebuild it")
    args = parser.parse_args(argv)

    configure_logging()
    with session_scope() as db:
        summary = seed_demo_data(db, force=args.force)
    if not summary.created:
        logger.info("Nothing seeded. %s", " ".join(summary.messages))
        return 0
    logger.info("Demo login: %s / %s", settings.DEMO_USER_EMAIL, settings.DEMO_USER_PASSWORD)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
