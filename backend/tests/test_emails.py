"""Tests for the emails module: classifier, linker, ingestion pipeline and API (§13)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.application import Application, ApplicationEvent
from app.models.audit import AuditLog
from app.models.base import utcnow
from app.models.company import Company
from app.models.email import EmailMessage
from app.models.enums import (
    Actor,
    ApplicationEventType,
    ApplicationStatus,
    ApplicationType,
    EmailClassification,
    InterviewStatus,
    JobSourceType,
    NotificationType,
)
from app.models.interview import Interview
from app.models.job import Job
from app.models.notification import Notification
from app.models.profile import UserProfile
from app.models.user import User
from app.modules.companies.service import normalize_company_name
from app.modules.emails import classifier, linker, service
from app.modules.emails.gmail_client import GmailClient, build_query, parse_message, strip_html
from app.modules.emails.schemas import IncomingEmail

API = "/api/v1/emails"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _local_status_updates(monkeypatch):
    """Pin status changes to the local fallback.

    ``applications.service`` is written by another agent in parallel; these tests assert
    on the email pipeline itself, so they must not depend on whichever implementation is
    on disk. One test below monkeypatches a stub module to prove the delegation path.
    """
    monkeypatch.setattr(service, "_applications_service", lambda: None)


@pytest.fixture
def user(db) -> User:
    row = User(
        email="emails-tester@example.com",
        hashed_password=hash_password("StrongPass123!"),
        full_name="Emails Tester",
    )
    db.add(row)
    db.flush()
    db.add(UserProfile(user_id=row.id, city="Bangalore", skills=["React", "Node.js"]))
    db.commit()
    return row


@pytest.fixture
def api(client, user):
    """TestClient authenticated as ``user`` (independent of the auth module)."""
    token = create_access_token(user.id, user.role.value)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_application(
    db,
    user: User,
    *,
    company_name: str = "Acme Cloud",
    domain: str | None = None,
    email_domains: list[str] | None = None,
    title: str = "Senior Backend Engineer",
    status: ApplicationStatus = ApplicationStatus.APPLIED,
    applied_at: datetime | None = None,
    external_application_id: str | None = None,
    company: Company | None = None,
) -> Application:
    if company is None:
        company = Company(
            name=company_name,
            normalized_name=normalize_company_name(company_name),
            domain=domain,
            email_domains=list(email_domains or []),
        )
        db.add(company)
        db.flush()
    job = Job(
        company_id=company.id,
        title=title,
        normalized_title=title.lower(),
        description="Build and ship product features.",
        location="Bangalore",
        dedupe_hash=uuid.uuid4().hex,
        application_type=ApplicationType.ATS_FORM,
        apply_url="https://example.test/apply",
    )
    db.add(job)
    db.flush()
    application = Application(
        user_id=user.id,
        job_id=job.id,
        status=status,
        source=JobSourceType.DEMO_ATS,
        applied_at=applied_at or utcnow(),
        last_update_at=applied_at or utcnow(),
        external_application_id=external_application_id,
    )
    db.add(application)
    db.flush()
    db.commit()
    return application


def incoming(
    *,
    subject: str,
    sender: str,
    body: str = "",
    provider_message_id: str | None = None,
    received_at: datetime | None = None,
) -> IncomingEmail:
    return IncomingEmail(
        provider_message_id=provider_message_id or f"msg-{uuid.uuid4()}",
        sender=sender,
        recipient="candidate@example.com",
        subject=subject,
        body_text=body,
        received_at=received_at or utcnow(),
    )


# --------------------------------------------------------------------------- classifier

CLASSIFIER_CASES = [
    (
        EmailClassification.APPLICATION_RECEIVED,
        "Thank you for applying to Acme Cloud",
        "Acme Cloud Careers <no-reply@acmecloud.com>",
        "We have received your application for the Senior Backend Engineer role. Application ID: DEMO-AB12CD",
    ),
    (
        EmailClassification.RECRUITER_MESSAGE,
        "Exciting opportunity at Northwind Labs",
        "Priya Nair <priya@northwind.io>",
        "I came across your profile and wanted to reach out about a backend role on my team.",
    ),
    (
        EmailClassification.INTERVIEW,
        "Interview invitation - Senior Backend Engineer at Northwind Labs",
        "Northwind Recruiting <recruiting@northwind.io>",
        "We would like to schedule a call with you on Tuesday. Please share your availability.",
    ),
    (
        EmailClassification.ASSESSMENT,
        "Coding challenge for the Senior Backend Engineer role",
        "no-reply@us.greenhouse-mail.io",
        "Please complete the HackerRank online assessment within 5 days. The test link expires after that.",
    ),
    (
        EmailClassification.REJECTION,
        "Update on your application to Acme Cloud",
        "Acme Cloud Careers <no-reply@acmecloud.com>",
        "Unfortunately, we have decided to move forward with other candidates at this time.",
    ),
    (
        EmailClassification.OFFER,
        "Offer letter - Senior Backend Engineer at Northwind Labs",
        "Northwind People <people@northwind.io>",
        "We are pleased to offer you the position. Your compensation package is attached.",
    ),
    (
        EmailClassification.OTHER,
        "Your order has shipped",
        "ship-confirm@amazon.in",
        "Your package will arrive tomorrow between 9am and 6pm.",
    ),
]


@pytest.mark.parametrize("expected,subject,sender,body", CLASSIFIER_CASES)
def test_classifier_covers_every_class(expected, subject, sender, body):
    outcome = classifier.classify(subject, sender, body)
    assert outcome.classification is expected
    assert 0.0 < outcome.confidence <= 1.0
    assert outcome.reason
    assert outcome.classified_by in {classifier.CLASSIFIED_BY_RULES, classifier.CLASSIFIED_BY_AI}


@pytest.mark.parametrize("expected,subject,sender,body", [c for c in CLASSIFIER_CASES if c[0] is not EmailClassification.OTHER])
def test_rules_alone_are_confident_for_clear_mail(expected, subject, sender, body):
    outcome = classifier.classify_with_rules(subject, sender, body)
    assert outcome.classification is expected
    assert outcome.is_confident, f"{expected} should not need the LLM ({outcome.confidence})"
    assert outcome.classified_by == classifier.CLASSIFIED_BY_RULES


def test_rejection_beats_confirmation_wording():
    outcome = classifier.classify_with_rules(
        "Your application to Acme Cloud",
        "no-reply@acmecloud.com",
        "Thank you for applying. Unfortunately we have decided not to move forward with your application.",
    )
    assert outcome.classification is EmailClassification.REJECTION


def test_noreply_confirmation_sender_heuristic():
    outcome = classifier.classify_with_rules(
        "Your Acme Cloud application",
        "no-reply@acmecloud.com",
        "Thank you for applying to the Senior Backend Engineer role.",
    )
    assert outcome.classification is EmailClassification.APPLICATION_RECEIVED
    assert "automated sender" in outcome.reason


def test_unsure_rules_defer_to_the_model(monkeypatch):
    """Below the threshold the AI answer wins — but only when it is more confident."""
    calls: list[tuple[str, str, str]] = []

    class _Result:
        classification = EmailClassification.RECRUITER_MESSAGE
        confidence = 0.9
        reason = "model reason"

    def _fake_classify(subject, sender, body):  # noqa: ANN001
        calls.append((subject, sender, body))
        return _Result()

    import app.modules.ai.tasks as ai_tasks

    monkeypatch.setattr(ai_tasks, "classify_email", _fake_classify)
    outcome = classifier.classify("Hello there", "someone@example.com", "Just checking in.")
    assert calls, "the classifier should have asked the model"
    assert outcome.classification is EmailClassification.RECRUITER_MESSAGE
    assert outcome.classified_by == classifier.CLASSIFIED_BY_AI
    assert outcome.confidence == 0.9


def test_ai_failure_keeps_the_rule_result(monkeypatch):
    import app.modules.ai.tasks as ai_tasks

    def _boom(*_args, **_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ai_tasks, "classify_email", _boom)
    outcome = classifier.classify("Hello there", "someone@example.com", "Just checking in.")
    assert outcome.classification is EmailClassification.OTHER
    assert outcome.classified_by == classifier.CLASSIFIED_BY_RULES


def test_sender_helpers():
    assert classifier.extract_domain('"Acme Cloud" <No-Reply@Mail.AcmeCloud.com>') == "mail.acmecloud.com"
    assert classifier.extract_display_name('"Acme Cloud" <no-reply@acmecloud.com>') == "Acme Cloud"
    assert classifier.extract_address("recruiter@northwind.io") == "recruiter@northwind.io"
    assert classifier.is_job_board_domain("us.greenhouse-mail.io")
    assert not classifier.is_job_board_domain("acmecloud.com")
    assert classifier.is_noreply_sender("no-reply@acmecloud.com")


# --------------------------------------------------------------------------- linker


def test_link_by_company_domain(db, user):
    application = make_application(db, user, company_name="Acme Cloud", domain="acmecloud.com")
    msg = incoming(subject="Your application", sender="Careers <jobs@mail.acmecloud.com>", body="Thanks!")
    matched, matched_by = linker.link(db, user.id, msg)
    assert matched is not None and matched.id == application.id
    assert matched_by == linker.MATCH_DOMAIN


def test_link_by_company_email_domain_list(db, user):
    application = make_application(db, user, company_name="Globex", email_domains=["globex-mail.io"])
    msg = incoming(subject="Update", sender="no-reply@globex-mail.io", body="Hello")
    matched, matched_by = linker.link(db, user.id, msg)
    assert matched is not None and matched.id == application.id
    assert matched_by == linker.MATCH_DOMAIN


def test_link_by_company_name_and_learn_the_domain(db, user):
    application = make_application(db, user, company_name="Northwind Labs")
    msg = incoming(
        subject="Interview invitation at Northwind Labs",
        sender="Northwind Recruiting <recruiting@northwind-careers.io>",
        body="We would like to schedule a call.",
    )
    matched, matched_by = linker.link(db, user.id, msg)
    assert matched is not None and matched.id == application.id
    assert matched_by == linker.MATCH_COMPANY_NAME

    db.commit()
    company = db.get(Company, matched.job.company_id)
    assert "northwind-careers.io" in (company.email_domains or []), "a non-generic sender domain should be learned"


def test_generic_sender_domain_is_never_learned(db, user):
    make_application(db, user, company_name="Initech")
    msg = incoming(subject="Initech role", sender="Recruiter <recruiter@gmail.com>", body="Hi there")
    matched, matched_by = linker.link(db, user.id, msg)
    assert matched_by == linker.MATCH_COMPANY_NAME
    company = db.get(Company, matched.job.company_id)
    assert company.email_domains == []
    assert linker.is_generic_domain("gmail.com")
    assert linker.is_generic_domain("us.greenhouse-mail.io")
    assert not linker.is_generic_domain("acmecloud.com")


def test_link_by_job_title_in_subject(db, user):
    application = make_application(db, user, company_name="Umbrella Systems", title="Platform Reliability Engineer")
    msg = incoming(
        subject="Platform Reliability Engineer - next steps",
        sender="talent@unrelated-mailer.test",
        body="A quick note about your candidacy.",
    )
    matched, matched_by = linker.link(db, user.id, msg)
    assert matched is not None and matched.id == application.id
    assert matched_by == linker.MATCH_JOB_TITLE


def test_link_by_application_id_token(db, user):
    application = make_application(db, user, company_name="Hooli", external_application_id="DEMO-AB12CD")
    msg = incoming(
        subject="Your submission",
        sender="no-reply@ats-mailer.test",
        body="We are processing it.\n\nApplication ID: DEMO-AB12CD\n",
    )
    matched, matched_by = linker.link(db, user.id, msg)
    assert matched is not None and matched.id == application.id
    assert matched_by == linker.MATCH_APPLICATION_ID


def test_most_recently_applied_application_wins(db, user):
    company = Company(name="Acme Cloud", normalized_name=normalize_company_name("Acme Cloud"))
    db.add(company)
    db.flush()
    older = make_application(
        db, user, company=company, title="Backend Engineer", applied_at=utcnow() - timedelta(days=20)
    )
    newer = make_application(
        db, user, company=company, title="Staff Engineer", applied_at=utcnow() - timedelta(days=1)
    )
    msg = incoming(subject="Acme Cloud - update", sender="talent@unrelated-mailer.test", body="Hello")
    matched, matched_by = linker.link(db, user.id, msg)
    assert matched_by == linker.MATCH_COMPANY_NAME
    assert matched.id == newer.id and matched.id != older.id


def test_only_submitted_applications_are_candidates(db, user):
    make_application(db, user, company_name="Vandelay Industries", status=ApplicationStatus.QUEUED)
    msg = incoming(subject="Vandelay Industries update", sender="hr@vandelay.test", body="Hello")
    matched, matched_by = linker.link(db, user.id, msg)
    assert matched is None and matched_by is None


def test_link_never_crosses_users(db, user):
    other = User(email="someone-else@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Other")
    db.add(other)
    db.flush()
    make_application(db, other, company_name="Stark Industries", domain="stark.test")
    msg = incoming(subject="Stark Industries update", sender="hr@stark.test", body="Hello")
    matched, _ = linker.link(db, user.id, msg)
    assert matched is None


# --------------------------------------------------------------------------- status progression


@pytest.mark.parametrize(
    "current,classification,expected",
    [
        (ApplicationStatus.APPLIED, EmailClassification.APPLICATION_RECEIVED, ApplicationStatus.APPLICATION_RECEIVED),
        (ApplicationStatus.INTERVIEW, EmailClassification.APPLICATION_RECEIVED, None),
        (ApplicationStatus.INTERVIEW, EmailClassification.REJECTION, ApplicationStatus.REJECTED),
        (ApplicationStatus.APPLIED, EmailClassification.OTHER, None),
        (ApplicationStatus.REJECTED, EmailClassification.INTERVIEW, None),
        (ApplicationStatus.WITHDRAWN, EmailClassification.OFFER, None),
        (ApplicationStatus.NO_RESPONSE, EmailClassification.RECRUITER_MESSAGE, ApplicationStatus.RECRUITER_CONTACTED),
        (ApplicationStatus.ASSESSMENT, EmailClassification.INTERVIEW, ApplicationStatus.INTERVIEW),
        (ApplicationStatus.INTERVIEW, EmailClassification.ASSESSMENT, None),
    ],
)
def test_next_status_for(current, classification, expected):
    assert service.next_status_for(current, classification) is expected


# --------------------------------------------------------------------------- ingestion


def test_ingest_moves_applied_to_application_received(db, user):
    application = make_application(db, user, company_name="Acme Cloud", domain="acmecloud.com")
    msg = incoming(
        subject="Thank you for applying to Acme Cloud",
        sender="Acme Cloud Careers <no-reply@acmecloud.com>",
        body="We have received your application for the Senior Backend Engineer role.",
    )
    email = service.ingest_message(db, user.id, msg)
    db.commit()

    assert email.classification is EmailClassification.APPLICATION_RECEIVED
    assert email.matched_by == linker.MATCH_DOMAIN
    assert email.application_id == application.id
    assert email.status_applied is True
    assert email.sender_domain == "acmecloud.com"

    db.refresh(application)
    assert application.status is ApplicationStatus.APPLICATION_RECEIVED
    assert application.last_response_at is not None

    events = list(db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == application.id)))
    assert any(e.event_type is ApplicationEventType.EMAIL_LINKED for e in events)
    assert any(e.event_type is ApplicationEventType.STATUS_CHANGED and e.actor is Actor.EMAIL for e in events)

    notifications = list(db.scalars(select(Notification).where(Notification.user_id == user.id)))
    assert [n for n in notifications if n.title == "Application received by Acme Cloud"]

    actions = {row.action for row in db.scalars(select(AuditLog).where(AuditLog.user_id == user.id))}
    assert {"email.classified", "email.linked"} <= actions


def test_rejection_from_interview(db, user):
    application = make_application(
        db, user, company_name="Globex", domain="globex.test", status=ApplicationStatus.INTERVIEW
    )
    msg = incoming(
        subject="Update on your application to Globex",
        sender="Globex Careers <no-reply@globex.test>",
        body="Unfortunately, we have decided to move forward with other candidates.",
    )
    email = service.ingest_message(db, user.id, msg)
    db.commit()

    assert email.classification is EmailClassification.REJECTION
    db.refresh(application)
    assert application.status is ApplicationStatus.REJECTED
    types = {n.type for n in db.scalars(select(Notification).where(Notification.user_id == user.id))}
    assert NotificationType.REJECTION in types


def test_interview_email_creates_one_interview(db, user):
    application = make_application(db, user, company_name="Initech", domain="initech.test")
    msg = incoming(
        subject="Interview invitation - technical round at Initech",
        sender="Initech Recruiting <recruiting@initech.test>",
        body="We would like to schedule a call. Join at https://meet.google.com/abc-defg-hij",
    )
    service.ingest_message(db, user.id, msg)
    db.commit()
    db.refresh(application)
    assert application.status is ApplicationStatus.INTERVIEW

    interviews = list(db.scalars(select(Interview).where(Interview.application_id == application.id)))
    assert len(interviews) == 1
    assert interviews[0].status is InterviewStatus.SCHEDULED
    assert interviews[0].source_email_id is not None
    assert interviews[0].location_or_link == "https://meet.google.com/abc-defg-hij"

    # a second invitation must not pile up another scheduled interview
    service.ingest_message(
        db,
        user.id,
        incoming(
            subject="Interview reschedule at Initech",
            sender="Initech Recruiting <recruiting@initech.test>",
            body="Can we move the interview to Thursday?",
        ),
    )
    db.commit()
    assert db.scalar(select(Interview).where(Interview.application_id == application.id).exists().select()) is True
    assert len(list(db.scalars(select(Interview).where(Interview.application_id == application.id)))) == 1


def test_other_classification_leaves_the_status_alone(db, user):
    application = make_application(db, user, company_name="Umbrella Systems", domain="umbrella.test")
    msg = incoming(
        subject="Your order has shipped",
        sender="ship-confirm@amazon.in",
        body="Your package will arrive tomorrow.",
    )
    email = service.ingest_message(db, user.id, msg, application_id=application.id)
    db.commit()

    assert email.classification is EmailClassification.OTHER
    assert email.application_id == application.id  # explicitly linked
    assert email.status_applied is False
    db.refresh(application)
    assert application.status is ApplicationStatus.APPLIED
    assert list(db.scalars(select(Notification).where(Notification.user_id == user.id))) == []


def test_duplicate_provider_message_id_is_ignored(db, user):
    make_application(db, user, company_name="Acme Cloud", domain="acmecloud.com")
    msg = incoming(
        subject="Thank you for applying to Acme Cloud",
        sender="no-reply@acmecloud.com",
        body="We have received your application.",
        provider_message_id="gmail-123",
    )
    first = service.ingest_message(db, user.id, msg)
    second = service.ingest_message(db, user.id, msg)
    db.commit()
    assert first.id == second.id
    assert db.scalar(select(EmailMessage).where(EmailMessage.user_id == user.id).exists().select()) is True
    assert len(list(db.scalars(select(EmailMessage).where(EmailMessage.user_id == user.id)))) == 1


def test_unlinked_email_does_not_notify(db, user):
    make_application(db, user, company_name="Acme Cloud", domain="acmecloud.com")
    msg = incoming(
        subject="Interview invitation at Some Other Company",
        sender="recruiting@unrelated-mailer.test",
        body="We would like to schedule a call.",
    )
    email = service.ingest_message(db, user.id, msg)
    db.commit()
    assert email.application_id is None
    assert email.classification is EmailClassification.INTERVIEW
    assert list(db.scalars(select(Notification).where(Notification.user_id == user.id))) == []


def test_transition_is_delegated_to_the_applications_module(db, user, monkeypatch):
    """When ``applications.service`` exists, the email pipeline must use its API."""
    application = make_application(db, user, company_name="Acme Cloud", domain="acmecloud.com")
    calls: dict[str, dict] = {}

    def _transition(session, app, new_status, *, actor, message, meta=None):  # noqa: ANN001
        calls["transition"] = {"status": new_status, "actor": actor, "message": message, "meta": meta}
        app.status = new_status
        app.last_update_at = utcnow()

    def _record_event(session, app, event_type, message, *, actor=Actor.SYSTEM, meta=None):  # noqa: ANN001
        calls["record_event"] = {"event_type": event_type, "message": message, "actor": actor, "meta": meta}

    class _Stub:
        transition = staticmethod(_transition)
        record_event = staticmethod(_record_event)

    monkeypatch.setattr(service, "_applications_service", lambda: _Stub)
    service.ingest_message(
        db,
        user.id,
        incoming(
            subject="Thank you for applying to Acme Cloud",
            sender="no-reply@acmecloud.com",
            body="We have received your application.",
        ),
    )
    db.commit()

    assert calls["transition"]["status"] is ApplicationStatus.APPLICATION_RECEIVED
    assert calls["transition"]["actor"] is Actor.EMAIL
    assert calls["transition"]["message"].startswith("Email: ")
    assert calls["record_event"]["event_type"] is ApplicationEventType.EMAIL_LINKED
    db.refresh(application)
    assert application.status is ApplicationStatus.APPLICATION_RECEIVED


def test_ingest_simulated_email_builds_realistic_content(db, user):
    application = make_application(db, user, company_name="Northwind Labs", domain="northwind.test")
    email = service.ingest_simulated_email(db, user.id, application_id=application.id, kind=EmailClassification.OFFER)
    db.commit()

    assert email.is_simulated is True
    assert email.provider_message_id.startswith("sim-")
    assert "Northwind Labs" in email.subject
    assert email.classification is EmailClassification.OFFER
    db.refresh(application)
    assert application.status is ApplicationStatus.OFFER


def test_demo_ats_style_simulated_email(db, user):
    """The signature the demo ATS calls with (keyword subject/body/sender)."""
    application = make_application(db, user, company_name="Acme Cloud", domain="acmecloud.com")
    email = service.ingest_simulated_email(
        db,
        user.id,
        subject="Thank you for applying to Acme Cloud - Senior Backend Engineer",
        body="Your application has been received.\n\nApplication ID: DEMO-XY9987\n",
        sender="no-reply@acmecloud.com",
    )
    db.commit()
    assert email.application_id == application.id
    assert email.classification is EmailClassification.APPLICATION_RECEIVED


# --------------------------------------------------------------------------- API


def test_list_filters_and_truncates_the_body(db, user, api):
    application = make_application(db, user, company_name="Acme Cloud", domain="acmecloud.com")
    long_body = "We have received your application. " + ("x" * 3000)
    service.ingest_message(
        db,
        user.id,
        incoming(subject="Thank you for applying to Acme Cloud", sender="no-reply@acmecloud.com", body=long_body),
    )
    service.ingest_message(
        db,
        user.id,
        incoming(subject="Your order has shipped", sender="ship-confirm@amazon.in", body="Tomorrow."),
    )
    db.commit()

    response = api.get(API)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 2
    received = [item for item in payload["items"] if item["classification"] == "APPLICATION_RECEIVED"][0]
    assert len(received["body_text"]) == 2000

    assert api.get(API, params={"classification": "OTHER"}).json()["total"] == 1
    assert api.get(API, params={"unlinked": "true"}).json()["total"] == 1
    assert api.get(API, params={"application_id": str(application.id)}).json()["total"] == 1
    assert api.get(API, params={"q": "shipped"}).json()["total"] == 1

    full = api.get(f"{API}/{received['id']}").json()
    assert len(full["body_text"]) > 2000


def test_simulate_endpoint_runs_the_pipeline(db, user, api):
    application = make_application(db, user, company_name="Northwind Labs", domain="northwind.test")
    response = api.post(API + "/simulate", json={"application_id": str(application.id), "kind": "INTERVIEW"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["classification"] == "INTERVIEW"
    assert body["is_simulated"] is True
    assert body["application_id"] == str(application.id)
    assert "Northwind Labs" in body["subject"]

    db.expire_all()
    refreshed = db.get(Application, application.id)
    assert refreshed.status is ApplicationStatus.INTERVIEW


def test_simulate_with_a_foreign_application_is_404(db, user, api):
    other = User(email="intruder@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Intruder")
    db.add(other)
    db.flush()
    foreign = make_application(db, other, company_name="Stark Industries")
    response = api.post(API + "/simulate", json={"application_id": str(foreign.id), "kind": "OFFER"})
    assert response.status_code == 404, response.text


def test_manual_link_and_classify_apply_the_status(db, user, api):
    application = make_application(db, user, company_name="Umbrella Systems", domain="umbrella.test")
    email = service.ingest_message(
        db,
        user.id,
        incoming(subject="A note about your candidacy", sender="someone@unrelated-mailer.test", body="Hello there."),
    )
    db.commit()
    assert email.application_id is None

    linked = api.post(f"{API}/{email.id}/link", json={"application_id": str(application.id)})
    assert linked.status_code == 200, linked.text
    assert linked.json()["matched_by"] == linker.MATCH_MANUAL

    classified = api.post(f"{API}/{email.id}/classify", json={"classification": "ASSESSMENT"})
    assert classified.status_code == 200, classified.text
    assert classified.json()["classified_by"] == classifier.CLASSIFIED_BY_USER
    assert classified.json()["status_applied"] is True

    db.expire_all()
    assert db.get(Application, application.id).status is ApplicationStatus.ASSESSMENT


def test_mark_read_and_ownership(db, user, api):
    make_application(db, user, company_name="Acme Cloud", domain="acmecloud.com")
    email = service.ingest_message(
        db, user.id, incoming(subject="Thank you for applying to Acme Cloud", sender="no-reply@acmecloud.com")
    )
    db.commit()

    assert api.post(f"{API}/{email.id}/read").json()["is_read"] is True
    assert api.get(f"{API}/{uuid.uuid4()}").status_code == 404


def test_emails_require_authentication(client):
    assert client.get(API).status_code == 401


# --------------------------------------------------------------------------- gmail client


class _FakeExecutable:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def execute(self) -> dict:
        return self._payload


class _FakeMessages:
    def __init__(self, listing: dict, message: dict) -> None:
        self._listing = listing
        self._message = message
        self.last_query: str | None = None

    def list(self, *, userId: str, q: str, maxResults: int) -> _FakeExecutable:  # noqa: N803 - google api casing
        self.last_query = q
        assert userId == "me" and maxResults > 0
        return _FakeExecutable(self._listing)

    def get(self, *, userId: str, id: str, format: str) -> _FakeExecutable:  # noqa: A002, N803
        assert userId == "me" and format == "full" and id
        return _FakeExecutable(self._message)


class _FakeUsers:
    def __init__(self, messages: _FakeMessages) -> None:
        self._messages = messages

    def messages(self) -> _FakeMessages:
        return self._messages

    def getProfile(self, *, userId: str) -> _FakeExecutable:  # noqa: N802 - google api casing
        assert userId == "me"
        return _FakeExecutable({"emailAddress": "candidate@gmail.com"})


class _FakeGmailService:
    def __init__(self, listing: dict, message: dict) -> None:
        self.messages_resource = _FakeMessages(listing, message)

    def users(self) -> _FakeUsers:
        return _FakeUsers(self.messages_resource)


def _b64(text: str) -> str:
    import base64

    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def test_gmail_client_decodes_a_plain_text_message():
    raw = {
        "id": "gmail-1",
        "threadId": "thread-1",
        "internalDate": str(int(datetime(2026, 5, 1, 9, 30, tzinfo=timezone.utc).timestamp() * 1000)),
        "snippet": "We have received your application",
        "payload": {
            "headers": [
                {"name": "From", "value": "Acme Cloud <no-reply@acmecloud.com>"},
                {"name": "To", "value": "candidate@gmail.com"},
                {"name": "Subject", "value": "Thank you for applying to Acme Cloud"},
                {"name": "Date", "value": "Fri, 1 May 2026 09:30:00 +0000"},
            ],
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("We have received your application.\nApplication ID: DEMO-AB12CD")}},
                {"mimeType": "text/html", "body": {"data": _b64("<p>ignored</p>")}},
            ],
        },
    }
    fake = _FakeGmailService({"messages": [{"id": "gmail-1"}]}, raw)
    gmail = GmailClient({"token": "x"}, service=fake)

    ids = gmail.list_job_related_messages(max_results=10, newer_than_days=14)
    assert ids == ["gmail-1"]
    assert "newer_than:14d" in fake.messages_resource.last_query

    message = gmail.get_message("gmail-1")
    assert message.provider_message_id == "gmail-1"
    assert message.thread_id == "thread-1"
    assert message.sender == "Acme Cloud <no-reply@acmecloud.com>"
    assert message.subject == "Thank you for applying to Acme Cloud"
    assert "DEMO-AB12CD" in (message.body_text or "")
    assert message.received_at.year == 2026
    assert message.is_simulated is False
    assert gmail.get_profile_email() == "candidate@gmail.com"


def test_gmail_client_falls_back_to_stripped_html():
    raw = {
        "id": "gmail-2",
        "payload": {
            "headers": [{"name": "From", "value": "hr@globex.test"}, {"name": "Subject", "value": "Interview"}],
            "mimeType": "text/html",
            "body": {"data": _b64("<html><style>p{color:red}</style><p>Hello&nbsp;there</p><br><p>Bye</p></html>")},
        },
    }
    gmail = GmailClient({}, service=_FakeGmailService({"messages": []}, raw))
    message = gmail.get_message("gmail-2")
    assert "Hello there" in (message.body_text or "")
    assert "<p>" not in (message.body_text or "")
    assert "color:red" not in (message.body_text or "")


def test_gmail_query_and_html_helpers():
    query = build_query()
    assert "newer_than:30d" in query
    for term in ("application", "interview", "offer", "assessment", "recruiter", "position", "role"):
        assert term in query
    for term in ("greenhouse", "lever", "workday", "naukri", "linkedin", "indeed"):
        assert term in query
    assert strip_html("<div>a</div><div>b</div>").splitlines() == ["a", "b"]
    assert parse_message({}, message_id="fallback-id").provider_message_id == "fallback-id"
    with pytest.raises(ValueError):
        parse_message({})


# --------------------------------------------------------------------------- real applications module


def test_pipeline_against_the_real_applications_service(db, user, monkeypatch):
    """End-to-end with the shipped ``applications.service`` (skipped while it is missing).

    The two modules must cooperate: one status change, one timeline entry per fact, one
    notification per event (``transition`` already notifies for INTERVIEW) and an
    interview row attributed to the email that triggered it.
    """
    applications_service = pytest.importorskip(
        "app.modules.applications.service",
        reason="applications module not implemented yet (owned by the applications agent)",
    )
    monkeypatch.setattr(service, "_applications_service", lambda: applications_service)

    application = make_application(db, user, company_name="Initech", domain="initech.test")
    email = service.ingest_message(
        db,
        user.id,
        incoming(
            subject="Interview invitation - technical round at Initech",
            sender="Initech Recruiting <recruiting@initech.test>",
            body="We would like to schedule a call. Join at https://meet.google.com/abc-defg-hij",
        ),
    )
    db.commit()
    db.refresh(application)

    assert application.status is ApplicationStatus.INTERVIEW
    assert email.status_applied is True

    events = list(db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == application.id)))
    assert any(e.event_type is ApplicationEventType.EMAIL_LINKED for e in events)
    assert [e for e in events if e.event_type is ApplicationEventType.STATUS_CHANGED and e.to_status is ApplicationStatus.INTERVIEW]

    interviews = list(db.scalars(select(Interview).where(Interview.application_id == application.id)))
    assert len(interviews) == 1, "the email must not add a second round on top of the placeholder"
    assert interviews[0].source_email_id == email.id
    assert interviews[0].location_or_link == "https://meet.google.com/abc-defg-hij"

    scheduled = [
        n for n in db.scalars(select(Notification).where(Notification.user_id == user.id))
        if n.type is NotificationType.INTERVIEW_SCHEDULED
    ]
    assert len(scheduled) == 1, "the status change and the email must not both notify"


# --------------------------------------------------------------- reference beats recency


def test_a_quoted_reference_wins_over_the_most_recent_application_at_the_same_company(db, user) -> None:
    """An acknowledgement naming an application must not land on a sibling application.

    Applying twice to one company is ordinary. Both applications share the employer's
    sending domain, so a domain match alone picks whichever was applied to most recently.
    The reference the mail quotes names one of them outright and has to win.
    """
    company = Company(
        name="Acme Cloud",
        normalized_name=normalize_company_name("Acme Cloud"),
        domain="acmecloud.io",
    )
    db.add(company)
    db.flush()

    older = make_application(
        db,
        user,
        company=company,
        title="Platform Engineer",
        applied_at=utcnow() - timedelta(days=2),
        external_application_id="DEMO-AAAAAA",
    )
    newer = make_application(
        db,
        user,
        company=company,
        title="Backend Engineer",
        applied_at=utcnow(),
        external_application_id="DEMO-BBBBBB",
    )

    message = incoming(
        subject="Thank you for applying to Acme Cloud — Platform Engineer",
        sender="Acme Cloud Recruiting <no-reply@acmecloud.io>",
        body="Your application has been received.\n\nApplication ID: DEMO-AAAAAA\nRole: Platform Engineer\n",
    )

    result = linker.link(db, user.id, message)

    assert result.application is not None
    assert result.application.id == older.id, "the quoted reference must outrank the newer sibling"
    assert result.matched_by == linker.MATCH_APPLICATION_ID
    assert result.application.id != newer.id


def test_the_domain_still_links_an_acknowledgement_that_quotes_no_reference(db, user) -> None:
    """Without a reference the domain heuristic is still the right fallback."""
    application = make_application(db, user, company_name="Northwind Labs", domain="northwindlabs.dev")

    result = linker.link(
        db,
        user.id,
        incoming(
            subject="We received your application",
            sender="careers@northwindlabs.dev",
            body="Our team is reviewing it now.",
        ),
    )

    assert result.application is not None
    assert result.application.id == application.id
    assert result.matched_by == linker.MATCH_DOMAIN
