"""Tests for the resumes module (CONTRACTS.md §7)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.enums import ResumeParseStatus
from app.models.resume import Resume
from app.models.user import User
from app.modules.resumes import service, storage

try:  # pytest puts ``tests/`` on sys.path; the package path is the fallback
    from helpers.documents import SAMPLE_RESUME_TEXT, build_docx, build_fake_pdf, build_oversized_pdf, build_pdf
except ImportError:  # pragma: no cover
    from tests.helpers.documents import (  # type: ignore[no-redef]
        SAMPLE_RESUME_TEXT,
        build_docx,
        build_fake_pdf,
        build_oversized_pdf,
        build_pdf,
    )

DOCX_MIME = storage.DOCX_MIME
RESUMES = "/api/v1/resumes"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Keep the shared in-memory rate-limit window from leaking between tests."""
    from app.core.rate_limit import rate_limiter

    hits = getattr(getattr(rate_limiter, "_backend", None), "_hits", None)
    if hits is not None:
        hits.clear()
    yield


def _create_user(db: Session, email: str, full_name: str = "Test User") -> User:
    """Create a user directly.

    The auth module is owned by another agent, so the resume suite mints its own
    token instead of depending on ``POST /auth/register`` being implemented yet.
    """
    user = User(
        email=email,
        hashed_password=hash_password("StrongPass123!"),
        full_name=full_name,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


@pytest.fixture
def owner(db: Session) -> User:
    return _create_user(db, "owner@example.com", "Aarav Sharma")


@pytest.fixture
def api(client: TestClient, owner: User) -> TestClient:
    client.headers.update(_auth_headers(owner))
    return client


def _upload(api: TestClient, content: bytes, filename: str, mime: str = "application/pdf", **data: object):
    return api.post(
        RESUMES,
        files={"file": (filename, content, mime)},
        data={k: str(v) for k, v in data.items()},
    )


# --------------------------------------------------------------------------- upload


def test_upload_docx_extracts_and_parses(api: TestClient) -> None:
    response = _upload(api, build_docx(), "aarav_resume.docx", DOCX_MIME, name="Backend CV", target_role="Backend Engineer")
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["name"] == "Backend CV"
    assert body["target_role"] == "Backend Engineer"
    assert body["original_filename"] == "aarav_resume.docx"
    assert body["mime_type"] == DOCX_MIME
    assert body["size_bytes"] > 0
    assert body["parse_status"] == ResumeParseStatus.PARSED.value
    assert body["parse_error"] is None
    assert body["current_version"] == 1
    assert body["is_default"] is True  # first resume becomes the default

    parsed = body["parsed_data"]
    assert parsed["name"] == "Aarav Sharma"
    assert parsed["email"] == "aarav.sharma@example.com"
    assert {"React", "Node.js", "PostgreSQL"} <= set(parsed["skills"])
    assert parsed["total_experience_years"] == pytest.approx(2.0, abs=0.6)
    assert len(parsed["experience"]) == 2
    assert parsed["links"]["github"].endswith("aaravsharma")


def test_upload_pdf_parses_the_same_way(api: TestClient) -> None:
    response = _upload(api, build_pdf(), "aarav_resume.pdf")
    assert response.status_code == 201, response.text
    parsed = response.json()["parsed_data"]

    assert {"React", "Node.js", "PostgreSQL"} <= set(parsed["skills"])
    assert parsed["total_experience_years"] == pytest.approx(2.0, abs=0.6)
    assert parsed["education"][0]["degree"].lower().startswith("b.tech")
    assert [c["name"] for c in parsed["certifications"]][0].startswith("AWS Certified")


def test_upload_requires_authentication(client: TestClient) -> None:
    client.headers.pop("Authorization", None)
    response = client.post(RESUMES, files={"file": ("cv.pdf", build_pdf(), "application/pdf")})
    assert response.status_code == 401


def test_unsupported_extension_is_rejected(api: TestClient) -> None:
    response = _upload(api, b"just some text", "resume.txt", "text/plain")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_wrong_magic_bytes_are_rejected(api: TestClient) -> None:
    response = _upload(api, build_fake_pdf(), "resume.pdf")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_pdf"


def test_oversized_upload_is_rejected(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    response = _upload(api, build_oversized_pdf(1024 * 1024 + 2048), "big.pdf")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "file_too_large"


def test_unreadable_document_still_uploads_as_failed(api: TestClient) -> None:
    response = _upload(api, build_pdf("hi"), "empty.pdf")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["parse_status"] == ResumeParseStatus.FAILED.value
    assert body["parse_error"]
    assert body["parsed_data"] == {}


# --------------------------------------------------------------------------- listing / default


def test_default_flag_moves_to_the_selected_resume(api: TestClient) -> None:
    first = _upload(api, build_docx(), "first.docx", DOCX_MIME).json()
    second = _upload(api, build_pdf(), "second.pdf").json()
    assert first["is_default"] is True
    assert second["is_default"] is False

    patched = api.patch(f"{RESUMES}/{second['id']}", json={"is_default": True})
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_default"] is True

    listed = {item["id"]: item for item in api.get(RESUMES).json()}
    assert listed[first["id"]]["is_default"] is False
    assert listed[second["id"]]["is_default"] is True


def test_set_default_on_upload(api: TestClient) -> None:
    first = _upload(api, build_docx(), "first.docx", DOCX_MIME).json()
    second = _upload(api, build_pdf(), "second.pdf", set_default=True).json()
    assert second["is_default"] is True
    assert api.get(f"{RESUMES}/{first['id']}").json()["is_default"] is False


def test_rename_and_retarget(api: TestClient) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf").json()
    response = api.patch(f"{RESUMES}/{resume['id']}", json={"name": "Renamed CV", "target_role": "Full Stack Developer"})
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Renamed CV"
    assert response.json()["target_role"] == "Full Stack Developer"


def test_get_unknown_resume_is_404(api: TestClient) -> None:
    assert api.get(f"{RESUMES}/{uuid.uuid4()}").status_code == 404


# --------------------------------------------------------------------------- parsed data / versions


def test_editing_parsed_data_creates_a_version(api: TestClient) -> None:
    resume = _upload(api, build_docx(), "cv.docx", DOCX_MIME).json()
    edited = dict(resume["parsed_data"])
    edited["name"] = "Aarav S."
    edited["skills"] = ["React", "Node.js", "PostgreSQL", "Kubernetes"]

    response = api.put(f"{RESUMES}/{resume['id']}/parsed-data", json=edited)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_version"] == 2
    assert body["parsed_data"]["name"] == "Aarav S."
    assert "Kubernetes" in body["parsed_data"]["skills"]

    versions = api.get(f"{RESUMES}/{resume['id']}/versions").json()
    assert [v["version_number"] for v in versions] == [2, 1]
    assert versions[0]["note"] == "Edited by user"


def test_parsed_data_rejects_a_bad_shape(api: TestClient) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf").json()
    response = api.put(f"{RESUMES}/{resume['id']}/parsed-data", json={"skills": "React"})
    assert response.status_code == 422


def test_reparse_reruns_extraction(api: TestClient) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf").json()
    api.put(f"{RESUMES}/{resume['id']}/parsed-data", json={"name": "Wiped", "skills": []})

    response = api.post(f"{RESUMES}/{resume['id']}/reparse")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parse_status"] == ResumeParseStatus.PARSED.value
    assert {"React", "Node.js", "PostgreSQL"} <= set(body["parsed_data"]["skills"])


def test_reparse_saves_a_new_version_so_edits_can_be_restored(api: TestClient) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf").json()
    edited = api.put(f"{RESUMES}/{resume['id']}/parsed-data", json={"name": "Edited", "skills": ["React"]}).json()
    assert edited["current_version"] == 2

    body = api.post(f"{RESUMES}/{resume['id']}/reparse").json()
    assert body["current_version"] == 3
    versions = api.get(f"{RESUMES}/{resume['id']}/versions").json()
    by_number = {v["version_number"]: v for v in versions}
    assert by_number[3]["note"] == "Re-parsed from the uploaded file"
    assert by_number[2]["parsed_data"]["name"] == "Edited"  # the edit is still restorable

    again = api.post(f"{RESUMES}/{resume['id']}/reparse").json()
    assert again["current_version"] == 3  # an unchanged re-parse adds no version


def test_reparse_keeps_skills_the_user_added(api: TestClient) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf").json()
    skills = list(resume["parsed_data"]["skills"]) + ["Kubernetes", "Linux"]
    api.put(f"{RESUMES}/{resume['id']}/parsed-data", json={**resume["parsed_data"], "skills": skills})

    body = api.post(f"{RESUMES}/{resume['id']}/reparse").json()
    assert {"Kubernetes", "Linux"} <= set(body["parsed_data"]["skills"])
    assert {"React", "Node.js", "PostgreSQL"} <= set(body["parsed_data"]["skills"])


# --------------------------------------------------------------------------- download / delete


def test_download_streams_the_original_file(api: TestClient) -> None:
    content = build_pdf()
    resume = _upload(api, content, "aarav_resume.pdf").json()

    response = api.get(f"{RESUMES}/{resume['id']}/download")
    assert response.status_code == 200
    assert response.content == content
    assert "aarav_resume.pdf" in response.headers["content-disposition"]


def test_download_is_owner_only(api: TestClient, client: TestClient, db: Session) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf").json()
    other = _create_user(db, "intruder@example.com", "Other User")

    client.headers.update(_auth_headers(other))
    assert client.get(f"{RESUMES}/{resume['id']}/download").status_code == 404
    assert client.get(f"{RESUMES}/{resume['id']}").status_code == 404
    assert client.get(RESUMES).json() == []


def test_delete_tombstones_the_row_keeps_the_file_and_promotes_a_new_default(api: TestClient, db: Session) -> None:
    """Deleting a resume is a soft delete, and the uploaded bytes stay on disk.

    A soft delete that threw the file away would be reversible in name only, so the row
    is tombstoned and the file is left for a separate storage sweep.
    """
    first = _upload(api, build_docx(), "first.docx", DOCX_MIME).json()
    second = _upload(api, build_pdf(), "second.pdf").json()
    stored_path = db.get(Resume, uuid.UUID(first["id"])).file_path
    assert storage.file_exists(stored_path)

    response = api.delete(f"{RESUMES}/{first['id']}")
    assert response.status_code == 204
    assert storage.file_exists(stored_path)

    db.expunge_all()
    assert db.get(Resume, uuid.UUID(first["id"])) is None
    tombstoned = db.get(Resume, uuid.UUID(first["id"]), execution_options={"include_deleted": True})
    assert tombstoned.deleted_at is not None and tombstoned.is_active is False

    remaining = api.get(RESUMES).json()
    assert [r["id"] for r in remaining] == [second["id"]]
    assert remaining[0]["is_default"] is True


def test_delete_unknown_resume_is_404(api: TestClient) -> None:
    assert api.delete(f"{RESUMES}/{uuid.uuid4()}").status_code == 404


# --------------------------------------------------------------------------- service layer


def test_create_resume_from_bytes_and_get_default(db: Session) -> None:
    user = _create_user(db, "service@example.com")
    assert service.get_default_resume(db, user.id) is None

    first = service.create_resume_from_bytes(db, user.id, "one.pdf", build_pdf(), name="One")
    db.commit()
    assert first.is_default is True
    assert service.get_default_resume(db, user.id).id == first.id

    second = service.create_resume_from_bytes(db, user.id, "two.docx", build_docx(), set_default=True)
    db.commit()
    assert second.is_default is True
    db.refresh(first)
    assert first.is_default is False
    assert {r.id for r in service.list_resumes(db, user.id)} == {first.id, second.id}


def test_get_resume_is_scoped_to_the_owner(db: Session) -> None:
    owner = _create_user(db, "a@example.com")
    stranger = _create_user(db, "b@example.com")
    resume = service.create_resume_from_bytes(db, owner.id, "cv.pdf", build_pdf())
    db.commit()

    from app.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        service.get_resume(db, stranger.id, resume.id)


def test_storage_layout_is_per_user(db: Session) -> None:
    user = _create_user(db, "layout@example.com")
    resume = service.create_resume_from_bytes(db, user.id, "cv.pdf", build_pdf())
    db.commit()
    assert str(storage.resume_dir(user.id)) in resume.file_path
    assert resume.sha256 == storage.sha256_bytes(build_pdf())


def test_sample_fixture_text_is_what_we_think_it_is() -> None:
    assert "Work Experience" in SAMPLE_RESUME_TEXT
    assert "PostgreSQL" in SAMPLE_RESUME_TEXT


# --------------------------------------------------------------------------- built from structured data


def test_create_resume_from_parsed_has_no_file_and_renders_text(db: Session, owner: User) -> None:
    from app.models.enums import ResumeChangeSource, ResumeKind
    from app.modules.ai.schemas import ExperienceEntry, ParsedResume

    parsed = ParsedResume(
        name="Aarav Sharma",
        email="aarav@example.com",
        summary="Backend developer with five years of Python.",
        skills=["Python", "FastAPI"],
        experience=[ExperienceEntry(company="Acme", title="Developer", start="2020", end="2024", description="Built billing APIs.")],
    )
    resume = service.create_resume_from_parsed(db, owner.id, parsed, name="Built resume", target_role="Python Developer")
    db.flush()

    assert resume.kind == ResumeKind.CREATED
    assert resume.file_path is None and resume.original_filename is None and resume.size_bytes is None
    assert resume.parse_status == ResumeParseStatus.PARSED
    assert resume.is_default is True  # first resume of the user
    assert "FastAPI" in (resume.text_content or "") and "Built billing APIs." in (resume.text_content or "")
    versions = service.list_versions(db, owner.id, resume.id)
    assert [v.version_number for v in versions] == [1]
    assert versions[0].change_source == ResumeChangeSource.USER and versions[0].file_path is None

    read = service.resume_to_read(resume)
    assert read.has_file is False and read.kind == ResumeKind.CREATED and read.template == "classic"


def test_tailored_resume_must_point_at_the_users_own_source(db: Session, owner: User) -> None:
    from app.core.exceptions import NotFoundError
    from app.models.enums import ResumeChangeSource, ResumeKind
    from app.modules.ai.schemas import ParsedResume

    source = service.create_resume_from_parsed(db, owner.id, ParsedResume(name="Aarav", skills=["Python"]), name="Source")
    tailored = service.create_resume_from_parsed(
        db,
        owner.id,
        ParsedResume(name="Aarav", skills=["Python", "Django"]),
        name="Source - Acme",
        kind=ResumeKind.TAILORED,
        source_resume_id=source.id,
        note="Tailored for Acme",
        change_source=ResumeChangeSource.AI,
    )
    db.flush()
    assert tailored.source_resume_id == source.id and tailored.source_resume.id == source.id
    assert service.list_versions(db, owner.id, tailored.id)[0].change_source == ResumeChangeSource.AI

    other = _create_user(db, "other@example.com")
    with pytest.raises(NotFoundError):
        service.create_resume_from_parsed(
            db, other.id, ParsedResume(name="X"), name="Steal", kind=ResumeKind.TAILORED, source_resume_id=source.id
        )
