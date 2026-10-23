"""Regression tests for the round-2 correctness + scalability review.

Every test here pins a bug that was found by reading a flow end to end and then fixed.
Each one names the file it guards in its docstring so the link survives refactors.
"""
from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text, update
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.exceptions import ConflictError
from app.models.application import Application
from app.models.company import Company
from app.models.enums import ApplicationStatus, ApplicationType, JobSourceType, WorkMode
from app.models.job import Job, JobMatch, JobSource
from app.models.user import User

APPLICATIONS_API = "/api/v1/applications"
JOBS_API = "/api/v1/jobs"


# --------------------------------------------------------------------------- helpers


@contextmanager
def count_queries() -> "QueryCounter":
    """Count every statement the engine executes inside the block."""
    counter = QueryCounter()

    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        counter.statements.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before)


class QueryCounter:
    def __init__(self) -> None:
        self.statements: list[str] = []

    @property
    def count(self) -> int:
        return len(self.statements)


def current_user(client: TestClient, db: Session) -> User:
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    return db.get(User, uuid.UUID(me.json()["id"]))


def seed_jobs(db: Session, user_id: uuid.UUID, count: int) -> list[Job]:
    """``count`` companies, jobs, matches and applications — one of each, all linked."""
    now = datetime.now(timezone.utc)
    jobs: list[Job] = []
    for index in range(count):
        company = Company(
            name=f"Scale Co {index}",
            normalized_name=f"scaleco{index}",
            domain=f"scale{index}.test",
        )
        db.add(company)
        db.flush()
        job = Job(
            company_id=company.id,
            title=f"Engineer {index}",
            normalized_title=f"engineer {index}",
            description="React, Node.js and PostgreSQL.",
            location="Bangalore, India",
            normalized_location="bangalore",
            work_mode=WorkMode.HYBRID,
            salary_min=1_200_000,
            salary_max=1_800_000,
            salary_currency="INR",
            experience_min=1.0,
            experience_max=4.0,
            required_skills=["React"],
            preferred_skills=[],
            posted_at=now - timedelta(hours=index),
            canonical_url=f"https://scale.test/jobs/{index}",
            apply_url=f"https://scale.test/apply/{index}",
            application_type=ApplicationType.EASY_APPLY,
            dedupe_hash=uuid.uuid4().hex,
        )
        db.add(job)
        db.flush()
        db.add(
            JobSource(
                job_id=job.id,
                source=JobSourceType.LINKEDIN,
                external_id=f"scale-{index}-{uuid.uuid4().hex[:8]}",
                url=job.canonical_url,
                apply_url=job.apply_url,
                application_type=ApplicationType.EASY_APPLY,
                posted_at=job.posted_at,
                discovered_at=now,
                last_seen_at=now,
            )
        )
        db.add(
            JobMatch(
                job_id=job.id,
                user_id=user_id,
                match_score=50 + (index % 50),
                skill_score=60,
                experience_score=60,
                location_score=60,
                title_score=60,
                missing_skills=[],
                explanation="seeded",
                analyzed_at=now,
            )
        )
        db.add(
            Application(
                user_id=user_id,
                job_id=job.id,
                status=ApplicationStatus.QUEUED,
                match_score=50 + (index % 50),
                source=JobSourceType.LINKEDIN,
            )
        )
        jobs.append(job)
    db.commit()
    return jobs


# --------------------------------------------------------------------------- scalability


def test_queue_page_does_not_scale_queries_with_page_size(auth_client: TestClient, db: Session) -> None:
    """``applications.service._job_cards`` used to call ``jobs.service.get_job_detail``
    once per row (4 statements each): a 20-row queue page cost 83 queries. It must now
    batch-load, i.e. cost the same number of statements whatever the page size."""
    user = current_user(auth_client, db)
    seed_jobs(db, user.id, 30)

    with count_queries() as small:
        response = auth_client.get(f"{APPLICATIONS_API}/queue?page_size=5")
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 5

    with count_queries() as large:
        response = auth_client.get(f"{APPLICATIONS_API}/queue?page_size=25")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 25
    assert all(item["job"] is not None for item in items), "every queue row still carries its job card"

    assert large.count == small.count, (
        f"queue is N+1: {small.count} queries for 5 rows vs {large.count} for 25"
    )
    assert large.count <= 15, f"queue page should stay in single digits, got {large.count}"


