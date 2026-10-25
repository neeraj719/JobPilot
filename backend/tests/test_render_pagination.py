"""PDF pagination: sections and entries flow across pages instead of jumping to a new page.

Regression for the export where a whole section (heading plus its first, tall entry) was pushed
to the next page, leaving most of the previous page blank. Only the *start* of a section or an
entry is kept together; the remaining bullets may split.
"""
import io

import pytest
from pypdf import PdfReader

from app.modules.ai.schemas import ParsedResume
from app.modules.resumes.render import render_pdf

LONG = (
    "Developed a full-stack government platform using React.js, Node.js, REST APIs, and database technologies "
    "for end-to-end rural project management. Implemented multi-level role-based workflows covering project "
    "creation, feasibility, site verification, approvals, estimates, and technical sanction for several roles "
    "with audit trails and notifications."
)
BULLET = "Engineered scalable microservices, REST APIs, and real-time streaming for enterprise-grade platforms."
HEADINGS = {"SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS", "ACHIEVEMENTS", "LANGUAGES"}


def _resume(experience_bullets: int) -> ParsedResume:
    return ParsedResume(
        name="Pagination Probe",
        email="probe@example.com",
        summary="Software developer with five years of experience building web platforms. " * 3,
        skills=["JavaScript", "React", "Node.js", "SQL", "Docker", "AWS"],
        experience=[
            {
                "company": "Example Systems",
                "title": "Software Developer",
                "start": "Nov 2024",
                "end": "Present",
                "technologies": ["JavaScript"],
                "description": "\n".join(f"- {BULLET} ({i})" for i in range(experience_bullets)),
            }
        ],
        projects=[
            {"name": "Tall first project", "description": "\n".join([f"- {LONG}", f"- {LONG}", f"- {BULLET}", f"- {BULLET}"])},
            {"name": "Second project", "description": f"- {BULLET}\n- {BULLET}"},
        ],
        education=[{"institution": "State University", "degree": "B.Tech", "start": "2016", "end": "2020"}],
    )


def _pages(pdf: bytes) -> list[list[str]]:
    reader = PdfReader(io.BytesIO(pdf))
    return [[line for line in page.extract_text().splitlines() if line.strip()] for page in reader.pages]


def test_short_resume_fits_on_one_page() -> None:
    # Before the fix this two-bullet resume took four pages: each section landed on its own page.
    pages = _pages(render_pdf(_resume(2), "classic"))
    assert len(pages) == 1, [p[0] for p in pages]


@pytest.mark.parametrize("bullets", [6, 8, 10, 12, 14, 16])
def test_sections_flow_across_pages_and_headings_never_end_a_page(bullets: int) -> None:
    pages = _pages(render_pdf(_resume(bullets), "classic"))
    assert len(pages) <= 2, [p[0] for p in pages]
    for page in pages[:-1]:
        # A heading at the bottom of a page would be an orphan: it is kept with its first line.
        assert page[-1].strip() not in HEADINGS, page[-3:]
        # The page is used: it ends inside the content, not right after the header block.
        assert len(page) >= 15, page
