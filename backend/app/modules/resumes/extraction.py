"""Text extraction from PDF and DOCX resumes.

Extraction is *best effort*: a resume that cannot be read (scanned image, corrupt
file, exotic encoding) still uploads successfully — the row is stored with
``parse_status=FAILED`` and a human-readable ``parse_error`` so the user can fix it.
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

MIN_USEFUL_CHARS = 30


class ExtractionError(Exception):
    """Raised when a document's text cannot be read."""


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise ExtractionError("pypdf is not installed") from exc
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - pypdf raises many error types
        raise ExtractionError(f"Could not read the PDF: {exc}") from exc
    return _tidy("\n".join(pages))


def extract_docx_text(content: bytes) -> str:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise ExtractionError("python-docx is not installed") from exc
    try:
        document = docx.Document(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001 - python-docx raises many error types
        raise ExtractionError(f"Could not read the DOCX file: {exc}") from exc

    parts: list[str] = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            line = " | ".join(c for c in cells if c)
            if line:
                parts.append(line)
    return _tidy("\n".join(parts))


def extract_text(content: bytes, ext: str) -> str:
    """Extract text from an in-memory document. Raises :class:`ExtractionError`."""
    kind = (ext or "").lower().lstrip(".")
    if kind == "pdf":
        text = extract_pdf_text(content)
    elif kind == "docx":
        text = extract_docx_text(content)
    else:
        raise ExtractionError(f"Unsupported document type: {ext!r}")
    if len(text) < MIN_USEFUL_CHARS:
        raise ExtractionError(
            "No readable text found in the document (a scanned image resume needs OCR, which is not supported)."
        )
    return text


def extract_text_from_path(path: str | Path) -> str:
    file_path = Path(str(path))
    if not file_path.is_file():
        raise ExtractionError(f"Resume file is missing on disk: {file_path.name}")
    return extract_text(file_path.read_bytes(), file_path.suffix)


def try_extract_text(content: bytes, ext: str) -> tuple[str | None, str | None]:
    """``(text, error)`` — never raises, for the upload path."""
    try:
        return extract_text(content, ext), None
    except ExtractionError as exc:
        logger.warning("Resume text extraction failed: %s", exc)
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001 - defensive: never fail an upload
        logger.exception("Unexpected resume extraction failure")
        return None, f"Unexpected error while reading the document: {exc}"


__all__ = [
    "ExtractionError",
    "extract_docx_text",
    "extract_pdf_text",
    "extract_text",
    "extract_text_from_path",
    "try_extract_text",
]
