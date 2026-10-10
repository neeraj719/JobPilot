"""Resume file storage: validation, hashing and on-disk layout.

Files live under ``UPLOAD_DIR/resumes/<user_id>/<uuid>.<ext>`` so one user can never
reach another user's directory, and the API only ever exposes the resume id.

Uploads are validated on **extension and magic bytes** — a ``.pdf`` that is not a PDF
is rejected before anything tries to parse it.
"""
from __future__ import annotations

import hashlib
import io
import logging
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.exceptions import ValidationFailed

logger = logging.getLogger(__name__)

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

ALLOWED_EXTENSIONS: dict[str, str] = {"pdf": PDF_MIME, "docx": DOCX_MIME}
RESUMES_SUBDIR = "resumes"


@dataclass(frozen=True)
class StoredFile:
    path: str
    ext: str
    mime_type: str
    size_bytes: int
    sha256: str


def upload_root() -> Path:
    return Path(settings.UPLOAD_DIR).expanduser().resolve()


def resume_dir(user_id: uuid.UUID | str) -> Path:
    return upload_root() / RESUMES_SUBDIR / str(user_id)


def max_upload_bytes() -> int:
    return int(settings.MAX_UPLOAD_MB) * 1024 * 1024


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


#: How much of an upload is pulled into memory at a time.
READ_CHUNK_BYTES = 256 * 1024


def read_within_limit(fileobj: Any, limit: int | None = None) -> bytes:
    """Read ``fileobj`` but stop as soon as it exceeds the upload limit.

    Reading the whole request body first and *then* checking its size lets one
    request pin an arbitrary amount of memory, so the limit is enforced while
    streaming: at most ``limit`` bytes are ever retained.
    """
    cap = max_upload_bytes() if limit is None else int(limit)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = fileobj.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > cap:
            raise ValidationFailed(
                f"File is too large. The limit is {settings.MAX_UPLOAD_MB} MB.",
                code="file_too_large",
                details={"limit_bytes": cap},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _extension_of(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    return suffix


def _looks_like_pdf(content: bytes) -> bool:
    return content[:5].startswith(b"%PDF")


def _looks_like_docx(content: bytes) -> bool:
    if not content[:2] == b"PK":
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, OSError):
        return False
    return "word/document.xml" in names


def validate_upload(filename: str, content: bytes) -> tuple[str, str]:
    """Return ``(ext, mime_type)`` or raise ``ValidationFailed`` (HTTP 422)."""
    ext = _extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationFailed(
            "Unsupported file type. Upload a PDF or DOCX resume.",
            code="unsupported_file_type",
            details={"filename": filename, "allowed": sorted(ALLOWED_EXTENSIONS)},
        )
    if not content:
        raise ValidationFailed("The uploaded file is empty.", code="empty_file")

    limit = max_upload_bytes()
    if len(content) > limit:
        raise ValidationFailed(
            f"File is too large. The limit is {settings.MAX_UPLOAD_MB} MB.",
            code="file_too_large",
            details={"size_bytes": len(content), "limit_bytes": limit},
        )

    if ext == "pdf" and not _looks_like_pdf(content):
        raise ValidationFailed("That file is not a valid PDF.", code="invalid_pdf")
    if ext == "docx" and not _looks_like_docx(content):
        raise ValidationFailed("That file is not a valid DOCX document.", code="invalid_docx")

    return ext, ALLOWED_EXTENSIONS[ext]


def save_resume_file(user_id: uuid.UUID | str, content: bytes, ext: str) -> StoredFile:
    """Write the upload to disk and describe what was written."""
    directory = resume_dir(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4()}.{ext}"
    path.write_bytes(content)
    logger.info("Stored resume file for user %s at %s (%d bytes)", user_id, path.name, len(content))
    return StoredFile(
        path=str(path),
        ext=ext,
        mime_type=ALLOWED_EXTENSIONS.get(ext, "application/octet-stream"),
        size_bytes=len(content),
        sha256=sha256_bytes(content),
    )


def store_upload(user_id: uuid.UUID | str, filename: str, content: bytes) -> StoredFile:
    ext, _mime = validate_upload(filename, content)
    return save_resume_file(user_id, content, ext)


def read_file(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def file_exists(path: str | Path | None) -> bool:
    return bool(path) and Path(str(path)).is_file()


def delete_file(path: str | Path | None) -> bool:
    """Best-effort delete; a missing file is not an error."""
    if not path:
        return False
    target = Path(str(path))
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:  # pragma: no cover - locked file on Windows
        logger.warning("Could not delete resume file %s: %s", target, exc)
        return False


def safe_download_name(original_filename: str | None, ext: str | None = None) -> str:
    """A filename safe to put in a Content-Disposition header."""
    name = Path(original_filename or "").name.strip() or f"resume.{ext or 'pdf'}"
    return "".join(ch for ch in name if ch.isalnum() or ch in " ._-()[]").strip() or f"resume.{ext or 'pdf'}"


__all__ = [
    "ALLOWED_EXTENSIONS",
    "DOCX_MIME",
    "PDF_MIME",
    "StoredFile",
    "delete_file",
    "file_exists",
    "max_upload_bytes",
    "read_file",
    "read_within_limit",
    "resume_dir",
    "safe_download_name",
    "save_resume_file",
    "sha256_bytes",
    "store_upload",
    "upload_root",
    "validate_upload",
]
