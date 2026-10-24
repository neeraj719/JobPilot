"""Resume studio (builder): templates, rendering, create/import, drafts, versions, AI help.

Runs with ``LLM_PROVIDER=mock``: every AI helper answers from its rules, and model output
is simulated by monkeypatching the ``ai.tasks`` writing functions.
"""
from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import ResumeKind
from app.models.profile import JobPreference, UserProfile
from app.models.user import User
from app.modules.ai import tasks as ai_tasks
from app.modules.ai.resume_parser import parse_resume_text
from app.modules.resumes import diff as diff_mod
from app.modules.resumes import importers, render, service, storage, templates
from app.modules.resumes.extraction import extract_text

try:  # pytest puts ``tests/`` on sys.path; the package path is the fallback
    from helpers.documents import SAMPLE_RESUME_TEXT, build_pdf
except ImportError:  # pragma: no cover
    from tests.helpers.documents import SAMPLE_RESUME_TEXT, build_pdf  # type: ignore[no-redef]

RESUMES = "/api/v1/resumes"


# --------------------------------------------------------------------------- fixtures


def _create_user(db: Session, email: str, full_name: str = "Test User") -> User:
    user = User(email=email, hashed_password=hash_password("StrongPass123!"), full_name=full_name, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


@pytest.fixture
def owner(db: Session) -> User:
    return _create_user(db, "builder.owner@example.com", "Aarav Sharma")


@pytest.fixture
def intruder(db: Session) -> User:
    return _create_user(db, "builder.intruder@example.com", "Other Person")


@pytest.fixture
def api(client: TestClient, owner: User) -> TestClient:
    client.headers.update(_headers(owner))
    return client


SAMPLE = {
    "name": "Aarav Sharma",
    "email": "aarav.sharma@example.com",
    "phone": "+91 98765 43210",
    "headline": "Full Stack Developer",
    "location": "Bangalore, India",
    "summary": "Full Stack Developer with 2 years of experience building React and Node.js products.",
    "skills": ["React", "Node.js", "PostgreSQL", "Docker", "TypeScript"],
    "experience": [
        {
            "company": "Northwind Labs",
            "title": "Software Engineer",
            "start": "2023-03",
            "end": "Present",
            "location": "Bangalore, India",
            "description": "Built a React and TypeScript dashboard used by 4,000 internal users.\nWorked on payment APIs in Node.js",
            "technologies": ["React", "TypeScript", "Node.js"],
        },
        {
            "company": "Acme Cloud",
            "title": "Junior Software Engineer",
            "start": "2021-07",
            "end": "2023-02",
            "description": "Maintained Express.js microservices and MongoDB data pipelines.",
        },
    ],
    "education": [{"institution": "VIT University", "degree": "B.Tech", "field": "Computer Science", "start": "2017", "end": "2021"}],
    "projects": [{"name": "JobTracker", "description": "Tracks job applications end to end.", "technologies": ["FastAPI"]}],
    "certifications": [{"name": "AWS Certified Developer - Associate", "issuer": "Amazon Web Services", "year": "2023"}],
    "achievements": ["Won the internal hackathon"],
    "languages": ["English", "Hindi"],
    "links": {"linkedin": "https://www.linkedin.com/in/aaravsharma", "github": "https://github.com/aaravsharma"},
}


def _build(api: TestClient, name: str = "Built CV", data: dict | None = None, **extra) -> dict:
    response = api.post(f"{RESUMES}/build", json={"name": name, "parsed_data": data or SAMPLE, **extra})
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- templates + rendering


def test_templates_endpoint_lists_three_ats_templates(api: TestClient) -> None:
    response = api.get(f"{RESUMES}/templates")
    assert response.status_code == 200, response.text
    ids = [t["id"] for t in response.json()]
    assert ids == ["classic", "modern", "compact"]
    for tpl in response.json():
        assert tpl["fonts"]["pdf"] in {"Times-Roman", "Helvetica"}
        assert set(tpl["section_order"]) == set(templates.SECTION_LABELS)


@pytest.mark.parametrize("template_id", ["classic", "modern", "compact"])
@pytest.mark.parametrize("fmt", ["pdf", "docx"])
def test_exports_round_trip_through_extraction_and_the_parser(template_id: str, fmt: str) -> None:
    content, mime = render.render(SAMPLE, fmt, template_id)
    assert mime in (render.PDF_MIME, render.DOCX_MIME)
    text = extract_text(content, fmt)
    back = parse_resume_text(text)
    assert back["name"] == "Aarav Sharma"
    assert back["email"] == "aarav.sharma@example.com"
    assert {"React", "Node.js", "PostgreSQL", "Docker"} <= set(back["skills"])
    jobs = [(e["title"], e["company"]) for e in back["experience"]]
    assert ("Software Engineer", "Northwind Labs") in jobs
    assert ("Junior Software Engineer", "Acme Cloud") in jobs
    first = next(e for e in back["experience"] if e["company"] == "Northwind Labs")
    assert first["start"] == "2023-03" and first["end"] == "Present"
    # Bullets stay list items (the extractor marks them), and every heading is a real one.
    assert "- Built a React and TypeScript dashboard" in text
    for heading in ("Summary", "Skills", "Experience", "Education", "Projects", "Certifications"):
        assert heading.lower() in text.lower()


def test_uploaded_resume_round_trip_keeps_the_sample_facts() -> None:
    parsed = parse_resume_text(SAMPLE_RESUME_TEXT)
    for fmt in ("pdf", "docx"):
        back = parse_resume_text(extract_text(render.render(parsed, fmt, "classic")[0], fmt))
        assert back["name"] == parsed["name"]
        assert set(parsed["skills"]) <= set(back["skills"])
        assert [(e["title"], e["company"]) for e in back["experience"]] == [
            (e["title"], e["company"]) for e in parsed["experience"]
        ]


def test_layout_follows_the_resume_section_order_and_skips_empty_sections() -> None:
    data = {**SAMPLE, "section_order": ["experience", "skills"], "summary": None}
    layout = render.build_layout(data, "classic")
    assert [s.key for s in layout.sections] == ["experience", "skills"]
    assert render.format_date("2023-03", "MM/YYYY") == "03/2023"
    assert render.format_date("present") == "Present"
    assert render.format_date("Summer 2020") == "Summer 2020"


# --------------------------------------------------------------------------- build + export


def test_build_creates_a_created_resume_and_exports_both_formats(api: TestClient) -> None:
    body = _build(api, template="modern", target_role="Full Stack Developer")
    assert body["kind"] == "CREATED"
    assert body["template"] == "modern"
    assert body["has_file"] is False
    assert body["current_version"] == 1
    assert body["is_default"] is True
    assert body["parsed_data"]["headline"] == "Full Stack Developer"
    assert body["parsed_data"]["achievements"] == ["Won the internal hackathon"]

    pdf = api.get(f"{RESUMES}/{body['id']}/export", params={"format": "pdf"})
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert 'filename="Built CV.pdf"' in pdf.headers["content-disposition"]
    assert pdf.content.startswith(b"%PDF")
    assert "Northwind Labs" in extract_text(pdf.content, "pdf")

    docx = api.get(f"{RESUMES}/{body['id']}/export", params={"format": "docx", "template": "compact"})
    assert docx.status_code == 200
    assert docx.headers["content-type"].startswith(storage.DOCX_MIME)
    assert "Northwind Labs" in extract_text(docx.content, "docx")

    # No uploaded file: "download" renders the DOCX instead of a 404.
    download = api.get(f"{RESUMES}/{body['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith(storage.DOCX_MIME)

    bad = api.get(f"{RESUMES}/{body['id']}/export", params={"format": "txt"})
    assert bad.status_code == 422


def test_export_of_an_old_version_and_of_an_upload(api: TestClient) -> None:
    body = _build(api)
    edited = {**SAMPLE, "name": "Aarav K Sharma"}
    assert api.put(f"{RESUMES}/{body['id']}/parsed-data", json=edited).status_code == 200
    v1 = api.get(f"{RESUMES}/{body['id']}/export", params={"format": "docx", "version": 1})
    assert "Aarav Sharma" in extract_text(v1.content, "docx")
    assert 'v1.docx' in v1.headers["content-disposition"]
    assert api.get(f"{RESUMES}/{body['id']}/export", params={"version": 9}).status_code == 404

    upload = api.post(RESUMES, files={"file": ("cv.pdf", build_pdf(), "application/pdf")})
    assert upload.status_code == 201
    exported = api.get(f"{RESUMES}/{upload.json()['id']}/export", params={"format": "pdf"})
    assert exported.status_code == 200
    assert "Northwind Labs" in extract_text(exported.content, "pdf")


def test_patch_template_and_unknown_template(api: TestClient) -> None:
    body = _build(api)
    ok = api.patch(f"{RESUMES}/{body['id']}", json={"template": "compact"})
    assert ok.status_code == 200 and ok.json()["template"] == "compact"
    bad = api.patch(f"{RESUMES}/{body['id']}", json={"template": "fancy-two-column"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "unknown_template"


# --------------------------------------------------------------------------- prefill + imports


def test_prefill_uses_only_profile_facts(api: TestClient, db: Session, owner: User) -> None:
    assert api.get(f"{RESUMES}/prefill").json()["name"] is None  # no profile yet: empty, nothing invented
    db.add(
        UserProfile(
            user_id=owner.id,
            full_name="Aarav Sharma",
            email="aarav@example.com",
            city="Pune",
            country="India",
            current_company="Northwind Labs",
            current_designation="Software Engineer",
            previous_companies=[{"company": "Acme Cloud", "title": "Junior Engineer", "start": "2021-07", "end": "2023-02"}],
            education=[{"institution": "VIT University", "degree": "B.Tech", "field": "CSE"}],
            skills=["React", "Python"],
            technologies=["Docker", "react"],
            projects=[{"name": "JobTracker", "description": "Tracks applications", "tech": ["FastAPI"]}],
            achievements=["Hackathon winner"],
            languages=["English"],
            years_of_experience=3,
            linkedin_url="https://linkedin.com/in/aarav",
        )
    )
    db.add(JobPreference(user_id=owner.id, desired_titles=["Backend Engineer"]))
    db.commit()
    data = api.get(f"{RESUMES}/prefill").json()
    assert data["name"] == "Aarav Sharma"
    assert data["location"] == "Pune, India"
    assert data["headline"] == "Backend Engineer"
    assert data["skills"] == ["React", "Python", "Docker"]
    assert data["experience"][0] == {
        "company": "Northwind Labs", "title": "Software Engineer", "start": None, "end": "Present",
        "description": None, "technologies": [], "location": None, "url": None,
    }
    assert data["experience"][1]["company"] == "Acme Cloud"
    assert data["projects"][0]["technologies"] == ["FastAPI"]
    assert data["achievements"] == ["Hackathon winner"]
    assert data["total_experience_years"] == 3


def test_import_text_parses_and_keeps_the_pasted_text(api: TestClient, db: Session) -> None:
    response = api.post(f"{RESUMES}/import/text", json={"text": SAMPLE_RESUME_TEXT, "target_role": "Backend Engineer"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "CREATED"
    assert body["name"] == "Aarav Sharma - resume"
    assert body["parsed_data"]["email"] == "aarav.sharma@example.com"
    assert len(body["parsed_data"]["experience"]) == 2
    versions = api.get(f"{RESUMES}/{body['id']}/versions").json()
    assert versions[0]["note"] == "Imported from pasted text"
    assert versions[0]["change_source"] == "SYSTEM"

    short = api.post(f"{RESUMES}/import/text", json={"text": "too short"})
    assert short.status_code == 422


def _csv(header: str, *rows: str) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


LINKEDIN = {
    "Profile.csv": _csv(
        "First Name,Last Name,Maiden Name,Address,Birth Date,Headline,Summary,Industry,Zip Code,Geo Location,Twitter Handles,Websites,Instant Messengers",
        'Aarav,Sharma,,,,Full Stack Developer,"I build React and Node.js products.",Software,,"Bengaluru, Karnataka, India",,"[PORTFOLIO:https://aarav.dev,OTHER:https://github.com/aaravsharma]",',
    ),
    "Positions.csv": _csv(
        "Company Name,Title,Description,Location,Started On,Finished On",
        'Northwind Labs,Software Engineer,"Built a React dashboard.","Bengaluru, India",Mar 2023,',
        "Acme Cloud,Junior Software Engineer,Maintained Express.js services.,Pune,Jul 2021,Feb 2023",
    ),
    "Education.csv": _csv("School Name,Start Date,End Date,Notes,Degree Name,Activities", "VIT University,2017,2021,,B.Tech,"),
    "Skills.csv": _csv("Name", "React", "Node.js", "ReactJS"),
    "Certifications.csv": _csv(
        "Name,Url,Authority,Started On,Finished On,License Number", "AWS Certified Developer,,Amazon Web Services,Jan 2023,,"
    ),
    "Projects.csv": _csv("Title,Description,Url,Started On,Finished On", "JobTracker,Tracks job applications.,https://jt.dev,,"),
    "Languages.csv": _csv("Name,Proficiency", "English,Native or bilingual proficiency", "Hindi,"),
    "Email Addresses.csv": _csv("Email Address,Confirmed,Primary,Updated On", "old@example.com,Yes,No,", "aarav@example.com,Yes,Yes,"),
}


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_import_linkedin_zip_maps_the_real_export_columns(api: TestClient) -> None:
    response = api.post(
        f"{RESUMES}/import/linkedin",
        files=[("files", ("Basic_LinkedInDataExport.zip", _zip(LINKEDIN), "application/zip"))],
        data={"target_role": "Full Stack Developer"},
    )
    assert response.status_code == 201, response.text
    parsed = response.json()["parsed_data"]
    assert parsed["name"] == "Aarav Sharma"
    assert parsed["headline"] == "Full Stack Developer"
    assert parsed["email"] == "aarav@example.com"
    assert parsed["location"] == "Bengaluru, Karnataka, India"
    assert parsed["links"]["portfolio"] == "https://aarav.dev"
    assert parsed["links"]["github"] == "https://github.com/aaravsharma"
    assert parsed["experience"][0] == {
        "company": "Northwind Labs", "title": "Software Engineer", "start": "2023-03", "end": "Present",
        "description": "Built a React dashboard.", "technologies": [], "location": "Bengaluru, India", "url": None,
    }
    assert parsed["experience"][1]["end"] == "2023-02"
    assert parsed["skills"] == ["React", "Node.js"]  # "ReactJS" is the same skill
    assert parsed["certifications"][0] == {"name": "AWS Certified Developer", "issuer": "Amazon Web Services", "year": "2023"}
    assert parsed["languages"] == ["English (Native or bilingual proficiency)", "Hindi"]
    assert parsed["projects"][0]["url"] == "https://jt.dev"
    assert response.json()["kind"] == "CREATED"


def test_import_linkedin_individual_csvs_and_bad_input(api: TestClient) -> None:
    ok = api.post(
        f"{RESUMES}/import/linkedin",
        files=[
            ("files", ("Profile.csv", LINKEDIN["Profile.csv"], "text/csv")),
            ("files", ("Positions.csv", LINKEDIN["Positions.csv"], "text/csv")),
        ],
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["parsed_data"]["experience"][0]["company"] == "Northwind Labs"

    other = api.post(f"{RESUMES}/import/linkedin", files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert other.status_code == 422 and other.json()["error"]["code"] == "unsupported_file_type"

    empty = api.post(f"{RESUMES}/import/linkedin", files=[("files", ("x.zip", _zip({"Skills.csv": LINKEDIN["Skills.csv"]}), "application/zip"))])
    assert empty.status_code == 422 and empty.json()["error"]["code"] == "linkedin_data_missing"

    broken = api.post(f"{RESUMES}/import/linkedin", files=[("files", ("x.zip", b"PK\x03\x04garbage", "application/zip"))])
    assert broken.status_code == 422 and broken.json()["error"]["code"] == "invalid_zip"


def test_linkedin_zip_slip_members_are_ignored_and_nothing_is_written(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    evil = _zip(
        {
            "../../Profile.csv": _csv("First Name,Last Name,Headline", "Evil,Person,Hacker"),
            "/abs/Positions.csv": _csv("Company Name,Title", "Evil Corp,Owner"),
            "export/Positions.csv": LINKEDIN["Positions.csv"],
        }
    )
    members = importers.linkedin_members([("export.zip", evil)])
    assert set(members) == {"positions.csv"}
    assert b"Northwind" in members["positions.csv"]
    assert list(tmp_path.iterdir()) == []  # nothing extracted anywhere


def test_linkedin_member_size_is_capped(monkeypatch) -> None:
    monkeypatch.setattr(importers, "MAX_MEMBER_BYTES", 1000)
    big = _zip({"Positions.csv": _csv("Company Name,Title", *[f"Company {i},Engineer" for i in range(200)])})
    with pytest.raises(Exception) as excinfo:
        importers.linkedin_members([("big.zip", big)])
    assert getattr(excinfo.value, "code", "") == "file_too_large"


# --------------------------------------------------------------------------- drafts


def test_draft_save_get_discard_and_cleared_on_save(api: TestClient) -> None:
    body = _build(api)
    rid = body["id"]
    assert api.get(f"{RESUMES}/{rid}/draft").json()["draft_data"] is None

    draft = {**SAMPLE, "summary": "Draft summary typed in the editor."}
    saved = api.put(f"{RESUMES}/{rid}/draft", json=draft)
    assert saved.status_code == 200, saved.text
    assert saved.json()["draft_data"]["summary"] == "Draft summary typed in the editor."
    assert saved.json()["draft_saved_at"] is not None
    resume = api.get(f"{RESUMES}/{rid}").json()
    assert resume["draft_saved_at"] is not None
    assert resume["current_version"] == 1  # autosave makes no version
    assert resume["parsed_data"]["summary"] == SAMPLE["summary"]

    discarded = api.delete(f"{RESUMES}/{rid}/draft")
    assert discarded.status_code == 200 and discarded.json()["draft_data"] is None

    api.put(f"{RESUMES}/{rid}/draft", json=draft)
    put = api.put(f"{RESUMES}/{rid}/parsed-data", json={**draft, "note": "Polished the summary"})
    assert put.status_code == 200
    assert put.json()["draft_saved_at"] is None
    assert put.json()["current_version"] == 2
    versions = api.get(f"{RESUMES}/{rid}/versions").json()
    assert versions[0]["note"] == "Polished the summary"
    assert versions[0]["change_source"] == "USER"


def test_parsed_data_save_accepts_ai_source_but_not_system(api: TestClient) -> None:
    rid = _build(api)["id"]
    ai = api.put(f"{RESUMES}/{rid}/parsed-data", json={**SAMPLE, "skills": ["React"], "change_source": "AI", "note": "AI rewrite"})
    assert ai.status_code == 200
    assert api.get(f"{RESUMES}/{rid}/versions").json()[0]["change_source"] == "AI"
    system = api.put(f"{RESUMES}/{rid}/parsed-data", json={**SAMPLE, "change_source": "SYSTEM"})
    assert system.status_code == 422
    # A bare ParsedResume (older clients) still works.
    assert api.put(f"{RESUMES}/{rid}/parsed-data", json=SAMPLE).status_code == 200


# --------------------------------------------------------------------------- duplicate + archive


def test_duplicate_keeps_kind_links_source_and_starts_at_v1(api: TestClient) -> None:
    source = _build(api, template="modern", target_role="Backend Engineer")
    api.put(f"{RESUMES}/{source['id']}/parsed-data", json={**SAMPLE, "summary": "Second version."})
    copy = api.post(f"{RESUMES}/{source['id']}/duplicate", json={})
    assert copy.status_code == 201, copy.text
    body = copy.json()
    assert body["name"] == "Built CV (copy)"
    assert body["kind"] == "CREATED"
    assert body["source_resume_id"] == source["id"]
    assert body["template"] == "modern"
    assert body["target_role"] == "Backend Engineer"
    assert body["is_default"] is False
    assert body["current_version"] == 1
    assert body["parsed_data"]["summary"] == "Second version."
    version = api.get(f"{RESUMES}/{body['id']}/versions").json()[0]
    assert version["note"] == "Duplicated from Built CV v2"
    assert version["change_source"] == "SYSTEM"

    named = api.post(f"{RESUMES}/{source['id']}/duplicate", json={"name": "React CV"})
    assert named.json()["name"] == "React CV"

    upload = api.post(RESUMES, files={"file": ("cv.pdf", build_pdf(), "application/pdf")}).json()
    up_copy = api.post(f"{RESUMES}/{upload['id']}/duplicate").json()
    assert up_copy["kind"] == "UPLOADED" and up_copy["has_file"] is True
    assert api.post(f"{RESUMES}/{up_copy['id']}/reparse").status_code == 200


def test_archive_hides_from_list_and_default_and_restore(api: TestClient, db: Session, owner: User) -> None:
    first = _build(api, name="First")
    second = _build(api, name="Second")
    assert first["is_default"] is True and second["is_default"] is False

    archived = api.post(f"{RESUMES}/{first['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert archived.json()["is_default"] is False

    listed = [r["id"] for r in api.get(RESUMES).json()]
    assert listed == [second["id"]]
    everything = {r["id"] for r in api.get(RESUMES, params={"include_archived": True}).json()}
    assert everything == {first["id"], second["id"]}
    assert api.get(f"{RESUMES}/{second['id']}").json()["is_default"] is True  # promoted
    assert service.get_default_resume(db, owner.id).id.hex == second["id"].replace("-", "")

    refused = api.patch(f"{RESUMES}/{first['id']}", json={"is_default": True})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "archived_resume"

    # Only archived resumes left: nothing is picked as the default for matching/automation.
    api.post(f"{RESUMES}/{second['id']}/archive")
    db.expire_all()
    assert service.get_default_resume(db, owner.id) is None

    restored = api.post(f"{RESUMES}/{first['id']}/unarchive")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert restored.json()["is_default"] is True  # no other default existed


# --------------------------------------------------------------------------- versions, diff, restore, history


def test_version_diff_shape_and_restore_makes_a_new_version(api: TestClient) -> None:
    rid = _build(api)["id"]
    edited = {
        **SAMPLE,
        "skills": ["React", "Node.js", "PostgreSQL", "Docker", "Kubernetes", "AWS"],
        "experience": [
            {**SAMPLE["experience"][0], "description": "Built a React and TypeScript dashboard used by 4,000 internal users.\nDeveloped payment APIs in Node.js."},
            SAMPLE["experience"][1],
        ],
        "summary": "A different summary.",
    }
    api.put(f"{RESUMES}/{rid}/parsed-data", json=edited)

    one = api.get(f"{RESUMES}/{rid}/versions/1")
    assert one.status_code == 200 and one.json()["version_number"] == 1
    assert api.get(f"{RESUMES}/{rid}/versions/7").status_code == 404

    diff = api.get(f"{RESUMES}/{rid}/versions/2/diff", params={"against": 1})
    assert diff.status_code == 200, diff.text
    body = diff.json()
    assert set(body) >= {"fields", "summary"}
    kinds = {(f["path"], f["kind"], f["before"], f["after"]) for f in body["fields"]}
    assert ("skills", "added", None, "Kubernetes") in kinds
    assert ("skills", "added", None, "AWS") in kinds
    assert ("skills", "removed", "TypeScript", None) in kinds
    assert ("experience[0].bullets[1]", "changed", "Worked on payment APIs in Node.js", "Developed payment APIs in Node.js.") in kinds
    assert ("summary", "changed", SAMPLE["summary"], "A different summary.") in kinds
    assert body["summary"] == {"added": 2, "removed": 1, "changed": 2}
    assert body["description"].startswith("+2 skills, -1 skill")
    assert "1 bullet changed" in body["description"]
    # Default base is the previous version.
    assert api.get(f"{RESUMES}/{rid}/versions/2/diff").json()["summary"] == body["summary"]

    restored = api.post(f"{RESUMES}/{rid}/versions/1/restore")
    assert restored.status_code == 200
    assert restored.json()["current_version"] == 3
    assert restored.json()["parsed_data"]["skills"] == SAMPLE["skills"]
    latest = api.get(f"{RESUMES}/{rid}/versions").json()[0]
    assert latest["note"] == "Restored from v1" and latest["change_source"] == "SYSTEM"


def test_diff_against_another_resume_and_entry_matching() -> None:
    before = {**SAMPLE}
    after = {**SAMPLE, "experience": [SAMPLE["experience"][1], {**SAMPLE["experience"][0], "title": "Senior Software Engineer"}]}
    result = diff_mod.diff_parsed(before, after)
    paths = {(f.path, f.kind) for f in result.fields}
    assert ("experience[1].title", "changed") in paths  # matched by company, not position
    assert not any(f.kind == "added" and f.path.startswith("experience[") and f.path.count(".") == 0 for f in result.fields)
    assert diff_mod.diff_parsed(SAMPLE, SAMPLE).summary.model_dump() == {"added": 0, "removed": 0, "changed": 0}
    assert diff_mod.diff_parsed(SAMPLE, SAMPLE).description == "No content changes"


def test_resume_vs_resume_diff_endpoint(api: TestClient) -> None:
    source = _build(api, name="Source")
    copy = api.post(f"{RESUMES}/{source['id']}/duplicate").json()
    api.put(f"{RESUMES}/{copy['id']}/parsed-data", json={**SAMPLE, "skills": [*SAMPLE["skills"], "GraphQL"]})
    diff = api.get(f"{RESUMES}/{copy['id']}/diff", params={"against": source["id"]})
    assert diff.status_code == 200
    assert diff.json()["fields"] == [{"path": "skills", "label": "Skills", "before": None, "after": "GraphQL", "kind": "added"}]


def test_history_lists_versions_across_resumes_with_filters_and_cursor(api: TestClient) -> None:
    a = _build(api, name="Alpha")
    b = _build(api, name="Beta")
    api.put(f"{RESUMES}/{a['id']}/parsed-data", json={**SAMPLE, "skills": [*SAMPLE["skills"], "Go", "Rust"]})
    api.put(f"{RESUMES}/{a['id']}/parsed-data", json={**SAMPLE, "change_source": "AI", "note": "AI tailoring"})

    page = api.get(f"{RESUMES}/history").json()
    assert [(i["resume_name"], i["version_number"]) for i in page["items"]] == [("Alpha", 3), ("Alpha", 2), ("Beta", 1), ("Alpha", 1)]
    assert page["items"][1]["change_summary"] == "+2 skills"
    assert page["items"][0]["is_current"] is True and page["items"][1]["is_current"] is False
    assert page["items"][2]["change_summary"].startswith("5 skills")

    ai_only = api.get(f"{RESUMES}/history", params={"change_source": "AI"}).json()["items"]
    assert [(i["resume_name"], i["version_number"], i["note"]) for i in ai_only] == [("Alpha", 3, "AI tailoring")]
    only_b = api.get(f"{RESUMES}/history", params={"resume_id": b["id"]}).json()["items"]
    assert [i["resume_name"] for i in only_b] == ["Beta"]

    first = api.get(f"{RESUMES}/history", params={"limit": 2}).json()
    assert len(first["items"]) == 2 and first["next_cursor"] == "2"
    second = api.get(f"{RESUMES}/history", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [i["version_number"] for i in second["items"]] == [1, 1] and second["next_cursor"] is None


def test_summary_counts(api: TestClient) -> None:
    a = _build(api, name="Alpha")
    b = _build(api, name="Beta")
    _build(api, name="Gamma")
    api.post(f"{RESUMES}/{b['id']}/archive")
    api.put(f"{RESUMES}/{a['id']}/draft", json=SAMPLE)
    api.put(f"{RESUMES}/{a['id']}/parsed-data", json={**SAMPLE, "change_source": "AI"})
    api.put(f"{RESUMES}/{a['id']}/draft", json=SAMPLE)
    body = api.get(f"{RESUMES}/summary").json()
    assert body["total"] == 2
    assert body["archived"] == 1
    assert body["by_kind"] == {"UPLOADED": 0, "CREATED": 2, "TAILORED": 0}
    assert body["drafts_pending"] == 1
    assert body["ai_versions_to_review"] == 1
    assert body["recently_edited"][0]["name"] == "Alpha"
    assert body["recently_edited"][0]["has_draft"] is True
    assert body["default_resume_id"] == a["id"]


# --------------------------------------------------------------------------- AI writing help


def test_rewrite_bullet_rule_candidates_carry_checks(api: TestClient) -> None:
    rid = _build(api)["id"]
    response = api.post(f"{RESUMES}/{rid}/ai/rewrite-bullet", json={"text": "Worked on payment APIs in Node.js"})
    assert response.status_code == 200, response.text
    body = response.json()
    texts = [c["text"] for c in body["candidates"]]
    assert texts[:3] == ["Developed payment APIs in Node.js.", "Built payment APIs in Node.js.", "Implemented payment APIs in Node.js."]
    assert all(c["source"] == "rule" for c in body["candidates"])
    assert all(c["checks"] == {"kept_details": True, "no_new_numbers": True, "no_new_claims": True} for c in body["candidates"])
    assert body["ai_used"] is False


def test_rewrite_bullet_drops_model_candidates_with_invented_facts(api: TestClient, monkeypatch) -> None:
    rid = _build(api)["id"]
    monkeypatch.setattr(
        ai_tasks,
        "rewrite_bullet_texts",
        lambda bullet, **_: [
            "Developed payment APIs in Node.js, cutting failures by 40%.",  # invented number
            "Led the team that developed payment APIs in Node.js.",  # invented claim
            "Developed payment APIs in Node.js and Kubernetes.",  # invented skill
            "Developed payment APIs in Node.js for checkout.",  # fine
        ],
    )
    body = api.post(f"{RESUMES}/{rid}/ai/rewrite-bullet", json={"text": "Worked on payment APIs in Node.js"}).json()
    texts = [c["text"] for c in body["candidates"]]
    assert "Developed payment APIs in Node.js for checkout." in texts
    assert not any("40%" in t or "Led" in t or "Kubernetes" in t for t in texts)
    assert body["candidates"][0]["source"] == "ai"
    assert body["ai_used"] is True


def test_responsibility_to_achievement_keeps_the_placeholder(api: TestClient, monkeypatch) -> None:
    rid = _build(api)["id"]
    body = api.post(f"{RESUMES}/{rid}/ai/responsibility-to-achievement", json={"text": "Responsible for the release process"}).json()
    assert body["candidates"][0]["text"] == "Owned release process, resulting in [result]."
    assert body["candidates"][0]["has_placeholder"] is True
    assert "[result]" in body["note"]

    # A model that fills in a number (or drops the placeholder) is refused.
    monkeypatch.setattr(ai_tasks, "achievement_bullet", lambda text: "Owned the release process, cutting release time by 50%.")
    again = api.post(f"{RESUMES}/{rid}/ai/responsibility-to-achievement", json={"text": "Responsible for the release process"}).json()
    assert [c["source"] for c in again["candidates"]] == ["rule"]
    assert all("50%" not in c["text"] for c in again["candidates"])

    # Input that already states a result gets no placeholder.
    stated = api.post(
        f"{RESUMES}/{rid}/ai/responsibility-to-achievement", json={"text": "Reduced build time from 20 to 5 minutes"}
    ).json()
    assert all("[" not in c["text"] for c in stated["candidates"])


def test_improve_text_fixes_grammar_and_rejects_new_facts(api: TestClient, monkeypatch) -> None:
    rid = _build(api)["id"]
    plain = api.post(
        f"{RESUMES}/{rid}/ai/improve-text", json={"text": "i built  the the dashboard ,for users", "field": "summary"}
    ).json()
    assert plain == {"text": "I built the dashboard, for users.", "changed": True, "source": "rule", "reason": None, "ai_provider": None, "ai_model": None}

    monkeypatch.setattr(ai_tasks, "improve_text", lambda text, field: "I built the dashboard for 5,000 users.")
    number = api.post(f"{RESUMES}/{rid}/ai/improve-text", json={"text": "i built the dashboard for users", "field": "summary"}).json()
    assert number["source"] == "rule" and number["reason"] == "invented_number"

    monkeypatch.setattr(ai_tasks, "improve_text", lambda text, field: "I built the dashboard for users with Kubernetes.")
    skill = api.post(f"{RESUMES}/{rid}/ai/improve-text", json={"text": "i built the dashboard for users", "field": "summary"}).json()
    assert skill["reason"] == "invented_skill"

    monkeypatch.setattr(ai_tasks, "improve_text", lambda text, field: "I built the dashboard at Google for users.")
    name = api.post(f"{RESUMES}/{rid}/ai/improve-text", json={"text": "i built the dashboard for users", "field": "summary"}).json()
    assert name["reason"] == "invented_name"

    monkeypatch.setattr(ai_tasks, "improve_text", lambda text, field: "I built the dashboard for our users.")
    good = api.post(f"{RESUMES}/{rid}/ai/improve-text", json={"text": "i built the dashboard for users", "field": "summary"}).json()
    assert {k: good[k] for k in ("text", "changed", "source", "reason")} == {
        "text": "I built the dashboard for our users.", "changed": True, "source": "ai", "reason": None
    }
    # the task is faked past the runtime and the routing is the mock: no model to name (ai-model-choice)
    assert good["ai_provider"] is None


def test_draft_summary_uses_facts_and_guards_the_polish(api: TestClient, monkeypatch) -> None:
    rid = _build(api)["id"]
    body = api.post(f"{RESUMES}/{rid}/ai/draft-summary", json={}).json()
    assert body["source"] == "rule"
    assert body["text"].startswith("Software Engineer")
    assert "Northwind Labs" in body["text"]

    monkeypatch.setattr(ai_tasks, "polish_summary", lambda summary: "Software Engineer with 9 years at Google.")
    refused = api.post(f"{RESUMES}/{rid}/ai/draft-summary").json()
    assert refused["source"] == "rule" and refused["reason"] == "invented_number"

    empty = api.post(f"{RESUMES}/{rid}/ai/draft-summary", json={"parsed_data": {"name": "Nobody"}}).json()
    assert empty == {"text": None, "source": "rule", "reason": "not_enough_facts", "ai_provider": None, "ai_model": None}


# --------------------------------------------------------------------------- ownership


def test_another_users_resume_is_404_everywhere(api: TestClient, client: TestClient, intruder: User) -> None:
    rid = _build(api)["id"]
    other = _headers(intruder)
    checks = [
        ("get", f"{RESUMES}/{rid}/draft", None),
        ("put", f"{RESUMES}/{rid}/draft", SAMPLE),
        ("delete", f"{RESUMES}/{rid}/draft", None),
        ("post", f"{RESUMES}/{rid}/duplicate", {}),
        ("post", f"{RESUMES}/{rid}/archive", None),
        ("post", f"{RESUMES}/{rid}/unarchive", None),
        ("get", f"{RESUMES}/{rid}/versions/1", None),
        ("get", f"{RESUMES}/{rid}/versions/1/diff", None),
        ("post", f"{RESUMES}/{rid}/versions/1/restore", None),
        ("get", f"{RESUMES}/{rid}/export?format=pdf", None),
        ("get", f"{RESUMES}/{rid}/download", None),
        ("post", f"{RESUMES}/{rid}/ai/rewrite-bullet", {"text": "Worked on APIs"}),
        ("post", f"{RESUMES}/{rid}/ai/improve-text", {"text": "hello there", "field": "summary"}),
        ("post", f"{RESUMES}/{rid}/ai/draft-summary", {}),
        ("post", f"{RESUMES}/{rid}/ai/responsibility-to-achievement", {"text": "Handled releases"}),
        ("get", f"{RESUMES}/history?resume_id={rid}", None),
    ]
    for method, url, payload in checks:
        kwargs = {"headers": other}
        if payload is not None:
            kwargs["json"] = payload
        response = getattr(client, method)(url, **kwargs)
        assert response.status_code == 404, (method, url, response.status_code, response.text)

    own = _build(api, name="Mine")
    cross = client.get(f"{RESUMES}/{own['id']}/diff", params={"against": rid}, headers=other)
    assert cross.status_code == 404
    assert client.get(f"{RESUMES}/history", headers=other).json()["items"] == []
    assert client.get(f"{RESUMES}/summary", headers=other).json()["total"] == 0


def test_kind_enum_values_are_stable() -> None:
    assert [k.value for k in ResumeKind] == ["UPLOADED", "CREATED", "TAILORED"]