def test_jobs_list_does_not_scale_queries_with_page_size(auth_client: TestClient, db: Session) -> None:
    """``jobs.service.list_jobs`` must resolve company priorities and sources in bulk."""
    user = current_user(auth_client, db)
    seed_jobs(db, user.id, 30)

    with count_queries() as small:
        response = auth_client.get(f"{JOBS_API}?page_size=5")
    assert response.status_code == 200, response.text

    with count_queries() as large:
        response = auth_client.get(f"{JOBS_API}?page_size=25")
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 25

    assert large.count == small.count, (
        f"jobs list is N+1: {small.count} queries for 5 rows vs {large.count} for 25"
    )
    assert large.count <= 10


def test_application_list_paginates_in_sql(auth_client: TestClient, db: Session) -> None:
    """``GET /applications`` used to load every application the user has ever had and
    slice the page in Python. One page must now read at most one page of rows."""
    user = current_user(auth_client, db)
    seed_jobs(db, user.id, 40)

    with count_queries() as counter:
        response = auth_client.get(f"{APPLICATIONS_API}?page_size=10")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 40
    assert len(body["items"]) == 10
    assert counter.count <= 8

    limited = [s for s in counter.statements if " LIMIT " in s.upper()]
    assert limited, "the page query must carry a SQL LIMIT"

    # Paging is stable: no row appears on two pages.
    first = {item["id"] for item in body["items"]}
    second = auth_client.get(f"{APPLICATIONS_API}?page_size=10&page=2").json()["items"]
    assert not (first & {item["id"] for item in second})


def test_queue_ready_filter_applies_before_pagination(auth_client: TestClient, db: Session) -> None:
    """``?ready=`` is now a SQL predicate; with no answers prepared nothing is ready."""
    user = current_user(auth_client, db)
    seed_jobs(db, user.id, 5)

    response = auth_client.get(f"{APPLICATIONS_API}/queue?ready=true")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0

    response = auth_client.get(f"{APPLICATIONS_API}/queue?ready=false")
    assert response.json()["total"] == 5


def test_hot_query_paths_have_composite_indexes() -> None:
    """Every user-scoped list endpoint filters on ``user_id`` *and* sorts/filters on a
    second column; without a composite index those are full scans on PostgreSQL."""
    from app.models import Base

    expected = {
        "applications": {"ix_applications_user_status", "ix_applications_user_applied_at"},
        "application_events": {"ix_application_events_application_created"},
        "job_matches": {"ix_job_matches_user_score"},
        "email_messages": {"ix_email_messages_user_received_at"},
        "audit_logs": {"ix_audit_logs_user_created_at"},
        "notifications": {"ix_notifications_user_read_created"},
        "interviews": {"ix_interviews_user_scheduled_at"},
    }
    # Metadata is keyed by the schema-qualified name now that the tables live in named
    # schemas ("transaction.applications", not "applications"), so look each one up by
    # its bare name rather than hardcoding which schema it ended up in.
    by_name = {table.name: table for table in Base.metadata.tables.values()}
    for table, names in expected.items():
        assert table in by_name, f"no table named {table} in the metadata"
        present = {index.name for index in by_name[table].indexes}
        assert names <= present, f"{table} is missing {names - present}"


# --------------------------------------------------------------------------- UTC datetimes


def _iso_datetimes(payload: object, out: list[str] | None = None) -> list[str]:
    """Every string in ``payload`` that looks like an ISO-8601 datetime."""
    out = [] if out is None else out
    if isinstance(payload, dict):
        for value in payload.values():
            _iso_datetimes(value, out)
    elif isinstance(payload, list):
        for value in payload:
            _iso_datetimes(value, out)
    elif isinstance(payload, str) and len(payload) >= 19 and payload[4] == "-" and payload[10] == "T":
        try:
            datetime.fromisoformat(payload)
        except ValueError:
            return out
        out.append(payload)
    return out


