"""ATS optimizer - endpoints: analyses (create / poll / list), apply with server-side validation,
re-run, ignore, undo, auto-optimize, job targets (CRUD, status audit, snapshots, refresh),
tailoring, compare, ownership and the summary. The background polish runs against a fake model."""
from __future__ import annotations

import html
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ats import AtsAnalysis, JobTarget, OptimizationSuggestion
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.enums import AtsAnalysisStatus, EmploymentType, ResumeChangeSource, ResumeKind, WorkMode
from app.models.job import Job
from app.models.profile import UserProfile
from app.models.resume import Resume, ResumeVersion
from app.modules.ats import llm
from app.modules.ats import service as ats_service
from app.modules.jobs.dedupe import compute_dedupe_hash
from app.modules.resumes import recommendations as rec_mod

try:
    from helpers.ats import BACKEND_JD, FRONTEND_JD, backend_resume, headers, make_resume, make_user, no_page_network  # noqa: F401
except ImportError:  # pragma: no cover
    from tests.helpers.ats import BACKEND_JD, FRONTEND_JD, backend_resume, headers, make_resume, make_user, no_page_network  # type: ignore[no-redef]  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_page_network")

ATS = "/api/v1/ats"


@pytest.fixture(autouse=True)
def _fresh_cache():
    rec_mod.clear_cache()
    yield
    rec_mod.clear_cache()


@pytest.fixture
def owner(db: Session):
    user = make_user(db, "ats.owner@example.com")
    db.add(UserProfile(user_id=user.id, full_name="Asha Rao", skills=["Kubernetes"], years_of_experience=4.5))
    resume = make_resume(db, user)
    db.commit()
    return {"user": user, "headers": headers(user), "resume_id": str(resume.id)}


