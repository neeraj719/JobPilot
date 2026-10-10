"""Tests for the AI module (CONTRACTS.md §6).

Everything here runs on the deterministic mock provider — no network, no API keys.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.company import Company
from app.models.enums import AnswerSource, EmailClassification
from app.models.job import Job, JobSource
from app.models.user import User
from app.modules.ai import answer_rules, tasks
from app.modules.ai.factory import get_llm_provider, provider_status, reset_llm_provider
from app.modules.ai.prompts import build_prompt, parse_task_envelope
from app.modules.ai.providers.mock import TASK_NAMES, MockLLMProvider
from app.modules.ai.schemas import JobContext, ParsedResume

try:  # pytest puts ``tests/`` on sys.path; the package path is the fallback
    from helpers.documents import SAMPLE_RESUME_TEXT
except ImportError:  # pragma: no cover
    from tests.helpers.documents import SAMPLE_RESUME_TEXT  # type: ignore[no-redef]


JOB = {
    "id": "11111111-1111-1111-1111-111111111111",
    "title": "Full Stack Developer",
    "company_name": "Northwind Labs",
    "company_description": "Northwind Labs builds logistics software for Indian exporters.",
    "location": "Bangalore, India",
    "work_mode": "HYBRID",
    "description": "Own React and Node.js features end to end.",
    "required_skills": ["React", "Node.js", "PostgreSQL", "AWS"],
    "preferred_skills": ["Docker", "TypeScript"],
    "experience_min": 2,
    "experience_max": 4,
    "salary_min": 1200000,
    "salary_max": 1800000,
    "salary_currency": "INR",
    "source": "DEMO_ATS",
}

CANDIDATE = {
    "flat": {
        "full_name": "Aarav Sharma",
        "first_name": "Aarav",
        "email": "aarav.sharma@example.com",
        "phone": "+91 98765 43210",
        "linkedin_url": "https://linkedin.com/in/aaravsharma",
        "city": "Bangalore",
        "years_of_experience": 2,
        "current_salary": 800000,
        "notice_period_days": 30,
        "work_authorization": {"IN": True, "US": False},
        "requires_sponsorship": False,
        "skill_years:react": 2,
    },
    "headline": "Full Stack Developer",
    "current_company": "Acme Cloud",
    "full_name": "Aarav Sharma",
    "years_of_experience": 2,
    "skills": ["React", "Node.js", "PostgreSQL", "TypeScript", "Docker"],
    "projects": [
        {"name": "JobTracker", "description": "Tracks job applications end to end.", "technologies": ["Next.js", "FastAPI", "PostgreSQL"]}
    ],
    "experience": [{"title": "Software Engineer", "company": "Acme Cloud", "description": "Built internal tools."}],
}

SCORES = {
    "match_score": 84,
    "skill_match": {"matched": ["React", "Node.js", "PostgreSQL"], "missing": ["AWS"], "total": 4},
    "missing_skills": ["AWS"],
    "experience_match": "STRONG",
    "location_match": "MATCH",
    "salary_match": "ABOVE",
    "company_priority": "P2",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.core.rate_limit import rate_limiter

    hits = getattr(getattr(rate_limiter, "_backend", None), "_hits", None)
    if hits is not None:
        hits.clear()
    yield


@pytest.fixture
def api(client: TestClient, db: Session) -> TestClient:
    """Authenticated client (the auth module is owned by another agent, so we mint
    the token ourselves and keep this suite hermetic)."""
    user = User(
        email="ai-tester@example.com",
        hashed_password=hash_password("StrongPass123!"),
        full_name="AI Tester",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    client.headers.update({"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"})
    return client


def _answer(question: str, field_type: str = "TEXT", options: list[str] | None = None, candidate=None):
    return tasks.generate_answer(question, field_type, options or [], JOB, candidate if candidate is not None else CANDIDATE)


# --------------------------------------------------------------------------- provider


def test_default_provider_is_the_mock() -> None:
    reset_llm_provider()
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)
    assert provider is get_llm_provider()  # cached

    reset_llm_provider()
    assert get_llm_provider() is not provider


def test_mock_supports_every_task() -> None:
    provider = MockLLMProvider()
    assert TASK_NAMES == {
        "parse_resume",
        "explain_match",
        "generate_answer",
        "generate_cover_letter",
        "classify_email",
        "generate_interview_prep",
        "polish_resume_recommendations",
    }
    for task_name in TASK_NAMES:
        assert provider.supports_task(task_name)
    assert not provider.supports_task("summarise_the_internet")


def test_mock_answers_prompts_through_the_task_envelope() -> None:
    """A real provider gets a prompt; the mock recovers the payload from it."""
    prompt = build_prompt("classify_email", {"subject": "Offer letter", "sender": "hr@acme.com", "body": "We are pleased to offer you the role."})
    assert parse_task_envelope(prompt)[0] == "classify_email"

    result = MockLLMProvider().complete_json(prompt, schema=None)
    assert result["classification"] == EmailClassification.OFFER.value


def test_status_endpoint(api: TestClient) -> None:
    response = api.get("/api/v1/ai/status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"provider": "mock", "model": "mock-deterministic-v1", "configured": True}
    assert provider_status()["configured"] is True


def test_status_endpoint_requires_auth(client: TestClient) -> None:
    client.headers.pop("Authorization", None)
    assert client.get("/api/v1/ai/status").status_code == 401


# --------------------------------------------------------------------------- parse_resume


def test_parse_resume_is_deterministic_and_grounded() -> None:
    first = tasks.parse_resume(SAMPLE_RESUME_TEXT)
    second = tasks.parse_resume(SAMPLE_RESUME_TEXT)
    assert isinstance(first, ParsedResume)
    assert first.model_dump() == second.model_dump()

    assert first.name == "Aarav Sharma"
    assert first.email == "aarav.sharma@example.com"
    assert first.phone and "98765" in first.phone
    assert {"React", "Node.js", "PostgreSQL"} <= set(first.skills)
    assert first.total_experience_years == pytest.approx(2.0, abs=0.6)
    assert [e.company for e in first.experience] == ["Northwind Labs", "Acme Cloud"]
    assert first.education[0].institution == "VIT University"
    assert first.links.linkedin and "aaravsharma" in first.links.linkedin


def test_parse_resume_invents_nothing_for_empty_input() -> None:
    parsed = tasks.parse_resume("")
    assert parsed.name is None
    assert parsed.email is None
    assert parsed.skills == []
    assert parsed.experience == []
    assert parsed.total_experience_years is None


# --------------------------------------------------------------------------- explain_match


def test_explain_match_is_two_to_four_sentences() -> None:
    import re

    explanation = tasks.explain_match(JOB, CANDIDATE, SCORES)
    # count sentence ends, not every dot ("Node.js" must not count)
    sentences = re.findall(r"[.!?](?=\s|$)", explanation)
    assert 2 <= len(sentences) <= 4
    assert "Northwind Labs" in explanation
    assert "AWS" in explanation  # the missing skill is named


def test_explain_match_respects_the_avoid_list() -> None:
    scores = dict(SCORES, company_priority="AVOID")
    assert tasks.explain_match(JOB, CANDIDATE, scores) == "Company is on your avoid list"


# --------------------------------------------------------------------------- generate_answer


def test_factual_answer_comes_from_the_profile() -> None:
    result = _answer("What is your phone number?", "PHONE")
    assert result.answer == "+91 98765 43210"
    assert result.source == AnswerSource.PROFILE
    assert result.needs_user_input is False
    assert result.confidence >= 0.9


def test_missing_salary_needs_user_input() -> None:
    result = _answer("Expected CTC (INR)", "NUMBER")
    assert result.answer is None
    assert result.needs_user_input is True
    assert result.source != AnswerSource.AI_GENERATED
    assert result.rationale.startswith("Not found in profile: expected_salary")


def test_sponsorship_question_is_never_ai_generated() -> None:
    answered = _answer("Will you require visa sponsorship?", "RADIO", ["Yes", "No"])
    assert answered.answer == "No"
    assert answered.source == AnswerSource.PROFILE
    assert answered.is_sensitive is True

    blank = dict(CANDIDATE, flat={k: v for k, v in CANDIDATE["flat"].items() if k != "requires_sponsorship"})
    unanswered = _answer("Will you require visa sponsorship?", "RADIO", ["Yes", "No"], candidate=blank)
    assert unanswered.answer is None
    assert unanswered.needs_user_input is True
    assert unanswered.source != AnswerSource.AI_GENERATED


def test_demographic_question_is_never_answered() -> None:
    result = _answer("What is your gender?", "SELECT", ["Male", "Female", "Prefer not to say"])
    assert result.answer is None
    assert result.needs_user_input is True
    assert result.is_sensitive is True
    assert result.source != AnswerSource.AI_GENERATED


def test_work_authorization_uses_the_job_country() -> None:
    allowed = _answer("Are you legally authorized to work in India?", "RADIO", ["Yes", "No"])
    assert allowed.answer == "Yes"
    assert allowed.source == AnswerSource.PROFILE

    denied = _answer("Are you legally authorized to work in the United States?", "RADIO", ["Yes", "No"])
    assert denied.answer == "No"

    unknown = _answer("Are you legally authorized to work in Germany?", "RADIO", ["Yes", "No"])
    assert unknown.answer is None
    assert unknown.needs_user_input is True


def test_select_options_are_matched_from_a_fact() -> None:
    result = _answer("What is your notice period?", "SELECT", ["Immediate", "15 days", "30 days", "60 days", "90 days"])
    assert result.answer == "30 days"
    assert result.source == AnswerSource.PREFERENCE
    assert result.needs_user_input is False


def test_skill_years_question_reads_the_skill_map() -> None:
    result = _answer("How many years of experience do you have with React?", "NUMBER")
    assert result.question_key == "skill_years:react"  # lowercase, like the mapper and CandidateContext.flat
    assert result.answer == "2"
    assert result.needs_user_input is False


def test_free_text_answer_uses_real_context_only() -> None:
    result = _answer("Why do you want to work at Northwind Labs?", "TEXTAREA")
    assert result.needs_user_input is False
    assert result.source == AnswerSource.AI_GENERATED
    assert result.confidence == pytest.approx(0.7)
    assert "Northwind Labs" in result.answer
    assert "Full Stack Developer" in result.answer
    assert "React" in result.answer


def test_unknown_custom_question_needs_user_input() -> None:
    result = _answer("What is your preferred start date?", "TEXT")
    assert result.question_key.startswith("custom:")
    assert result.answer is None
    assert result.needs_user_input is True


def test_describe_a_project_uses_the_real_project() -> None:
    result = _answer("Describe a project you are proud of", "TEXTAREA")
    assert "JobTracker" in result.answer
    assert result.source == AnswerSource.AI_GENERATED


def test_answer_accepts_a_candidate_context_object() -> None:
    context = SimpleNamespace(
        flat={"phone": "+91 90000 00000"},
        profile=SimpleNamespace(full_name="Aarav Sharma", headline="Backend Engineer", skills=["Python"]),
        preferences=SimpleNamespace(notice_period_days=45),
        resume=None,
        resume_path=None,
    )
    result = tasks.generate_answer("Phone number", "PHONE", [], JOB, context)
    assert result.answer == "+91 90000 00000"

    notice = tasks.generate_answer("Notice period (days)", "NUMBER", [], JOB, context)
    assert notice.answer == "45"  # filled from the preferences object


def test_question_key_can_be_supplied_by_the_caller() -> None:
    result = tasks.generate_answer("Mobile", "PHONE", [], JOB, CANDIDATE, question_key="phone")
    assert result.question_key == "phone"
    assert result.answer == "+91 98765 43210"


def test_infer_question_key_covers_the_canonical_vocabulary() -> None:
    assert answer_rules.infer_question_key("Current CTC") == "current_salary"
    assert answer_rules.infer_question_key("Expected CTC") == "expected_salary"
    assert answer_rules.infer_question_key("LinkedIn Profile") == "linkedin_url"
    assert answer_rules.infer_question_key("Upload your resume", "FILE") == "resume_file"
    assert answer_rules.infer_question_key("Total years of experience") == "years_of_experience"
    assert answer_rules.is_sensitive_key("work_authorization")
    assert answer_rules.is_sensitive_key("custom:demographic_gender")
    assert not answer_rules.is_sensitive_key("phone")


# --------------------------------------------------------------------------- cover letter


def test_cover_letter_is_short_and_grounded() -> None:
    letter = tasks.generate_cover_letter(JOB, CANDIDATE)
    assert len(letter.split()) <= 250
    assert "Northwind Labs" in letter
    assert "Full Stack Developer" in letter
    assert letter == tasks.generate_cover_letter(JOB, CANDIDATE)


# --------------------------------------------------------------------------- emails


@pytest.mark.parametrize(
    ("subject", "sender", "body", "expected"),
    [
        (
            "We received your application",
            "no-reply@greenhouse.io",
            "Thank you for applying to the Backend Engineer role.",
            EmailClassification.APPLICATION_RECEIVED,
        ),
        (
            "Interview invitation",
            "recruiting@northwindlabs.com",
            "Are you available for a technical round this week?",
            EmailClassification.INTERVIEW,
        ),
        (
            "Your coding challenge",
            "no-reply@hackerrank.com",
            "Please complete the assessment using the test link below.",
            EmailClassification.ASSESSMENT,
        ),
        (
            "Update on your application",
            "careers@acmecloud.com",
            "Unfortunately we are not moving forward with your application; we chose other candidates.",
            EmailClassification.REJECTION,
        ),
        (
            "Offer letter",
            "hr@northwindlabs.com",
            "We are pleased to offer you the role. Compensation details are attached.",
            EmailClassification.OFFER,
        ),
        (
            "An opportunity for you",
            "recruiter@zetatech.io",
            "I came across your profile and wanted to reach out about an opportunity.",
            EmailClassification.RECRUITER_MESSAGE,
        ),
        ("Lunch on Saturday?", "friend@gmail.com", "Are we still on?", EmailClassification.OTHER),
    ],
)
def test_classify_email(subject: str, sender: str, body: str, expected: EmailClassification) -> None:
    result = tasks.classify_email(subject, sender, body)
    assert result.classification == expected
    assert 0.0 < result.confidence <= 1.0
    assert result.reason


def test_classify_email_extracts_hints() -> None:
    result = tasks.classify_email(
        "Your application for the Backend Engineer role at Northwind Labs",
        "careers@northwindlabs.com",
        "Thank you for applying.",
    )
    assert result.company_hint and "northwind" in result.company_hint.lower()
    assert result.job_title_hint == "Backend Engineer"

    generic = tasks.classify_email("Hello", "someone@gmail.com", "Hi")
    assert generic.company_hint is None


# --------------------------------------------------------------------------- interview prep


def test_interview_prep_is_grounded_in_the_job_and_resume() -> None:
    prep = tasks.generate_interview_prep(JOB, CANDIDATE, "TECHNICAL")
    assert all(len(getattr(prep, bucket)) >= 4 for bucket in ("technical", "behavioral", "company_specific", "job_specific"))
    assert any("React" in q for q in prep.technical)
    assert all("Northwind Labs" in q for q in prep.company_specific[:1])
    assert any("JobTracker" in q for q in prep.resume_based)
    assert prep.model_dump() == tasks.generate_interview_prep(JOB, CANDIDATE, "TECHNICAL").model_dump()


# --------------------------------------------------------------------------- JobContext


def test_job_context_from_job(db: Session) -> None:
    from datetime import datetime, timezone

    company = Company(name="Northwind Labs", normalized_name="northwindlabs", description="Logistics software.")
    db.add(company)
    db.flush()
    job = Job(
        company_id=company.id,
        title="Full Stack Developer",
        normalized_title="full stack developer",
        description="React and Node.js",
        location="Bangalore, India",
        required_skills=["React", "Node.js"],
        preferred_skills=["Docker"],
        experience_min=2,
        experience_max=4,
        salary_min=1200000,
        salary_max=1800000,
        salary_currency="INR",
        dedupe_hash="hash-1",
    )
    db.add(job)
    db.flush()
    now = datetime.now(timezone.utc)
    db.add(
        JobSource(
            job_id=job.id,
            source="DEMO_ATS",
            external_id="demo-1",
            url="http://localhost:8000/demo-ats/jobs/demo-1",
            discovered_at=now,
            last_seen_at=now,
        )
    )
    db.commit()

    context = JobContext.from_job(job)
    assert context.id == str(job.id)
    assert context.title == "Full Stack Developer"
    assert context.company_name == "Northwind Labs"
    assert context.company_description == "Logistics software."
    assert context.required_skills == ["React", "Node.js"]
    assert context.source == "DEMO_ATS"

    # The tasks accept a Job row directly, not just a JobContext.
    explanation = tasks.explain_match(job, CANDIDATE, SCORES)
    assert "Northwind Labs" in explanation


def test_job_context_coerces_dicts_and_none() -> None:
    assert JobContext.coerce(JOB).company_name == "Northwind Labs"
    assert JobContext.coerce(None).title == ""
    assert JobContext.coerce(JobContext.coerce(JOB)).title == "Full Stack Developer"


def test_tasks_tolerate_a_missing_candidate() -> None:
    result = tasks.generate_answer("What is your phone number?", "PHONE", [], JOB, None)
    assert result.needs_user_input is True
    assert uuid.UUID(JOB["id"])  # sanity: the fixture id stays a valid UUID