def test_naive_datetimes_load_back_timezone_aware(auth_client: TestClient, db: Session) -> None:
    """A naive timestamp must never reach the application layer from either backend.

    PostgreSQL's ``timestamptz`` always hands back an aware value, but SQLite (the
    no-Docker local run) has no time-zone type and drops tzinfo entirely, which made
    every client read UTC instants as local time. ``app.models.base.UTCDateTime``
    re-attaches UTC on read so both backends behave identically.
    """
    # The decorator carries the guarantee, so assert it directly — this holds whichever
    # database the suite is pointed at.
    from app.models.base import UTCDateTime

    naive = datetime(2026, 3, 1, 8, 30)
    loaded = UTCDateTime().process_result_value(naive, None)
    assert loaded.tzinfo is not None, "naive datetime leaked out of the DB"
    assert loaded.utcoffset() == timedelta(0)
    assert loaded.replace(tzinfo=None) == naive, "the instant must not be shifted, only labelled"

    # And end to end: a value written without a zone comes back aware.
    user = current_user(auth_client, db)
    job = seed_jobs(db, user.id, 1)[0]
    application = db.scalars(select(Application).where(Application.job_id == job.id)).one()
    db.execute(update(Application).where(Application.id == application.id).values(applied_at=naive))
    db.commit()
    db.expire_all()

    reloaded = db.get(Application, application.id)
    assert reloaded.applied_at is not None
    assert reloaded.applied_at.tzinfo is not None
    assert reloaded.applied_at.utcoffset() == timedelta(0)
    assert reloaded.created_at.tzinfo is not None


@pytest.mark.parametrize(
    "url",
    [
        f"{APPLICATIONS_API}?page_size=5",
        f"{JOBS_API}?page_size=5",
        "/api/v1/auth/me",
        "/api/v1/audit",
        f"{APPLICATIONS_API}/queue?page_size=5",
    ],
)
def test_api_datetimes_are_offset_aware(auth_client: TestClient, db: Session, url: str) -> None:
    """Contract §0: "datetimes are timezone-aware UTC, ISO-8601 in JSON". On SQLite they
    used to serialise as ``2026-09-19T10:42:58.733949`` — no offset — so a browser in
    Asia/Kolkata read every instant 5h30m early."""
    user = current_user(auth_client, db)
    seed_jobs(db, user.id, 3)

    response = auth_client.get(url)
    assert response.status_code == 200, response.text
    stamps = _iso_datetimes(response.json())
    assert stamps, f"{url} returned no datetimes to check"
    naive = [s for s in stamps if not (s.endswith("Z") or "+" in s[10:] or s[10:].count("-") > 0)]
    assert not naive, f"{url} returned offset-less datetimes: {naive[:3]}"


# --------------------------------------------------------------------------- application lifecycle


def test_unstarted_claim_still_blocks_a_second_run(db: Session) -> None:
    """``applications/executor.py``: ``run_in_background`` claims the slot *before*
    starting the thread, and ``Thread.is_alive()`` is False until ``start()`` - so the
    registry used to drop its own claim and allow a duplicate run (= duplicate submit)."""
    from app.modules.applications import executor

    application_id = uuid.uuid4()
    executor.reset()
    try:
        executor._claim(application_id, threading.Thread(target=lambda: None, name="first"))
        assert executor.is_running(application_id) is True
        with pytest.raises(ConflictError):
            executor._claim(application_id, threading.Thread(target=lambda: None, name="second"))
    finally:
        executor.reset()


def test_resume_automation_refuses_an_already_submitted_application(auth_client: TestClient, db: Session) -> None:
    """``applications/service.py::resume_automation`` had no already-submitted guard, so
    it re-drove the adapter and submitted the same form a second time."""
    from app.modules.applications import service as applications_service

    user = current_user(auth_client, db)
    job = seed_jobs(db, user.id, 1)[0]
    application = db.scalars(select(Application).where(Application.job_id == job.id)).one()
    application.status = ApplicationStatus.APPLIED
    application.applied_at = datetime.now(timezone.utc)
    db.commit()

    with pytest.raises(ConflictError):
        applications_service.resume_automation(db, application, None, run_in_background=False)

    response = auth_client.post(
        f"{APPLICATIONS_API}/{application.id}/resume-automation", json={"run_in_background": False}
    )
    assert response.status_code == 409, response.text


def test_approve_is_refused_while_a_run_is_in_flight(auth_client: TestClient, db: Session) -> None:
    """``approve()`` drives the adapter exactly like a run does, so it has to respect the
    same single-flight registry - otherwise Approve during a run means two submissions."""
    from app.models.user import User as UserModel
    from app.modules.applications import executor
    from app.modules.applications import service as applications_service

    user = current_user(auth_client, db)
    job = seed_jobs(db, user.id, 1)[0]
    application = db.scalars(select(Application).where(Application.job_id == job.id)).one()
    application.status = ApplicationStatus.IN_PROGRESS
    db.commit()

    executor.reset()
    # What a background POST /{id}/start leaves behind for several seconds.
    executor._claim(application.id, threading.Thread(target=lambda: None, name="in-flight-run"))
    try:
        with pytest.raises(ConflictError):
            applications_service.approve(db, application, db.get(UserModel, user.id))
    finally:
        executor.reset()