def _analyse(client: TestClient, owner: dict, jd: dict | None = None, **extra) -> dict:
    body = {"resume_id": owner["resume_id"], "jd": jd or {"text": BACKEND_JD, "company": "Acme"}, **extra}
    r = client.post(f"{ATS}/analyses", json=body, headers=owner["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def _by_kind(analysis: dict, kind: str) -> list[dict]:
    return [s for s in analysis["suggestions"] if s["kind"] == kind]


# --------------------------------------------------------------------------- analyses


def test_create_poll_and_list(client: TestClient, owner: dict):
    analysis = _analyse(client, owner)
    assert analysis["status"] == "DONE" and analysis["progress"] == 100  # mock provider: nothing to polish
    assert 0 <= analysis["overall_score"] <= 100
    assert "not the score of any employer" in analysis["disclaimer"]
    assert {c["key"] for c in analysis["category_scores"]} >= {"keyword_coverage", "parse_risk"}
    assert {"Go", "Kubernetes"} <= {m["keyword"] for m in analysis["missing_keywords"]}
    assert analysis["jd"]["company"] == "Acme" and analysis["jd"]["title"] == "Senior Backend Engineer"
    assert analysis["is_current"] is True

    polled = client.get(f"{ATS}/analyses/{analysis['id']}", headers=owner["headers"]).json()
    assert polled["overall_score"] == analysis["overall_score"]
    listed = client.get(f"{ATS}/analyses", params={"resume_id": owner["resume_id"]}, headers=owner["headers"]).json()
    assert [a["id"] for a in listed] == [analysis["id"]] and listed[0]["jd_company"] == "Acme"

    again = _analyse(client, owner)
    assert again["overall_score"] == analysis["overall_score"]  # deterministic


def test_methodology_and_custom_weights(client: TestClient, owner: dict):
    method = client.get(f"{ATS}/methodology", headers=owner["headers"]).json()
    assert method["version"] and len(method["categories"]) == 9
    analysis = _analyse(client, owner, weights={"keyword_coverage": 0.5})
    assert analysis["weights"]["keyword_coverage"] > method["categories"][0]["weight"]
    r = client.post(
        f"{ATS}/analyses", json={"resume_id": owner["resume_id"], "jd": {"text": BACKEND_JD}, "weights": {"magic": 0.2}}, headers=owner["headers"]
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_weight"


def test_jd_must_be_exactly_one_source(client: TestClient, owner: dict):
    r = client.post(f"{ATS}/analyses", json={"resume_id": owner["resume_id"], "jd": {}}, headers=owner["headers"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "jd_required"


def test_client_structure_is_revalidated_against_the_text(client: TestClient, owner: dict):
    structured = {"title": "Senior Backend Engineer", "required_skills": ["Python", "COBOL"], "preferred_skills": []}
    analysis = _analyse(client, owner, jd={"text": BACKEND_JD, "structured": structured})
    keywords = {m["keyword"] for m in analysis["missing_keywords"]} | {m["keyword"] for m in analysis["matched_keywords"]}
    assert "COBOL" not in keywords  # not in the posting, so dropped


def test_confirmation_items_are_never_safe(client: TestClient, owner: dict):
    analysis = _analyse(client, owner)
    go = next(s for s in _by_kind(analysis, "ADD_SKILL") if s["after"] == "Go")
    assert go["safe"] is False and go["requires_confirmation"] is True and go["confirmation_label"] == "I have used Go"
    k8s = next(s for s in _by_kind(analysis, "ADD_SKILL") if s["after"] == "Kubernetes")
    assert k8s["safe"] is True  # the profile lists it
    assert all(not s["requires_confirmation"] for s in analysis["suggestions"] if s["safe"])


# --------------------------------------------------------------------------- apply


def test_apply_saves_a_version_reruns_and_records_ai(client: TestClient, owner: dict, db: Session):
    analysis = _analyse(client, owner)
    safe = [s for s in analysis["suggestions"] if s["safe"]]
    assert safe
    r = client.post(f"{ATS}/analyses/{analysis['id']}/apply", json={"suggestion_ids": [s["id"] for s in safe]}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["resume"]["current_version"] == 2 and result["restorable_version"] == 1
    assert result["previous_score"] == analysis["overall_score"]
    assert result["analysis"]["overall_score"] > analysis["overall_score"]  # re-run on the new version
    assert result["analysis"]["previous_analysis_id"] == analysis["id"]
    assert result["analysis"]["resume_version"] == 2
    version = db.scalar(select(ResumeVersion).where(ResumeVersion.resume_id == uuid.UUID(owner["resume_id"]), ResumeVersion.version_number == 2))
    assert version.change_source == ResumeChangeSource.AI and version.note.startswith("ATS: applied")
    db.expire_all()
    resume = db.get(Resume, uuid.UUID(owner["resume_id"]))
    assert "Kubernetes" in resume.parsed_data["skills"] and "Go" not in resume.parsed_data["skills"]
    assert resume.parsed_data["skills"][0] == "Python"  # reordered to the posting
    old = client.get(f"{ATS}/analyses/{analysis['id']}", headers=owner["headers"]).json()
    assert {s["status"] for s in old["suggestions"] if s["safe"]} == {"APPLIED"}
    assert old["is_current"] is False
    assert db.scalar(select(AuditLog).where(AuditLog.action == "ats.suggestions_applied")) is not None


def test_apply_validates_on_the_server(client: TestClient, owner: dict):
    analysis = _analyse(client, owner)
    url = f"{ATS}/analyses/{analysis['id']}/apply"
    h = owner["headers"]

    r = client.post(url, json={"suggestion_ids": [str(uuid.uuid4())]}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_suggestion"

    manual = _by_kind(analysis, "MANUAL")[0]
    r = client.post(url, json={"suggestion_ids": [manual["id"]]}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_applicable"

    summary = _by_kind(analysis, "REPLACE_SUMMARY")[0]
    r = client.post(url, json={"suggestion_ids": [summary["id"]], "edits": {summary["id"]: "Backend engineer with 37 years of Python."}}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invented_number"
    assert r.json()["error"]["details"]["id"] == summary["id"]

    r = client.post(url, json={"suggestion_ids": [summary["id"]], "edits": {summary["id"]: "Backend engineer who [add your result]."}}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "placeholder_left"

    needs_edit = next(s for s in _by_kind(analysis, "REPLACE_BULLET") if s["after"] is None)
    r = client.post(url, json={"suggestion_ids": [needs_edit["id"]]}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "edit_required"


def test_edited_text_is_the_users_own_version(client: TestClient, owner: dict, db: Session):
    analysis = _analyse(client, owner)
    bullet = next(s for s in _by_kind(analysis, "REPLACE_BULLET") if s["after"] is None)
    mine = "Built internal tools in Python that cut onboarding time by 30%."
    r = client.post(
        f"{ATS}/analyses/{analysis['id']}/apply", json={"suggestion_ids": [bullet["id"]], "edits": {bullet["id"]: mine}}, headers=owner["headers"]
    )
    assert r.status_code == 200, r.text
    assert r.json()["applied"][0]["edited"] is True
    version = db.scalar(select(ResumeVersion).where(ResumeVersion.resume_id == uuid.UUID(owner["resume_id"]), ResumeVersion.version_number == 2))
    assert version.change_source == ResumeChangeSource.USER
    assert mine in version.parsed_data["experience"][1]["description"]
    stored = db.get(OptimizationSuggestion, uuid.UUID(bullet["id"]))
    assert stored.status.value == "EDITED" and stored.after == mine


def test_stale_analysis_is_a_conflict(client: TestClient, owner: dict):
    analysis = _analyse(client, owner)
    safe = [s["id"] for s in analysis["suggestions"] if s["safe"]]
    client.put(f"/api/v1/resumes/{owner['resume_id']}/parsed-data", json=backend_resume(), headers=owner["headers"])
    r = client.post(f"{ATS}/analyses/{analysis['id']}/apply", json={"suggestion_ids": safe}, headers=owner["headers"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_resume"


def test_ignore_and_unignore(client: TestClient, owner: dict):
    analysis = _analyse(client, owner)
    go = next(s for s in _by_kind(analysis, "ADD_SKILL") if s["after"] == "Go")
    r = client.post(f"{ATS}/analyses/{analysis['id']}/ignore", json={"suggestion_ids": [go["id"]]}, headers=owner["headers"])
    assert next(s for s in r.json()["suggestions"] if s["id"] == go["id"])["status"] == "IGNORED"
    r = client.post(f"{ATS}/analyses/{analysis['id']}/ignore", json={"suggestion_ids": [go["id"]], "ignore": False}, headers=owner["headers"])
    assert next(s for s in r.json()["suggestions"] if s["id"] == go["id"])["status"] == "PROPOSED"


def test_undo_restores_the_previous_content_as_a_new_version(client: TestClient, owner: dict, db: Session):
    analysis = _analyse(client, owner)
    safe = [s["id"] for s in analysis["suggestions"] if s["safe"]]
    applied = client.post(f"{ATS}/analyses/{analysis['id']}/apply", json={"suggestion_ids": safe}, headers=owner["headers"]).json()
    r = client.post(f"{ATS}/analyses/{applied['analysis']['id']}/undo", headers=owner["headers"])
    assert r.status_code == 200, r.text
    undone = r.json()
    assert undone["restored_version"] == 1 and undone["resume"]["current_version"] == 3
    assert undone["analysis"]["overall_score"] == analysis["overall_score"]
    db.expire_all()
    assert db.get(Resume, uuid.UUID(owner["resume_id"])).parsed_data["skills"] == backend_resume()["skills"]
    first = client.get(f"{ATS}/analyses/{analysis['id']}", headers=owner["headers"]).json()
    assert {s["status"] for s in first["suggestions"]} == {"PROPOSED"}


def test_auto_optimize_creates_a_tailored_resume(client: TestClient, owner: dict, db: Session):
    analysis = _analyse(client, owner)
    r = client.post(f"{ATS}/analyses/{analysis['id']}/auto-optimize", json={"mode": "new_resume"}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["resume"]["kind"] == "TAILORED" and result["resume"]["source_resume_id"] == owner["resume_id"]
    assert "Acme" in result["resume"]["name"]
    assert result["analysis"]["overall_score"] > analysis["overall_score"]
    assert result["explanations"] and all(e["why"] for e in result["explanations"])
    applied_ids = {a["id"] for a in result["applied"]}
    confirmation_ids = {s["id"] for s in analysis["suggestions"] if s["requires_confirmation"]}
    assert not applied_ids & confirmation_ids
    tailored = db.get(Resume, uuid.UUID(result["resume"]["id"]))
    assert tailored.kind == ResumeKind.TAILORED and "Go" not in tailored.parsed_data["skills"]
    first = db.scalar(select(ResumeVersion).where(ResumeVersion.resume_id == tailored.id))
    assert first.change_source == ResumeChangeSource.AI
    source = db.get(Resume, uuid.UUID(owner["resume_id"]))
    assert source.current_version == 1  # the original is untouched


def test_auto_optimize_new_version(client: TestClient, owner: dict):
    analysis = _analyse(client, owner)
    result = client.post(f"{ATS}/analyses/{analysis['id']}/auto-optimize", json={"mode": "new_version"}, headers=owner["headers"]).json()
    assert result["resume"]["id"] == owner["resume_id"] and result["resume"]["current_version"] == 2


# --------------------------------------------------------------------------- polish (fake model)


def test_background_polish_keeps_only_guard_passing_rewrites(client: TestClient, owner: dict, db: Session, monkeypatch):
    analysis = _analyse(client, owner)
    row = db.get(AtsAnalysis, uuid.UUID(analysis["id"]))
    row.status = AtsAnalysisStatus.RUNNING
    db.commit()
    answers = iter(
        [
            {"bullet": "Developed REST APIs for the billing service using Python and Django, enabling faster invoicing."},
            {"bullet": "Led a team of 12 engineers building internal tools in Python."},  # invented claim + number
        ]
        + [{"bullet": "x"}] * 10
    )
    monkeypatch.setattr(llm, "llm_json", lambda task, prompt, **kw: next(answers))
    monkeypatch.setattr(llm, "model_info", lambda task=None: ("fake", "fake-1"))
    ats_service.polish_analysis(row.id)
    polled = client.get(f"{ATS}/analyses/{analysis['id']}", headers=owner["headers"]).json()
    assert polled["status"] == "DONE" and polled["progress"] == 100 and polled["ai_provider"] == "fake"
    bullets = _by_kind(polled, "REPLACE_BULLET")
    assert not any("Led a team" in (s["after"] or "") for s in bullets)
    assert any(s["checks"].get("ai_rejected") for s in bullets) or any(s["checks"].get("ai_polished") for s in bullets)


def test_polish_failure_keeps_the_rule_suggestions(client: TestClient, owner: dict, db: Session, monkeypatch):
    analysis = _analyse(client, owner)
    row = db.get(AtsAnalysis, uuid.UUID(analysis["id"]))
    row.status = AtsAnalysisStatus.RUNNING
    db.commit()

    def down(*a, **kw):
        raise RuntimeError("provider_timeout: the model took too long")

    monkeypatch.setattr(llm, "llm_json", down)
    ats_service.polish_analysis(row.id)
    polled = client.get(f"{ATS}/analyses/{analysis['id']}", headers=owner["headers"]).json()
    assert polled["status"] == "DONE" and "AI polish unavailable" in polled["error"]
    assert len(polled["suggestions"]) == len(analysis["suggestions"])


def test_retry_polish_needs_a_model(client: TestClient, owner: dict):
    analysis = _analyse(client, owner)
    r = client.post(f"{ATS}/analyses/{analysis['id']}/polish", headers=owner["headers"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "provider_not_configured"


# --------------------------------------------------------------------------- targets


def _target(client: TestClient, owner: dict, **body) -> dict:
    payload = {"company_name": "Acme", "role_title": "Senior Backend Engineer", "job_url": "https://jobs.example.com/acme/backend"} | body
    r = client.post(f"{ATS}/targets", json=payload, headers=owner["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def test_targets_crud_filters_and_duplicates(client: TestClient, owner: dict, db: Session):
    target = _target(client, owner, jd={"source": "PASTED", "text": BACKEND_JD}, source_resume_id=owner["resume_id"])
    assert target["status"] == "SAVED" and target["latest_snapshot"]["structured"]["years_min"] == 5.0
    assert "Python" in target["required_skills"] and target["source_resume"]["id"] == owner["resume_id"]
    _target(client, owner, company_name="Globex", role_title="Frontend Engineer", job_url=None)

    r = client.post(f"{ATS}/targets", json={"company_name": "ACME Pvt Ltd", "role_title": "senior backend engineer", "job_url": "https://www.jobs.example.com/acme/backend/"}, headers=owner["headers"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "target_exists" and r.json()["error"]["details"]["id"] == target["id"]

    page = client.get(f"{ATS}/targets", params={"search": "front"}, headers=owner["headers"]).json()
    assert page["total"] == 1 and page["items"][0]["company_name"] == "Globex"
    page = client.get(f"{ATS}/targets", params={"company": "acme"}, headers=owner["headers"]).json()
    assert [t["id"] for t in page["items"]] == [target["id"]]
    page = client.get(f"{ATS}/targets", params={"status": ["SAVED", "READY"], "page_size": 1}, headers=owner["headers"]).json()
    assert page["total"] == 2 and len(page["items"]) == 1

    r = client.patch(f"{ATS}/targets/{target['id']}", json={"notes": "Referral from Priya", "deadline": "2026-11-30T00:00:00Z"}, headers=owner["headers"])
    assert r.json()["notes"] == "Referral from Priya"

    assert client.delete(f"{ATS}/targets/{target['id']}", headers=owner["headers"]).status_code == 204
    assert client.get(f"{ATS}/targets/{target['id']}", headers=owner["headers"]).status_code == 404
    assert db.scalar(select(JobTarget).where(JobTarget.id == uuid.UUID(target["id"])).execution_options(include_deleted=True)).deleted_at
    again = _target(client, owner)  # a deleted target can be saved again (partial unique index)
    assert again["id"] != target["id"]


def test_status_changes_are_audited_and_applied_records_the_version(client: TestClient, owner: dict, db: Session):
    target = _target(client, owner, source_resume_id=owner["resume_id"])
    r = client.patch(f"{ATS}/targets/{target['id']}", json={"status": "APPLIED"}, headers=owner["headers"])
    assert r.status_code == 200 and r.json()["status"] == "APPLIED" and r.json()["submitted_resume_version"] == 1
    log = db.scalar(select(AuditLog).where(AuditLog.action == "ats.target_status_changed"))
    assert log.meta["from"] == "SAVED" and log.meta["to"] == "APPLIED"
    detail = client.get(f"{ATS}/targets/{target['id']}", headers=owner["headers"]).json()
    assert any(item["kind"] == "status" for item in detail["activity"])


def test_snapshot_change_detection_and_refresh(client: TestClient, owner: dict, no_page_network):
    target = _target(client, owner, jd={"source": "PASTED", "text": BACKEND_JD})
    url = f"{ATS}/targets/{target['id']}/snapshot"
    same = client.post(url, json={"source": "PASTED", "text": BACKEND_JD + "\n\n"}, headers=owner["headers"]).json()
    assert same["created"] is False  # whitespace-only change: same snapshot
    changed = BACKEND_JD.replace("- Familiarity with Terraform", "- Familiarity with Terraform and Snowflake")
    result = client.post(url, json={"source": "PASTED", "text": changed}, headers=owner["headers"]).json()
    assert result["created"] is True and result["snapshot"]["changed_from_previous"] is True
    assert result["snapshot"]["changes"]["added_preferred"] == ["Snowflake"]

    page = f"<main>{html.escape(changed.replace('Kafka or RabbitMQ', 'Kafka')).replace(chr(10), '<br>')}</main>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=f"<html><body>{page}</body></html>")

    no_page_network.set_transport(httpx.MockTransport(handler))
    r = client.post(f"{ATS}/targets/{target['id']}/refresh", headers=owner["headers"])
    assert r.status_code == 200, r.text
    refreshed = r.json()
    assert refreshed["created"] is True and refreshed["snapshot"]["source"] == "URL"
    assert refreshed["snapshot"]["changes"]["removed_preferred"] == ["RabbitMQ"]
    detail = client.get(f"{ATS}/targets/{target['id']}", headers=owner["headers"]).json()
    assert len(detail["snapshots"]) == 3 and detail["latest_snapshot"]["id"] == refreshed["snapshot"]["id"]


def test_save_an_analysis_as_a_job_target(client: TestClient, owner: dict):
    analysis = _analyse(client, owner)
    r = client.post(f"{ATS}/targets", json={"snapshot_id": analysis["snapshot_id"], "analysis_id": analysis["id"]}, headers=owner["headers"])
    assert r.status_code == 201, r.text
    target = r.json()
    assert target["company_name"] == "Acme" and target["role_title"] == "Senior Backend Engineer"
    assert target["latest_snapshot_id"] == analysis["snapshot_id"] and target["last_score"] == analysis["overall_score"]
    assert target["source_resume"]["id"] == owner["resume_id"]
    assert client.get(f"{ATS}/analyses", params={"job_target_id": target["id"]}, headers=owner["headers"]).json()[0]["id"] == analysis["id"]


def test_target_from_a_discovered_job(client: TestClient, owner: dict, db: Session):
    company = Company(name="Initrode", normalized_name="initrode")
    db.add(company)
    db.flush()
    job = Job(
        company_id=company.id, title="Senior Backend Engineer", normalized_title="senior backend engineer",
        description=BACKEND_JD, location="Pune", normalized_location="pune", work_mode=WorkMode.HYBRID,
        employment_type=EmploymentType.FULL_TIME, required_skills=["Python", "PostgreSQL"], preferred_skills=[],
        canonical_url="https://initrode.example.com/jobs/1", dedupe_hash=compute_dedupe_hash("initrode", "senior backend engineer", "pune"),
    )
    db.add(job)
    db.commit()
    r = client.post(f"{ATS}/targets", json={"job_id": str(job.id)}, headers=owner["headers"])
    assert r.status_code == 201, r.text
    target = r.json()
    assert target["company_name"] == "Initrode" and target["job_id"] == str(job.id)
    assert target["latest_snapshot"]["source"] == "JOB"
    analysis = _analyse(client, owner, jd={"job_target_id": target["id"]})
    assert analysis["job_target_id"] == target["id"]
    assert client.get(f"{ATS}/targets/{target['id']}", headers=owner["headers"]).json()["last_score"] == analysis["overall_score"]


def test_tailor_and_compare(client: TestClient, owner: dict, db: Session):
    target = _target(client, owner, jd={"source": "PASTED", "text": BACKEND_JD}, source_resume_id=owner["resume_id"])
    r = client.post(f"{ATS}/targets/{target['id']}/tailor", json={}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["target"]["status"] == "READY"
    assert result["target"]["tailored_resume"]["id"] == result["resume"]["id"]
    assert result["resume"]["kind"] == "TAILORED" and result["resume"]["source_resume_id"] == owner["resume_id"]
    assert result["analysis"]["overall_score"] > result["source_score"]
    statuses = [log.meta["to"] for log in db.scalars(select(AuditLog).where(AuditLog.action == "ats.target_status_changed").order_by(AuditLog.created_at))]
    assert statuses == ["PREPARING", "READY"]

    compare = client.get(f"{ATS}/targets/{target['id']}/compare", headers=owner["headers"]).json()
    assert compare["source"]["id"] == owner["resume_id"] and compare["tailored"]["id"] == result["resume"]["id"]
    assert compare["summary"]["added"] >= 1 and compare["explanations"]
    assert any(f["path"] == "skills" and f["kind"] == "added" and "Kubernetes" in f["after"] for f in compare["fields"])
    assert compare["tailored"]["score"] > compare["source"]["score"]


def test_tailor_needs_a_job_description(client: TestClient, owner: dict):
    target = _target(client, owner)
    r = client.post(f"{ATS}/targets/{target['id']}/tailor", json={}, headers=owner["headers"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "target_has_no_jd"


def test_summary(client: TestClient, owner: dict):
    target = _target(client, owner, jd={"source": "PASTED", "text": BACKEND_JD}, source_resume_id=owner["resume_id"], follow_up_at="2099-01-01T00:00:00Z")
    _target(client, owner, company_name="Globex", role_title="Frontend Engineer", job_url=None, jd={"source": "PASTED", "text": FRONTEND_JD})
    client.post(f"{ATS}/targets/{target['id']}/tailor", json={}, headers=owner["headers"])
    summary = client.get(f"{ATS}/summary", headers=owner["headers"]).json()
    assert summary["total_targets"] == 2 and summary["targets_by_status"]["READY"] == 1 and summary["targets_by_status"]["SAVED"] == 1
    assert summary["recent_analyses"] and summary["in_progress"][0]["id"] == target["id"]


# --------------------------------------------------------------------------- ownership


def test_another_users_things_are_not_found(client: TestClient, owner: dict, db: Session):
    analysis = _analyse(client, owner)
    target = _target(client, owner, jd={"source": "PASTED", "text": BACKEND_JD})
    intruder = make_user(db, "intruder@example.com")
    db.commit()
    h = headers(intruder)
    assert client.get(f"{ATS}/analyses/{analysis['id']}", headers=h).status_code == 404
    assert client.post(f"{ATS}/analyses/{analysis['id']}/apply", json={"suggestion_ids": [analysis["suggestions"][0]["id"]]}, headers=h).status_code == 404
    assert client.post(f"{ATS}/analyses/{analysis['id']}/auto-optimize", json={}, headers=h).status_code == 404
    assert client.get(f"{ATS}/targets/{target['id']}", headers=h).status_code == 404
    assert client.patch(f"{ATS}/targets/{target['id']}", json={"status": "APPLIED"}, headers=h).status_code == 404
    assert client.delete(f"{ATS}/targets/{target['id']}", headers=h).status_code == 404
    assert client.get(f"{ATS}/targets/{target['id']}/compare", headers=h).status_code == 404
    assert client.post(f"{ATS}/analyses", json={"resume_id": owner["resume_id"], "jd": {"text": BACKEND_JD}}, headers=h).status_code == 404
    r = client.post(f"{ATS}/analyses", json={"resume_id": owner["resume_id"], "jd": {"job_target_id": target["id"]}}, headers=owner["headers"])
    assert r.status_code == 201
    snapshot_id = r.json()["snapshot_id"]
    mine = make_resume(db, intruder, name="Intruder resume")
    db.commit()
    assert client.post(f"{ATS}/analyses", json={"resume_id": str(mine.id), "jd": {"snapshot_id": snapshot_id}}, headers=h).status_code == 404
    assert client.get(f"{ATS}/targets", headers=h).json()["total"] == 0
    assert client.get(f"{ATS}/summary", headers=h).json()["total_targets"] == 0
    assert client.get(f"{ATS}/analyses", headers=h).json() == []
