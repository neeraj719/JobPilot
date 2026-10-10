"""Standing answers (Step 1b, Gap B): answers the user gives once and the engine reuses.

Covers the lookup order, the wording rule for consent/legal declarations, the
demographic exclusion, ``applies_to`` and expiry, the capture from
``PUT /applications/{id}/answers`` and the three ``/profiles/standing-answers`` endpoints.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationFailed
from app.models.application import Application, ApplicationAnswer
from app.models.company import Company
from app.models.enums import (
    AnswerSource,
    AnswerStatus,
    ApplicationStatus,
    ApplicationType,
    CompanyPriority,
    FieldType,
    JobSourceType,
    WorkMode,
)
from app.models.job import Job
from app.models.profile import StandingAnswer
from app.models.user import User
from app.modules.applications.answers import (
    STANDING_ANSWER_RATIONALE,
    answer_question,
    generate_answers,
    save_user_answers,
)
from app.modules.applications.questions import NOTICE_PERIOD_OPTIONS, FormQuestion
from app.modules.profiles import service as profiles

CONSENT_AT = "I consent to {name} storing the information in this application and contacting me about this role. *"
API = "/api/v1/profiles/standing-answers"


def standing(key: str, text: str, answer: str, **extra) -> StandingAnswer:
    """An unsaved row: the matching rules need no database."""
    values = {"applies_to": "ALL", "is_active": True, "expires_at": None, "field_type": FieldType.TEXT}
    values.update(extra)
    return StandingAnswer(user_id=uuid.uuid4(), question_key=key, question_text=text, answer=answer, **values)


def job_at(company: str) -> SimpleNamespace:
    return SimpleNamespace(company=SimpleNamespace(name=company), location="Bangalore, India", title="Engineer")


CANDIDATE = SimpleNamespace(flat={"first_name": "Aarav", "notice_period_days": 30}, resume_path=None)


# --------------------------------------------------------------------------- lookup order


def test_a_standing_answer_beats_the_profile_fact() -> None:
    question = FormQuestion(
        key="notice_period_days", text="Notice Period", field_type=FieldType.SELECT, options=list(NOTICE_PERIOD_OPTIONS)
    )
    from_profile = answer_question(question, CANDIDATE, job_at("Acme"))
    assert from_profile["answer"] == "30 days" and from_profile["answer_source"] == AnswerSource.PREFERENCE

    saved = [standing("notice_period_days", "Notice period", "60 days")]
    resolved = answer_question(question, CANDIDATE, job_at("Acme"), standing=saved, source=JobSourceType.DEMO_ATS)
    assert resolved["answer"] == "60 days"
    assert resolved["answer_source"] == AnswerSource.USER
    assert resolved["rationale"] == STANDING_ANSWER_RATIONALE
    assert resolved["status"] == AnswerStatus.ANSWERED


def test_a_standing_answer_that_is_not_one_of_the_choices_falls_through() -> None:
    question = FormQuestion(
        key="notice_period_days", text="Notice Period", field_type=FieldType.SELECT, options=["Immediate", "30 days"]
    )
    saved = [standing("notice_period_days", "Notice period", "120 days")]
    resolved = answer_question(question, CANDIDATE, job_at("Acme"), standing=saved)
    assert resolved["answer"] == "30 days" and resolved["answer_source"] == AnswerSource.PREFERENCE


def test_a_standing_answer_answers_what_the_profile_cannot() -> None:
    question = FormQuestion(key="custom:start_date", text="What is your preferred start date?")
    saved = [standing("custom:start_date", "What is your preferred start date?", "1 December 2026")]
    resolved = answer_question(question, CANDIDATE, job_at("Acme"), standing=saved)
    assert resolved["answer"] == "1 December 2026" and resolved["answer_source"] == AnswerSource.USER


# --------------------------------------------------------------------------- consent wording


def test_consent_is_reused_when_the_wording_matches_at_another_company() -> None:
    saved = [
        standing(
            "custom:consent",
            profiles.template_question_text(CONSENT_AT.format(name="Northwind Labs"), "Northwind Labs"),
            "Yes",
            field_type=FieldType.CHECKBOX,
        )
    ]
    question = FormQuestion(
        key="custom:consent", text=CONSENT_AT.format(name="Bluefin Analytics"), field_type=FieldType.CHECKBOX
    )
    resolved = answer_question(question, CANDIDATE, job_at("Bluefin Analytics"), standing=saved)
    assert resolved["answer"] == "Yes" and resolved["rationale"] == STANDING_ANSWER_RATIONALE


def test_consent_with_different_wording_still_needs_the_user() -> None:
    saved = [standing("custom:consent", CONSENT_AT.format(name="{company}"), "Yes", field_type=FieldType.CHECKBOX)]
    question = FormQuestion(
        key="custom:consent",
        text="I consent to Acme sharing my information with partners and contacting me about other roles. *",
        field_type=FieldType.CHECKBOX,
    )
    resolved = answer_question(question, CANDIDATE, job_at("Acme"), standing=saved)
    assert resolved["rationale"] != STANDING_ANSWER_RATIONALE
    assert resolved["status"] == AnswerStatus.NEEDS_USER_INPUT


def test_wording_similarity_threshold() -> None:
    stored = profiles.template_question_text(CONSENT_AT.format(name="Northwind Labs"), "Northwind Labs")
    assert stored.startswith("I consent to {company} storing") and not stored.endswith("*")
    assert profiles.wording_similarity(stored, CONSENT_AT.format(name="Acme Cloud"), "Acme Cloud") == 1.0
    assert profiles.wording_similarity(stored, "I agree to the privacy policy", "Acme Cloud") < profiles.WORDING_MATCH_THRESHOLD


def test_work_authorization_is_a_declaration_too() -> None:
    saved = [standing("work_authorization", "Are you legally authorized to work in India?", "Yes")]
    india = FormQuestion(key="work_authorization", text="Are you legally authorized to work in India?", is_sensitive=True)
    usa = FormQuestion(key="work_authorization", text="Are you legally authorized to work in the United States?", is_sensitive=True)
    assert answer_question(india, SimpleNamespace(flat={}), job_at("Acme"), standing=saved)["answer"] == "Yes"
    assert answer_question(usa, SimpleNamespace(flat={}), job_at("Acme"), standing=saved)["status"] == AnswerStatus.NEEDS_USER_INPUT


# --------------------------------------------------------------------------- exclusions and scope


def test_demographic_questions_never_use_a_standing_answer() -> None:
    saved = [standing("custom:demographic_gender", "Gender", "Prefer not to say")]
    question = FormQuestion(key="custom:demographic_gender", text="Gender", is_sensitive=True)
    resolved = answer_question(question, SimpleNamespace(flat={}), job_at("Acme"), standing=saved)
    assert resolved["status"] == AnswerStatus.NEEDS_USER_INPUT
    assert resolved["rationale"] != STANDING_ANSWER_RATIONALE


@pytest.mark.parametrize(
    "applies_to, source, used",
    [
        ("ALL", JobSourceType.GREENHOUSE, True),
        ("ALL", None, True),
        (["DEMO_ATS", "LEVER"], JobSourceType.DEMO_ATS, True),
        (["DEMO_ATS", "LEVER"], JobSourceType.GREENHOUSE, False),
        (["DEMO_ATS"], None, False),
    ],
)
def test_applies_to_limits_the_sources(applies_to, source, used: bool) -> None:
    saved = [standing("custom:start_date", "Start date", "Immediately", applies_to=applies_to)]
    question = FormQuestion(key="custom:start_date", text="Start date")
    found = profiles.find_standing_answer(saved, question_key=question.key, question_text=question.text, source=source)
    assert (found is not None) is used


def test_expired_and_switched_off_answers_are_not_used() -> None:
    now = datetime.now(timezone.utc)
    question = dict(question_key="custom:start_date", question_text="Start date", source=JobSourceType.DEMO_ATS)
    expired = standing("custom:start_date", "Start date", "x", expires_at=now - timedelta(minutes=1))
    future = standing("custom:start_date", "Start date", "y", expires_at=now + timedelta(days=30))
    paused = standing("custom:start_date", "Start date", "z", is_active=False)
    assert profiles.find_standing_answer([expired], **question) is None
    assert profiles.find_standing_answer([paused], **question) is None
    assert profiles.find_standing_answer([expired, future], **question) is future


# --------------------------------------------------------------------------- with a database


@pytest.fixture
def owner(db: Session) -> User:
    from app.core.security import hash_password

    row = User(email="standing@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Standing Owner")
    db.add(row)
    db.commit()
    return row


def make_application(db: Session, user_id: uuid.UUID, company_name: str = "Northwind Labs") -> Application:
    company = db.scalars(select(Company).where(Company.name == company_name)).first()
    if company is None:
        company = Company(name=company_name, normalized_name=company_name.lower())
        db.add(company)
        db.flush()
    job = Job(
        company_id=company.id,
        title="Full Stack Engineer",
        normalized_title="full stack engineer",
        description="React.",
        location="Bangalore, India",
        work_mode=WorkMode.HYBRID,
        posted_at=datetime.now(timezone.utc),
        canonical_url=f"https://example.test/{uuid.uuid4().hex[:8]}",
        apply_url=f"https://example.test/apply/{uuid.uuid4().hex[:8]}",
        application_type=ApplicationType.ATS_FORM,
        dedupe_hash=uuid.uuid4().hex,
    )
    db.add(job)
    db.flush()
    application = Application(
        user_id=user_id,
        job_id=job.id,
        status=ApplicationStatus.QUEUED,
        priority=CompanyPriority.P2,
        source=JobSourceType.DEMO_ATS,
        form_snapshot={},
    )
    db.add(application)
    db.commit()
    return application


def question_row(application: Application, key: str, text: str, **extra) -> ApplicationAnswer:
    values = dict(field_type=FieldType.TEXT, required=True, status=AnswerStatus.NEEDS_USER_INPUT)
    values.update(extra)
    return ApplicationAnswer(application_id=application.id, question_key=key, question_text=text, **values)


def test_a_typed_answer_on_the_application_beats_the_standing_answer(db: Session, owner: User) -> None:
    profiles.upsert_standing_answer(
        db, owner.id, question_key="custom:start_date", question_text="Start date", answer="15 February 2027"
    )
    application = make_application(db, owner.id)
    db.add(
        question_row(
            application,
            "custom:start_date",
            "Start date",
            answer="1 January 2027",
            answer_source=AnswerSource.USER,
            status=AnswerStatus.ANSWERED,
            rationale="Provided by you",
        )
    )
    db.commit()
    db.refresh(application)

    rows = generate_answers(
        db, application, SimpleNamespace(flat={}), questions=[FormQuestion(key="custom:start_date", text="Start date")]
    )
    start = next(r for r in rows if r.question_key == "custom:start_date")
    assert start.answer == "1 January 2027" and start.rationale == "Provided by you"


def test_generate_answers_uses_the_standing_answer_for_this_source(db: Session, owner: User) -> None:
    profiles.upsert_standing_answer(
        db, owner.id, question_key="custom:start_date", question_text="Start date", answer="Immediately",
        applies_to=["LEVER"],
    )
    profiles.upsert_standing_answer(
        db, owner.id, question_key="willing_to_relocate", question_text="Willing to relocate?", answer="Yes",
    )
    application = make_application(db, owner.id)  # applies through DEMO_ATS
    db.refresh(application)
    rows = generate_answers(
        db,
        application,
        SimpleNamespace(flat={}),
        questions=[
            FormQuestion(key="custom:start_date", text="Start date"),
            FormQuestion(key="willing_to_relocate", text="Are you willing to relocate?", field_type=FieldType.RADIO, options=["Yes", "No"]),
        ],
    )
    by_key = {r.question_key: r for r in rows}
    assert by_key["willing_to_relocate"].answer == "Yes"
    assert by_key["willing_to_relocate"].answer_source == AnswerSource.USER
    assert by_key["custom:start_date"].rationale != STANDING_ANSWER_RATIONALE  # limited to LEVER


def test_active_standing_answers_skip_expired_ones(db: Session, owner: User) -> None:
    profiles.upsert_standing_answer(
        db, owner.id, question_key="custom:start_date", question_text="Start date", answer="x",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    profiles.upsert_standing_answer(db, owner.id, question_key="custom:why_us", question_text="Why us?", answer="y")
    assert [r.question_key for r in profiles.active_standing_answers(db, owner.id)] == ["custom:why_us"]
    assert len(profiles.list_standing_answers(db, owner.id)) == 2


def test_upsert_refuses_demographics_and_files(db: Session, owner: User) -> None:
    with pytest.raises(ValidationFailed):
        profiles.upsert_standing_answer(db, owner.id, question_key="custom:demographic_gender", question_text="Gender", answer="x")
    with pytest.raises(ValidationFailed):
        profiles.upsert_standing_answer(db, owner.id, question_key="custom:pronouns", question_text="Your pronouns", answer="x")
    with pytest.raises(ValidationFailed):
        profiles.upsert_standing_answer(
            db, owner.id, question_key="resume_file", question_text="Resume", answer="/etc/passwd", field_type=FieldType.FILE
        )


def test_save_as_standing_upserts_one_row(db: Session, owner: User) -> None:
    application = make_application(db, owner.id, "Northwind Labs")
    consent = question_row(
        application, "custom:consent", CONSENT_AT.format(name="Northwind Labs"), field_type=FieldType.CHECKBOX
    )
    start = question_row(application, "custom:start_date", "What is your preferred start date?")
    db.add_all([consent, start])
    db.commit()
    db.refresh(application)

    save_user_answers(
        db,
        application,
        [
            {"id": consent.id, "answer": "Yes", "save_as_standing": True},
            {"id": start.id, "answer": "1 December 2026"},  # not remembered
        ],
    )
    db.commit()
    rows = profiles.list_standing_answers(db, owner.id)
    assert [(r.question_key, r.answer) for r in rows] == [("custom:consent", "Yes")]
    assert rows[0].question_text == CONSENT_AT.format(name="{company}").rstrip(" *")
    assert rows[0].field_type == FieldType.CHECKBOX and rows[0].applies_to == "ALL"

    # Answering it again with a new value updates the same standing answer.
    save_user_answers(db, application, [{"id": consent.id, "answer": "true", "save_as_standing": True}])
    db.commit()
    again = profiles.list_standing_answers(db, owner.id)
    assert len(again) == 1 and again[0].id == rows[0].id and again[0].answer == "true"


def test_save_as_standing_refuses_a_demographic_question(db: Session, owner: User) -> None:
    application = make_application(db, owner.id)
    gender = question_row(application, "custom:demographic_gender", "Gender", is_sensitive=True)
    db.add(gender)
    db.commit()
    db.refresh(application)
    with pytest.raises(ValidationFailed):
        save_user_answers(db, application, [{"id": gender.id, "answer": "Female", "save_as_standing": True}])
    db.rollback()
    assert profiles.list_standing_answers(db, owner.id) == []


# --------------------------------------------------------------------------- the API


def _me(db: Session, email: str = "tester@example.com") -> User:
    return db.scalars(select(User).where(User.email == email)).one()


def test_the_three_endpoints(auth_client: TestClient, db: Session) -> None:
    assert auth_client.get(API).json() == []

    created = auth_client.put(
        API,
        json={
            "question_key": "custom:start_date",
            "question_text": "What is your preferred start date?",
            "answer": "1 December 2026",
            "applies_to": ["DEMO_ATS", "GREENHOUSE"],
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["applies_to"] == ["DEMO_ATS", "GREENHOUSE"] and body["is_active"] is True

    updated = auth_client.put(
        API,
        json={"question_key": "custom:start_date", "question_text": "Start date", "answer": "Immediately"},
    )
    assert updated.status_code == 200 and updated.json()["id"] == body["id"]
    assert updated.json()["applies_to"] == "ALL"

    listed = auth_client.get(API).json()
    assert [(r["question_key"], r["answer"]) for r in listed] == [("custom:start_date", "Immediately")]

    assert auth_client.delete(f"{API}/{body['id']}").status_code == 204
    assert auth_client.get(API).json() == []
    assert auth_client.delete(f"{API}/{body['id']}").status_code == 404

    # Deleting tombstones the row; saving the same question again re-uses the key.
    again = auth_client.put(API, json={"question_key": "custom:start_date", "question_text": "Start date", "answer": "Soon"})
    assert again.status_code == 200 and again.json()["id"] != body["id"]


def test_the_endpoints_validate_and_stay_per_user(auth_client: TestClient, db: Session, owner: User) -> None:
    bad = auth_client.put(API, json={"question_key": "custom:x", "question_text": "X", "answer": "y", "applies_to": []})
    assert bad.status_code == 422
    unknown_source = auth_client.put(API, json={"question_key": "custom:x", "question_text": "X", "answer": "y", "applies_to": ["MYSPACE"]})
    assert unknown_source.status_code == 422
    demographic = auth_client.put(API, json={"question_key": "custom:demographic_gender", "question_text": "Gender", "answer": "y"})
    assert demographic.status_code == 422
    assert demographic.json()["error"]["code"] == "standing_answer_not_allowed"

    someone_else = profiles.upsert_standing_answer(db, owner.id, question_key="custom:why_us", question_text="Why?", answer="z")
    db.commit()
    assert auth_client.get(API).json() == []
    assert auth_client.delete(f"{API}/{someone_else.id}").status_code == 404
    assert auth_client.get(API, headers={"Authorization": ""}).status_code == 401


def test_put_answers_with_save_as_standing(auth_client: TestClient, db: Session) -> None:
    me = _me(db)
    application = make_application(db, me.id, "Acme Cloud")
    start = question_row(application, "custom:start_date", "What is your preferred start date?")
    db.add(start)
    db.commit()

    response = auth_client.put(
        f"/api/v1/applications/{application.id}/answers",
        json={"answers": [{"id": str(start.id), "answer": "1 December 2026", "save_as_standing": True}]},
    )
    assert response.status_code == 200, response.text
    saved = auth_client.get(API).json()
    assert [(r["question_key"], r["answer"]) for r in saved] == [("custom:start_date", "1 December 2026")]