def test_two_concurrent_approvals_submit_exactly_once(auth_client: TestClient, db: Session) -> None:
    """``executor.is_running()`` is a *test*, not a claim: two simultaneous approvals both
    passed the check and both drove the adapter, creating a duplicate application at the
    ATS and over-counting the daily limit. ``approve()`` now runs under the atomic claim,
    so the loser is refused before it touches anything."""
    from app.models.user import User as UserModel
    from app.modules.applications import executor
    from app.modules.applications import service as applications_service

    user = current_user(auth_client, db)
    job = seed_jobs(db, user.id, 1)[0]
    application = db.scalars(select(Application).where(Application.job_id == job.id)).one()
    application.status = ApplicationStatus.IN_PROGRESS
    db.commit()

    submissions: list[str] = []
    entered = threading.Event()
    release = threading.Event()

    def fake_submit(_db, app):  # noqa: ANN001 - stands in for the adapter call
        submissions.append(str(app.id))
        entered.set()
        release.wait(timeout=10)
        raise RuntimeError("stop before a real submission")

    original_review = applications_service.build_review
    original_submit = applications_service._submit_through_adapter
    applications_service.build_review = lambda _db, _app: type(
        "_Review", (), {"can_submit": True, "blockers": [], "missing": []}
    )()
    applications_service._submit_through_adapter = fake_submit

    def first_approval() -> None:
        try:
            applications_service.approve(db, application, db.get(UserModel, user.id))
        except Exception:  # the deliberate RuntimeError above
            pass

    executor.reset()
    winner = threading.Thread(target=first_approval, name="approve-winner")
    try:
        winner.start()
        assert entered.wait(timeout=10), "the first approval never reached the adapter"
        # The loser is rejected by the claim itself, before it reads or writes anything.
        with pytest.raises(ConflictError):
            applications_service.approve(db, application, db.get(UserModel, user.id))
    finally:
        release.set()
        winner.join(timeout=10)
        applications_service.build_review = original_review
        applications_service._submit_through_adapter = original_submit
        executor.reset()

    assert submissions == [str(application.id)], (
        f"the adapter was asked to submit {len(submissions)} times"
    )


# --------------------------------------------------------------------------- automation


def test_a_dry_run_does_not_consume_the_days_scheduled_slot(auth_client: TestClient, db: Session) -> None:
    """``automation/pipeline.py::_finish`` set ``last_run_at`` for dry runs too, so
    previewing at 08:00 silently cancelled the real 09:00 scheduled run."""
    from app.models.enums import AutomationRunTrigger
    from app.modules.automation import locks, pipeline
    from app.modules.automation.service import get_config
    from app.worker import scheduler

    user = current_user(auth_client, db)
    config = get_config(db, user.id)
    config.enabled = True
    # Midnight, so the scheduled slot has already opened whatever the wall clock says (a 09:00
    # slot is not due yet before 09:00 IST, which made this test fail every early morning).
    config.schedule_time = "00:00"
    config.timezone = "Asia/Kolkata"
    config.last_run_at = None
    db.flush()

    locks.reset_locks()
    try:
        pipeline.run_pipeline(
            user.id, AutomationRunTrigger.MANUAL, dry_run=True, db=db, sleep_fn=lambda _s: None
        )
    finally:
        locks.reset_locks()
    db.commit()

    assert config.last_run_at is None, "a dry run must not count as the day's automation run"
    assert user.id in scheduler.due_users(db, datetime.now(timezone.utc))


def test_cancel_does_not_release_a_lock_it_does_not_own(auth_client: TestClient, db: Session) -> None:
    """``cancel_run`` force-released the per-user lock while the pipeline was still
    executing its current step, letting a second run start and spend the daily limit twice."""
    from app.models.enums import AutomationRunTrigger
    from app.modules.automation import locks
    from app.modules.automation import service as automation_service

    user = current_user(auth_client, db)
    locks.reset_locks()
    token = locks.acquire_lock(user.id)  # held by the still-running pipeline
    assert token is not None
    try:
        run = automation_service.create_run(db, user.id, AutomationRunTrigger.MANUAL)
        db.flush()
        automation_service.cancel_run(db, user.id, run.id)
        assert locks.is_locked(user.id), "cancel dropped the lock the live pipeline still owns"
    finally:
        locks.release_lock(user.id, token)
        locks.reset_locks()


