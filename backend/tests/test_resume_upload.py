"""Uploaded-resume endpoints (``resumes.router_upload``): inline file, file facts, replace, edit copy."""
from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import ResumeChangeSource
from app.models.resume import Resume, ResumeVersion
from app.models.user import User
from app.modules.resumes import storage

try:  # pytest puts ``tests/`` on sys.path; the package path is the fallback
    from helpers.documents import SAMPLE_RESUME_TEXT, build_docx, build_pdf
except ImportError:  # pragma: no cover
    from tests.helpers.documents import SAMPLE_RESUME_TEXT, build_docx, build_pdf  # type: ignore[no-redef]

RESUMES = "/api/v1/resumes"
DOCX_MIME = storage.DOCX_MIME


def _create_user(db: Session, email: str) -> User:
    user = User(email=email, hashed_password=hash_password("StrongPass123!"), full_name="Upload Tester", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


@pytest.fixture
def owner(db: Session) -> User:
    return _create_user(db, "upload-owner@example.com")


@pytest.fixture
def api(client: TestClient, owner: User) -> TestClient:
    client.headers.update(_headers(owner))
    return client


def _upload(api: TestClient, content: bytes, filename: str, mime: str = "application/pdf") -> dict:
    response = api.post(RESUMES, files={"file": (filename, content, mime)}, data={"name": "Original CV"})
    assert response.status_code == 201, response.text
    return response.json()


def _encrypted_pdf(password: str = "secret") -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(build_pdf())).pages:
        writer.add_page(page)
    writer.encrypt(user_password=password, owner_password="owner", algorithm="RC4-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# --------------------------------------------------------------------------- GET /{id}/file


def test_inline_file_has_inline_disposition_and_safe_headers(api: TestClient) -> None:
    pdf = build_pdf()
    resume = _upload(api, pdf, "Aarav CV.pdf")
    response = api.get(f"{RESUMES}/{resume['id']}/file")
    assert response.status_code == 200, response.text
    assert response.content == pdf
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith('inline; filename="Aarav CV.pdf"')
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in response.headers["cache-control"]


def test_attachment_disposition_on_request(api: TestClient) -> None:
    resume = _upload(api, build_docx(), "cv.docx", DOCX_MIME)
    response = api.get(f"{RESUMES}/{resume['id']}/file", params={"disposition": "attachment"})
    assert response.status_code == 200
    assert response.headers["content-type"] == DOCX_MIME
    assert response.headers["content-disposition"].startswith('attachment; filename="cv.docx"')


def test_bad_disposition_is_422(api: TestClient) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf")
    assert api.get(f"{RESUMES}/{resume['id']}/file", params={"disposition": "../../etc"}).status_code == 422


def test_built_resume_has_no_file(api: TestClient) -> None:
    built = api.post(f"{RESUMES}/build", json={"name": "Built", "parsed_data": {"name": "A"}})
    assert built.status_code == 201, built.text
    response = api.get(f"{RESUMES}/{built.json()['id']}/file")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_file"


def test_file_outside_upload_root_is_refused(api: TestClient, db: Session, tmp_path) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf")
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(build_pdf())
    row = db.get(Resume, uuid.UUID(resume["id"]))
    row.file_path = str(outside)
    db.commit()
    response = api.get(f"{RESUMES}/{resume['id']}/file")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "file_missing"


# --------------------------------------------------------------------------- ownership


def test_other_users_get_404_everywhere(api: TestClient, client: TestClient, db: Session) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf")
    intruder = _create_user(db, "intruder@example.com")
    client.headers.update(_headers(intruder))
    rid = resume["id"]
    assert client.get(f"{RESUMES}/{rid}/file").status_code == 404
    assert client.get(f"{RESUMES}/{rid}/file-info").status_code == 404
    assert client.post(f"{RESUMES}/{rid}/file", files={"file": ("n.pdf", build_pdf("Other text " * 20), "application/pdf")}).status_code == 404
    assert client.post(f"{RESUMES}/{rid}/edit-copy", json={}).status_code == 404
    assert client.get(f"{RESUMES}/{uuid.uuid4()}/file-info").status_code == 404


# --------------------------------------------------------------------------- file-info


def test_file_info_for_pdf(api: TestClient) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf")
    info = api.get(f"{RESUMES}/{resume['id']}/file-info").json()
    assert info["has_file"] is True
    assert info["format"] == "pdf"
    assert info["page_count"] >= 1
    assert info["encrypted"] is False
    assert info["previewable"] is True
    assert info["original_filename"] == "cv.pdf"
    assert info["size_bytes"] == resume["size_bytes"]
    assert info["uploaded_at"]
    assert info["previous_files"] == 0
    assert info["parse_status"] == "PARSED"
    assert "Aarav Sharma" in info["extracted_text"]


def test_file_info_for_docx(api: TestClient) -> None:
    resume = _upload(api, build_docx(), "cv.docx", DOCX_MIME)
    info = api.get(f"{RESUMES}/{resume['id']}/file-info").json()
    assert info["format"] == "docx"
    assert info["previewable"] is False
    assert "Aarav Sharma" in info["extracted_text"]


def test_file_info_reports_encrypted_pdf(api: TestClient) -> None:
    resume = _upload(api, _encrypted_pdf(), "locked.pdf")
    info = api.get(f"{RESUMES}/{resume['id']}/file-info").json()
    assert info["encrypted"] is True
    assert info["previewable"] is False


def test_file_info_for_built_resume(api: TestClient) -> None:
    built = api.post(f"{RESUMES}/build", json={"name": "Built", "parsed_data": {"name": "A"}}).json()
    info = api.get(f"{RESUMES}/{built['id']}/file-info").json()
    assert info["has_file"] is False
    assert info["format"] is None


# --------------------------------------------------------------------------- replace


def test_replace_creates_a_user_version_and_keeps_the_old_file(api: TestClient, db: Session) -> None:
    resume = _upload(api, build_pdf(), "old.pdf")
    old_path = db.get(Resume, uuid.UUID(resume["id"])).file_path
    new_text = SAMPLE_RESUME_TEXT.replace("Aarav Sharma", "Aarav K Sharma")
    response = api.post(f"{RESUMES}/{resume['id']}/file", files={"file": ("new.docx", build_docx(new_text), DOCX_MIME)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_version"] == 2
    assert body["original_filename"] == "new.docx"
    assert body["mime_type"] == DOCX_MIME
    assert body["kind"] == "UPLOADED"

    db.expire_all()
    row = db.get(Resume, uuid.UUID(resume["id"]))
    assert row.file_path != old_path
    versions = list(db.scalars(select(ResumeVersion).where(ResumeVersion.resume_id == row.id).order_by(ResumeVersion.version_number)))
    assert [v.version_number for v in versions] == [1, 2]
    assert versions[0].file_path == old_path  # the previous file stays with its version
    assert versions[1].file_path == row.file_path
    assert versions[1].change_source == ResumeChangeSource.USER
    assert "old.pdf" in versions[1].note and "new.docx" in versions[1].note
    assert storage.file_exists(old_path)

    info = api.get(f"{RESUMES}/{resume['id']}/file-info").json()
    assert info["previous_files"] == 1
    assert info["format"] == "docx"
    # The inline endpoint now serves the new file.
    assert api.get(f"{RESUMES}/{resume['id']}/file").headers["content-type"] == DOCX_MIME


def test_replace_rejects_renamed_exe(api: TestClient) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf")
    exe = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff" + b"\x00" * 200 + b"This program cannot be run in DOS mode."
    response = api.post(f"{RESUMES}/{resume['id']}/file", files={"file": ("resume.pdf", exe, "application/pdf")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_pdf"
    as_docx = api.post(f"{RESUMES}/{resume['id']}/file", files={"file": ("resume.docx", exe, DOCX_MIME)})
    assert as_docx.json()["error"]["code"] == "invalid_docx"
    as_exe = api.post(f"{RESUMES}/{resume['id']}/file", files={"file": ("resume.exe", exe, "application/octet-stream")})
    assert as_exe.json()["error"]["code"] == "unsupported_file_type"


def test_replace_rejects_encrypted_pdf_same_file_and_oversize(api: TestClient, monkeypatch) -> None:
    pdf = build_pdf()
    resume = _upload(api, pdf, "cv.pdf")
    locked = api.post(f"{RESUMES}/{resume['id']}/file", files={"file": ("l.pdf", _encrypted_pdf(), "application/pdf")})
    assert locked.status_code == 422 and locked.json()["error"]["code"] == "encrypted_pdf"
    same = api.post(f"{RESUMES}/{resume['id']}/file", files={"file": ("cv.pdf", pdf, "application/pdf")})
    assert same.status_code == 422 and same.json()["error"]["code"] == "same_file"
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    big = b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10)
    too_big = api.post(f"{RESUMES}/{resume['id']}/file", files={"file": ("big.pdf", big, "application/pdf")})
    assert too_big.status_code == 422 and too_big.json()["error"]["code"] == "file_too_large"


def test_replace_refused_for_built_resume(api: TestClient) -> None:
    built = api.post(f"{RESUMES}/build", json={"name": "Built", "parsed_data": {"name": "A"}}).json()
    response = api.post(f"{RESUMES}/{built['id']}/file", files={"file": ("cv.pdf", build_pdf(), "application/pdf")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "not_uploaded"


# --------------------------------------------------------------------------- edit copy


def test_edit_copy_creates_a_created_resume_and_leaves_the_original(api: TestClient, db: Session) -> None:
    resume = _upload(api, build_pdf(), "cv.pdf")
    before = db.get(Resume, uuid.UUID(resume["id"]))
    before_state = (before.file_path, before.current_version, dict(before.parsed_data), before.kind)

    response = api.post(f"{RESUMES}/{resume['id']}/edit-copy", json={})
    assert response.status_code == 201, response.text
    copy_ = response.json()
    assert copy_["kind"] == "CREATED"
    assert copy_["source_resume_id"] == resume["id"]
    assert copy_["has_file"] is False
    assert copy_["name"] == "Original CV (edited copy)"
    assert copy_["parsed_data"]["name"] == resume["parsed_data"]["name"]
    assert copy_["is_default"] is False

    # Editing the copy does not touch the original.
    data = dict(copy_["parsed_data"])
    data["summary"] = "Changed in the copy only."
    assert api.put(f"{RESUMES}/{copy_['id']}/parsed-data", json=data).status_code == 200

    db.expire_all()
    after = db.get(Resume, uuid.UUID(resume["id"]))
    assert (after.file_path, after.current_version, dict(after.parsed_data), after.kind) == before_state
    assert after.is_default is True


def test_edit_copy_takes_a_name(api: TestClient) -> None:
    resume = _upload(api, build_docx(), "cv.docx", DOCX_MIME)
    copy_ = api.post(f"{RESUMES}/{resume['id']}/edit-copy", json={"name": "  My edit  "}).json()
    assert copy_["name"] == "My edit"
    # No body at all works too.
    assert api.post(f"{RESUMES}/{resume['id']}/edit-copy").status_code == 201
