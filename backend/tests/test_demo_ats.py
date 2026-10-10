"""The demo ATS careers site (CONTRACTS.md section 12, end of).

Served at ``/demo-ats`` without auth, so every test here uses the plain ``client``
fixture. Submissions land in ``UPLOAD_DIR/demo_ats_submissions.jsonl``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.demo_ats.catalog import DEMO_JOBS, get_demo_job, list_demo_jobs
from app.demo_ats.router import submissions_path

SLUG = "northwind-labs-full-stack-engineer"
KUBERNETES_SLUG = "acme-cloud-platform-engineer"
APPLICATION_ID_RE = re.compile(r"Application ID: (DEMO-[A-Z0-9]{6})")


def valid_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "first_name": "Aarav",
        "last_name": "Sharma",
        "email": "aarav.sharma@example.com",
        "phone": "+91 98765 43210",
        "location": "Bangalore",
        "linkedin": "https://linkedin.com/in/aarav",
        "github": "https://github.com/aarav",
        "portfolio": "",
        "total_experience": "2",
        "react_experience": "2",
        "current_ctc": "800000",
        "expected_ctc": "1200000",
        "notice_period": "30 days",
        "work_authorization": "Yes",
        "why_company": "You ship fast and the product is one I would use.",
        "start_date": "1 November 2026",
        "consent": "true",
    }
    payload.update(overrides)
    return payload


def resume_file() -> dict[str, tuple[str, bytes, str]]:
    return {"resume": ("aarav_resume.pdf", b"%PDF-1.4 demo resume\n", "application/pdf")}


def apply_(client: TestClient, slug: str = SLUG, **overrides: str):
    return client.post(f"/demo-ats/jobs/{slug}/apply", data=valid_payload(**overrides), files=resume_file())


# --------------------------------------------------------------------------- catalogue


def test_catalogue_covers_the_demo_scenarios() -> None:
    jobs = list_demo_jobs()
    assert len(jobs) == 8
    assert len({j["slug"] for j in jobs}) == 8
    mirrors = [j for j in jobs if j["is_mirror"]]
    assert len(mirrors) == 3
    assert all("(Demo Careers)" in j["company"] for j in mirrors)
    assert all(j["company_domain"].endswith(".example") for j in mirrors)
    assert all(j["logo_url"] is None for j in mirrors)
    # one posting demos missing skills, one demos being UNDER-experienced
    assert any("Kubernetes" in j["required_skills"] for j in jobs)
    assert any(j["experience_min"] >= 6 for j in jobs)
    for job in jobs:
        assert job["description"].count("\n\n") >= 2, job["slug"]
        assert job["custom_questions"], job["slug"]


def test_get_demo_job_by_slug() -> None:
    assert get_demo_job(SLUG)["title"] == "Full Stack Engineer"
    assert get_demo_job("nope") is None


# --------------------------------------------------------------------------- pages


def test_index_lists_every_company(client: TestClient) -> None:
    response = client.get("/demo-ats/")
    assert response.status_code == 200
    body = response.text
    for company in ("Northwind Labs", "Acme Cloud", "Bluefin Analytics", "Google (Demo Careers)"):
        assert company in body
    assert "fictional" in body.lower()


def test_jobs_json_shape(client: TestClient) -> None:
    response = client.get("/demo-ats/jobs.json")
    assert response.status_code == 200
    jobs = response.json()
    assert isinstance(jobs, list) and len(jobs) == len(DEMO_JOBS)
    job = next(j for j in jobs if j["slug"] == SLUG)
    for key in (
        "external_id", "slug", "title", "company", "company_name", "company_domain", "company_logo_url",
        "location", "work_mode", "employment_type", "salary_min", "salary_max", "salary_currency",
        "experience_min", "experience_max", "required_skills", "preferred_skills", "description",
        "posted_at", "url", "apply_url", "application_type", "source", "is_mirror", "custom_questions",
    ):
        assert key in job, key
    assert job["source"] == "DEMO_ATS"
    assert job["application_type"] == "ATS_FORM"
    assert job["work_mode"] == "HYBRID"
    assert job["apply_url"].endswith(f"/demo-ats/jobs/{SLUG}/apply")
    assert job["apply_url"].startswith(settings.DEMO_ATS_BASE_URL)


def test_job_detail_page(client: TestClient) -> None:
    response = client.get(f"/demo-ats/jobs/{SLUG}")
    assert response.status_code == 200
    assert "Full Stack Engineer" in response.text
    assert f"/demo-ats/jobs/{SLUG}/apply" in response.text


def test_unknown_job_is_404(client: TestClient) -> None:
    response = client.get("/demo-ats/jobs/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_apply_form_contains_every_contract_field(client: TestClient) -> None:
    body = client.get(f"/demo-ats/jobs/{SLUG}/apply").text
    for name in (
        "first_name", "last_name", "email", "phone", "location", "linkedin", "github", "portfolio",
        "resume", "total_experience", "react_experience", "current_ctc", "expected_ctc",
        "notice_period", "work_authorization", "why_company", "start_date", "consent",
    ):
        assert f'name="{name}"' in body, name
    assert '<button type="submit">Submit Application</button>' in body
    assert 'type="file"' in body
    for option in ("Immediate", "15 days", "30 days", "60 days", "90 days"):
        assert f'value="{option}"' in body
    assert 'for="first_name"' in body  # real label associations
    assert 'class="g-recaptcha"' not in body  # only rendered with ?captcha=1


def test_job_specific_custom_question_is_rendered(client: TestClient) -> None:
    body = client.get(f"/demo-ats/jobs/{KUBERNETES_SLUG}/apply").text
    assert 'name="kubernetes_experience"' in body
    assert "Describe your experience with Kubernetes" in body
    assert 'name="start_date"' not in body


def test_captcha_flag_renders_the_widget(client: TestClient) -> None:
    body = client.get(f"/demo-ats/jobs/{SLUG}/apply?captcha=1").text
    assert '<div class="g-recaptcha" data-sitekey="demo">' in body
    assert "never attempted" in body


# --------------------------------------------------------------------------- submitting


def test_submit_application_confirms_and_appends_a_jsonl_line(client: TestClient) -> None:
    before = submissions_path().read_text(encoding="utf-8").count("\n") if submissions_path().exists() else 0
    response = apply_(client)
    assert response.status_code == 200
    body = response.text
    assert "Thank you for applying" in body
    match = APPLICATION_ID_RE.search(body)
    assert match, body[:400]
    application_id = match.group(1)

    path = submissions_path()
    assert path.exists()
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == before + 1
    record = json.loads(lines[-1])
    assert record["application_id"] == application_id
    assert record["slug"] == SLUG
    assert record["company"] == "Northwind Labs"
    assert record["answers"]["email"] == "aarav.sharma@example.com"
    assert record["answers"]["notice_period"] == "30 days"
    assert record["answers"]["consent"] is True
    assert record["resume_filename"] == "aarav_resume.pdf"
    assert Path(record["resume_path"]).exists()


def test_application_ids_are_unique_per_submission(client: TestClient) -> None:
    ids = {APPLICATION_ID_RE.search(apply_(client).text).group(1) for _ in range(3)}
    assert len(ids) == 3


def test_missing_required_fields_are_rejected(client: TestClient) -> None:
    response = client.post(
        f"/demo-ats/jobs/{SLUG}/apply",
        data=valid_payload(first_name="", notice_period=""),
        files=resume_file(),
    )
    assert response.status_code == 422
    assert "First Name is required." in response.text
    assert "Notice Period is required." in response.text
    assert "Thank you for applying" not in response.text
    # the form is re-rendered with what the applicant already typed
    assert 'value="Sharma"' in response.text


def test_missing_resume_and_consent_are_rejected(client: TestClient) -> None:
    response = client.post(f"/demo-ats/jobs/{SLUG}/apply", data=valid_payload(consent=""))
    assert response.status_code == 422
    assert "Resume/CV is required." in response.text
    assert "You must consent" in response.text


def test_required_custom_question_is_enforced(client: TestClient) -> None:
    payload = valid_payload()
    payload.pop("start_date")
    response = client.post(f"/demo-ats/jobs/{SLUG}/apply", data=payload, files=resume_file())
    assert response.status_code == 422
    assert "What is your preferred start date? is required." in response.text


def test_submissions_json_returns_newest_first(client: TestClient) -> None:
    first = APPLICATION_ID_RE.search(apply_(client).text).group(1)
    second = APPLICATION_ID_RE.search(apply_(client, email="second.applicant@example.com").text).group(1)
    response = client.get("/demo-ats/submissions.json")
    assert response.status_code == 200
    records = response.json()
    assert len(records) <= 50
    ids = [r["application_id"] for r in records]
    assert ids[0] == second
    assert ids.index(second) < ids.index(first)


# --------------------------------------------------------------------------- simulated email


def test_submission_by_an_unknown_email_still_succeeds(client: TestClient) -> None:
    response = apply_(client, email="nobody@example.com")
    assert response.status_code == 200
    assert "Thank you for applying" in response.text


def test_confirmation_email_is_simulated_for_a_jobpilot_user(client: TestClient, db: Session) -> None:
    pytest.importorskip(
        "app.modules.emails.service",
        reason="emails module is not implemented yet (owned by the emails+integrations agent)",
    )
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models.email import EmailMessage
    from app.models.user import User

    email = "known.user@example.com"
    user = User(email=email, hashed_password=hash_password("StrongPass123!"), full_name="Known User")
    db.add(user)
    db.commit()

    assert apply_(client, email=email).status_code == 200

    messages = db.scalars(select(EmailMessage).where(EmailMessage.user_id == user.id)).all()
    assert messages, "expected a simulated confirmation email for the applicant"
    message = messages[0]
    assert "Thank you for applying to Northwind Labs" in message.subject
    assert message.sender.endswith("@northwindlabs.dev")
    assert "DEMO-" in (message.body_text or "")