def test_a_contended_manual_run_never_strands_the_row_at_running(auth_client: TestClient, db: Session) -> None:
    """A manual run whose background thread loses the lock race used to leave the row
    ``RUNNING`` for ever, so every later run got a permanent 409."""
    from app.models.automation import AutomationRun
    from app.models.enums import AutomationRunStatus
    from app.modules.automation import locks
    from app.modules.automation import service as automation_service

    user = current_user(auth_client, db)
    locks.reset_locks()
    spawned: list[tuple] = []
    original_spawn = automation_service._spawn
    automation_service._spawn = lambda target, *args, **kwargs: spawned.append((target, args))
    try:
        run = automation_service.start_manual_run(db, user.id, background=True)
        assert run.status is AutomationRunStatus.RUNNING
        # Taking the lock in the request closes the guard/insert race outright.
        assert locks.is_locked(user.id)
        target, args = spawned[0]
        target(*args)  # the thread body, run inline
        db.expire_all()
        row = db.get(AutomationRun, run.id)
        assert row.status is not AutomationRunStatus.RUNNING, "the run row is stranded RUNNING"
        assert row.finished_at is not None
        automation_service.ensure_not_running(db, user.id)  # must not raise
    finally:
        automation_service._spawn = original_spawn
        locks.reset_locks()


# --------------------------------------------------------------------------- profiles & jobs


@pytest.mark.parametrize("field", ["skills", "education", "skill_experience", "work_authorization"])
def test_put_profile_accepts_a_null_json_field(auth_client: TestClient, field: str) -> None:
    """``ProfileUpdate.skills`` is ``list | None``, so ``null`` is a valid body - but it
    reached the NOT NULL JSON column, broke ``ProfileRead`` and returned 500 for the
    whole request, losing the other edits with it."""
    response = auth_client.put("/api/v1/profile", json={"city": "Pune", field: None})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["city"] == "Pune"
    assert body[field] in ([], {})


@pytest.mark.parametrize("field", ["desired_titles", "work_modes", "excluded_keywords"])
def test_put_preferences_accepts_a_null_json_field(auth_client: TestClient, field: str) -> None:
    response = auth_client.put("/api/v1/preferences/job", json={"notice_period_days": 30, field: None})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["notice_period_days"] == 30
    assert body[field] == []


