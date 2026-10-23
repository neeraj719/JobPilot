"""Build tiny, valid PDF and DOCX resumes in memory.

No binary fixtures are committed: the PDF is hand-written (a real xref table plus a
Helvetica text stream, so ``pypdf`` can extract the text back) and the DOCX comes from
``python-docx``.
"""
from __future__ import annotations

import io

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT_MARGIN = 40
TOP_BASELINE = 750
LINE_HEIGHT = 12
FONT_SIZE = 9
LINES_PER_PAGE = 55


SAMPLE_RESUME_TEXT = """Aarav Sharma
Bangalore, India | +91 98765 43210 | aarav.sharma@example.com
linkedin.com/in/aaravsharma | github.com/aaravsharma | https://aarav.dev

Summary
Full Stack Developer with 2 years of professional experience building React and Node.js
products on AWS. Comfortable owning a feature end to end, from PostgreSQL schema design
to production deployment.

Technical Skills
Languages: JavaScript, TypeScript, Python, SQL
Frontend: React, Redux, Tailwind CSS, HTML, CSS
Backend: Node.js, Express.js, FastAPI, REST APIs
Databases: PostgreSQL, MongoDB, Redis
Cloud and Tools: AWS, Docker, Git, CI/CD, Jest

Work Experience
Software Engineer - Northwind Labs
Bangalore, India | Mar 2023 - Present
- Built a React and TypeScript dashboard used by 4,000 internal users.
- Designed PostgreSQL schemas and Node.js services behind REST APIs.
- Added Docker based CI/CD pipelines that cut deploy time in half.

Junior Software Engineer, Acme Cloud
Pune, India | 07/2021 - 02/2023
- Maintained Express.js microservices and MongoDB data pipelines.
- Wrote Jest unit tests raising coverage from 40% to 82%.

Education
B.Tech in Computer Science - VIT University, Vellore
2017 - 2021 | CGPA 8.6/10

Projects
JobTracker - A Next.js and FastAPI app that tracks job applications end to end.
Technologies: Next.js, FastAPI, PostgreSQL

Kanban Lite: Real-time board with WebSockets and Redis pub/sub.

Certifications
AWS Certified Developer - Associate, 2023
MongoDB Associate Developer (2022)
"""


def _escape_pdf_text(line: str) -> bytes:
    escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    # The font uses WinAnsiEncoding, which is cp1252: dashes, curly quotes and bullets survive.
    return escaped.encode("cp1252", errors="replace")


def _content_stream(lines: list[str]) -> bytes:
    parts = [
        b"BT",
        f"/F1 {FONT_SIZE} Tf".encode("latin-1"),
        f"{LINE_HEIGHT} TL".encode("latin-1"),
        f"{LEFT_MARGIN} {TOP_BASELINE} Td".encode("latin-1"),
    ]
    for line in lines:
        parts.append(b"(" + _escape_pdf_text(line) + b") Tj T*")
    parts.append(b"ET")
    return b"\n".join(parts)


def build_pdf(text: str = SAMPLE_RESUME_TEXT, *, lines_per_page: int = LINES_PER_PAGE) -> bytes:
    """A minimal but standards-correct single-font PDF containing ``text``."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    pages = [lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [[""]]

    objects: dict[int, bytes] = {}
    page_numbers: list[int] = []
    next_number = 4
    for page_lines in pages:
        page_number, content_number = next_number, next_number + 1
        next_number += 2
        page_numbers.append(page_number)
        stream = _content_stream(page_lines)
        objects[page_number] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>"
        ).encode("latin-1")
        objects[content_number] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream"
        )

    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{n} 0 R" for n in page_numbers)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_numbers)} >>".encode("latin-1")
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode("latin-1") + objects[number] + b"\nendobj\n"

    xref_offset = len(out)
    size = max(objects) + 1
    out += f"xref\n0 {size}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for number in range(1, size):
        out += f"{offsets[number]:010d} 00000 n \n".encode("latin-1")
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    return bytes(out)


def build_docx(text: str = SAMPLE_RESUME_TEXT) -> bytes:
    """A real .docx (zip + word/document.xml) containing ``text``, one paragraph per line."""
    import docx  # python-docx

    document = docx.Document()
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_fake_pdf(payload: bytes = b"not really a pdf") -> bytes:
    """Bytes with a .pdf name but no ``%PDF`` header — for magic-byte tests."""
    return payload


def build_oversized_pdf(size_bytes: int) -> bytes:
    """A valid-looking PDF padded with a comment until it exceeds ``size_bytes``."""
    base = build_pdf("Padding resume\nSummary\nJust a big file.\n")
    if len(base) >= size_bytes:
        return base
    padding = b"\n%" + b"0" * (size_bytes - len(base))
    return base + padding


__all__ = [
    "SAMPLE_RESUME_TEXT",
    "build_docx",
    "build_fake_pdf",
    "build_oversized_pdf",
    "build_pdf",
]