def test_min_match_score_zero_is_respected(auth_client: TestClient, db: Session) -> None:
    """``0`` is a settable floor ("show me everything"); ``value or DEFAULT`` turned it
    into 75, so /matching/summary contradicted /preferences/job."""
    user = current_user(auth_client, db)
    seed_jobs(db, user.id, 3)
    assert auth_client.put("/api/v1/preferences/job", json={"min_match_score": 0}).status_code == 200

    summary = auth_client.get("/api/v1/matching/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["min_match_score"] == 0
    assert body["matched_at_or_above_min"] == body["analyzed"]


def test_jobs_list_rejects_an_unknown_status_filter(auth_client: TestClient) -> None:
    """``?status=`` is a free-form str on the router; an unknown value raised ValueError
    out of the service and surfaced as a 500."""
    response = auth_client.get(JOBS_API, params={"status": "not-a-status"})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_status"
    assert auth_client.get(JOBS_API, params={"status": "NONE"}).status_code == 200
    assert auth_client.get(JOBS_API, params={"status": "queued"}).status_code == 200


def _discovered(external_id: str, company_name: str) -> object:
    from app.modules.adapters.base import DiscoveredJob

    return DiscoveredJob(
        source=JobSourceType.LINKEDIN,
        external_id=external_id,
        url=f"https://x.test/{external_id}",
        title="Backend Engineer",
        company_name=company_name,
        location="Bangalore",
        work_mode=None,
        employment_type=None,
        description="d" * 200,
        required_skills=[],
        preferred_skills=[],
        experience_min=None,
        experience_max=None,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        posted_at=None,
        apply_url=None,
        application_type=ApplicationType.EASY_APPLY,
    )


def test_one_unusable_listing_does_not_lose_the_whole_ingest_batch(auth_client: TestClient, db: Session) -> None:
    """``get_or_create_company`` raises on a name that normalises to "", which aborted
    ``ingest_discovered`` mid-loop and rolled back every job from every adapter."""
    from app.modules.jobs import service as jobs_service

    user = current_user(auth_client, db)
    result = jobs_service.ingest_discovered(
        db, user.id, [_discovered("li-bad", "   "), _discovered("li-good", "Acme Cloud")]
    )
    assert result.jobs_new == 1
    assert result.skipped == 1


def test_discovery_forwards_the_users_work_modes(db: Session) -> None:
    """Every adapter honours ``SearchQuery.work_modes``; ``build_search_query`` dropped
    it, so a "remote only" candidate still got onsite postings."""
    from app.models.profile import JobPreference
    from app.modules.jobs import service as jobs_service

    preference = JobPreference(
        user_id=uuid.uuid4(),
        desired_titles=["Backend Engineer"],
        preferred_locations=["Bangalore"],
        work_modes=["REMOTE"],
    )
    query = jobs_service.build_search_query(preference, 10)
    assert [str(getattr(mode, "value", mode)) for mode in query.work_modes] == ["REMOTE"]


def test_a_job_card_never_repeats_a_source(auth_client: TestClient, db: Session) -> None:
    """Two postings from one platform that share a dedupe hash merge into one Job with
    two JobSource rows of the same type - the card must still show one chip."""
    from app.modules.jobs import service as jobs_service

    user_id = current_user(auth_client, db).id
    job = seed_jobs(db, user_id, 1)[0]
    now = datetime.now(timezone.utc)
    db.add(
        JobSource(
            job_id=job.id,
            source=JobSourceType.LINKEDIN,  # same platform, different posting
            external_id=f"dup-{uuid.uuid4().hex[:8]}",
            url="https://scale.test/jobs/dup",
            apply_url=None,
            application_type=ApplicationType.EASY_APPLY,
            posted_at=now,
            discovered_at=now,
            last_seen_at=now,
        )
    )
    db.commit()
    db.expire_all()

    detail = jobs_service.get_job_detail(db, user_id, job.id)
    assert detail.sources == [JobSourceType.LINKEDIN]
    assert len(detail.job_sources) == 2


# --------------------------------------------------------------------------- emails & dashboard


def _incoming(provider_id: str, sender: str, subject: str, body: str) -> object:
    from app.modules.emails.schemas import IncomingEmail

    return IncomingEmail(
        provider_message_id=provider_id,
        sender=sender,
        subject=subject,
        body_text=body,
        received_at=datetime.now(timezone.utc),
    )


def _applied(db: Session, user_id: uuid.UUID, *, company: str, domain: str | None = None,
             status: ApplicationStatus = ApplicationStatus.APPLIED) -> Application:
    """One company + job + application, committed and already 'sent'."""
    now = datetime.now(timezone.utc)
    row = Company(name=company, normalized_name=company.lower().replace(" ", ""), domain=domain)
    db.add(row)
    db.flush()
    job = Job(
        company_id=row.id,
        title="Software Engineer",
        normalized_title="software engineer",
        description="React, Node.js and PostgreSQL.",
        dedupe_hash=uuid.uuid4().hex,
        application_type=ApplicationType.ATS_FORM,
        apply_url="https://example.test/apply",
    )
    db.add(job)
    db.flush()
    db.add(
        JobMatch(
            job_id=job.id,
            user_id=user_id,
            match_score=90,
            skill_score=90,
            experience_score=90,
            location_score=90,
            title_score=90,
            missing_skills=[],
            explanation="seeded",
            analyzed_at=now,
        )
    )
    application = Application(
        user_id=user_id,
        job_id=job.id,
        status=status,
        source=JobSourceType.LINKEDIN,
        match_score=90,
        applied_at=now - timedelta(days=2),
        last_update_at=now,
    )
    db.add(application)
    db.commit()
    return application


def test_a_bulk_job_alert_does_not_advance_an_application(auth_client: TestClient, db: Session) -> None:
    """``emails/linker.py``: the job-title strategy is the weakest one, and a routine
    LinkedIn alert ("Software Engineer: 12 new jobs") used to link to - and advance - a
    real application, poisoning the response rate and the funnel."""
    from app.modules.emails import service as emails_service

    user = current_user(auth_client, db)
    application = _applied(db, user.id, company="Acme Cloud")

    email = emails_service.ingest_message(
        db,
        user.id,
        _incoming(
            "linkedin-alert-1",
            "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
            "Software Engineer: 12 new jobs in Bangalore",
            "Your job alert for Software Engineer. We are hiring for several open roles - see them now.",
        ),
    )
    db.commit()
    db.expire_all()

    assert email.application_id is None, f"a bulk job alert linked by {email.matched_by}"
    assert email.status_applied is False
    assert db.get(Application, application.id).status is ApplicationStatus.APPLIED


def test_an_unrelated_email_does_not_teach_the_global_company_registry(auth_client: TestClient, db: Session) -> None:
    """``companies`` has no ``user_id``: learning a sender domain from a newsletter that
    merely mentions the company name leaks the highest-trust match to every other user."""
    from app.modules.emails import service as emails_service

    user = current_user(auth_client, db)
    _applied(db, user.id, company="Google")  # no known domain yet
    google = db.scalars(select(Company).where(Company.normalized_name == "google")).one()

    emails_service.ingest_message(
        db,
        user.id,
        _incoming(
            "newsletter-1",
            "Tech Weekly <digest@tech-weekly.news>",
            "This week: Google ships a new model",
            "Our weekly roundup of what shipped.",
        ),
    )
    db.commit()
    db.refresh(google)
    assert google.email_domains == [], f"a newsletter poisoned the global company row: {google.email_domains}"


def test_an_interview_email_never_schedules_on_a_terminal_application(auth_client: TestClient, db: Session) -> None:
    """``next_status_for`` correctly refuses to move a WITHDRAWN application, but the
    interview row was created unconditionally."""
    from app.models.interview import Interview
    from app.modules.emails import service as emails_service

    user = current_user(auth_client, db)
    application = _applied(
        db, user.id, company="Acme Cloud", domain="acme.test", status=ApplicationStatus.WITHDRAWN
    )

    email = emails_service.ingest_message(
        db,
        user.id,
        _incoming(
            "withdrawn-interview-1",
            "Acme Recruiting <recruiting@acme.test>",
            "Interview invitation - Software Engineer",
            "We would like to schedule a technical interview. Please share your availability.",
        ),
    )
    db.commit()
    db.expire_all()

    assert email.status_applied is False
    assert db.get(Application, application.id).status is ApplicationStatus.WITHDRAWN
    assert db.scalars(select(Interview).where(Interview.application_id == application.id)).all() == []


def test_repeating_a_manual_classification_is_idempotent(auth_client: TestClient, db: Session) -> None:
    """A no-op override used to append another EMAIL_LINKED event and another
    notification every single time, contradicting "a status change never notifies twice"."""
    from app.models.application import ApplicationEvent
    from app.models.notification import Notification
    from app.modules.emails import service as emails_service

    user = current_user(auth_client, db)
    application = _applied(db, user.id, company="Initech", domain="initech.test")
    email = emails_service.ingest_message(
        db,
        user.id,
        _incoming(
            "initech-1",
            "Initech Careers <no-reply@initech.test>",
            "Thank you for applying to Initech",
            "We have received your application.",
        ),
    )
    db.commit()

    def counts() -> tuple[int, int]:
        db.expire_all()
        events = db.scalars(
            select(ApplicationEvent).where(ApplicationEvent.application_id == application.id)
        ).all()
        notifications = db.scalars(select(Notification).where(Notification.user_id == user.id)).all()
        return len(events), len(notifications)

    before = counts()
    for _ in range(3):
        response = auth_client.post(
            f"/api/v1/emails/{email.id}/classify", json={"classification": "APPLICATION_RECEIVED"}
        )
        assert response.status_code == 200, response.text
    assert counts() == before, "a repeated no-op override duplicated events / notifications"


def test_relinking_an_email_does_not_advance_two_applications(auth_client: TestClient, db: Session) -> None:
    """``unlink`` deliberately leaves the old application's status alone, so silently
    moving a link would advance two applications off one email."""
    from app.models.interview import Interview
    from app.modules.emails import service as emails_service

    user = current_user(auth_client, db)
    first = _applied(db, user.id, company="First Co")
    second = _applied(db, user.id, company="Second Co")
    email = emails_service.ingest_message(
        db,
        user.id,
        _incoming(
            "relink-1",
            "hr@unknown-sender.test",
            "Interview invitation",
            "We would like to schedule a call.",
        ),
    )
    db.commit()

    linked = auth_client.post(f"/api/v1/emails/{email.id}/link", json={"application_id": str(first.id)})
    assert linked.status_code == 200, linked.text
    moved = auth_client.post(f"/api/v1/emails/{email.id}/link", json={"application_id": str(second.id)})
    assert moved.status_code == 409, moved.text
    db.expire_all()
    assert db.get(Application, second.id).status is ApplicationStatus.APPLIED
    assert db.scalars(select(Interview).where(Interview.application_id == second.id)).all() == []

    # The documented flow still works.
    assert auth_client.post(f"/api/v1/emails/{email.id}/unlink").status_code == 200
    assert auth_client.post(
        f"/api/v1/emails/{email.id}/link", json={"application_id": str(second.id)}
    ).status_code == 200


def test_response_rate_never_exceeds_one_hundred_percent(auth_client: TestClient, db: Session) -> None:
    """The numerator was not a subset of the denominator: an application that replied and
    was then SKIPPED from the Jobs page stayed in ``responses`` but left ``applications``."""
    from app.modules.dashboard import service as dashboard
    from app.modules.jobs.service import skip_job

    user = current_user(auth_client, db)
    _applied(db, user.id, company="Live Co")
    for index in range(2):
        gone = _applied(db, user.id, company=f"Gone Co {index}", status=ApplicationStatus.INTERVIEW)
        gone.last_response_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.flush()
        skip_job(db, user.id, gone.job_id, "no longer interested")
    db.commit()
    db.expire_all()

    stats = dashboard.build_stats(db, user.id)
    assert 0.0 <= stats.response_rate <= 100.0, f"response_rate={stats.response_rate}"
    assert 0.0 <= stats.interview_rate <= 100.0
    assert 0.0 <= stats.offer_rate <= 100.0
    assert stats.totals.responses <= stats.totals.applications


def test_dashboard_funnel_is_monotonic(auth_client: TestClient, db: Session) -> None:
    """A manually created Interview on an APPLIED application made ``interviews`` exceed
    ``responses``. An interview *is* a response, so it must fold into that set."""
    from app.modules.dashboard import service as dashboard

    user = current_user(auth_client, db)
    application = _applied(db, user.id, company="Globex")
    created = auth_client.post(
        "/api/v1/interviews",
        json={
            "application_id": str(application.id),
            "interview_type": "TECHNICAL",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    db.expire_all()

    stages = dashboard.build_charts(db, user.id, "30d").funnel
    counts = [stage.count for stage in stages]
    ordered = [(stage.stage, stage.count) for stage in stages]
    # 'matched' vs 'queued' compare different populations by design (§14); the rest must not invert.
    tail = [c for name, c in ordered if name not in {"discovered", "matched", "queued"}]
    assert all(tail[i] >= tail[i + 1] for i in range(len(tail) - 1)), ordered


def test_chart_window_starts_at_local_midnight_across_dst(auth_client: TestClient, db: Session) -> None:
    """``day_start - timedelta(days=N)`` is N*24h, which lands on 01:00 local across a
    DST change and silently drops the first day of the window."""
    from app.modules.automation.service import get_config
    from app.modules.dashboard import service as dashboard

    user = current_user(auth_client, db)
    config = get_config(db, user.id)
    config.timezone = "America/Los_Angeles"
    db.flush()

    now = datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc)        # 2026-11-02 12:00 PST
    application = _applied(db, user.id, company="DST Co")
    application.applied_at = datetime(2026, 10, 27, 7, 30, tzinfo=timezone.utc)  # 00:30 PDT
    db.commit()

    charts = dashboard.build_charts(db, user.id, "7d", now=now)
    assert str(charts.start_date) == "2026-10-27"
    assert sum(day.count for day in charts.applications_per_day) == 1, [
        (str(day.date), day.count) for day in charts.applications_per_day
    ]
    assert dashboard.build_stats(db, user.id, now=now).week.applications == 1


def test_skill_years_keys_agree_across_the_two_question_paths() -> None:
    """``ai.answer_rules.infer_question_key`` produced ``skill_years:React`` while the
    browser mapper and ``CandidateContext.flat`` use ``skill_years:react`` - two keys for
    one fact, so an already-answered question reappeared on the review screen."""
    from app.modules.ai.answer_rules import infer_question_key
    from app.modules.browser.mapper import FieldMapper
    from app.modules.browser.schemas import DetectedField
    from app.models.enums import FieldType

    inferred = infer_question_key("Years of experience with React?")
    mapped = FieldMapper().map(
        DetectedField(
            selector="#react_years",
            label="Years of experience with React?",
            field_type=FieldType.NUMBER,
            required=True,
        )
    )
    assert inferred == "skill_years:react"
    assert mapped.canonical_key == inferred
