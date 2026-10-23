"""Resume templates: **data definitions**, not HTML.

A template says which sections come in which order, which fonts, sizes, spacing, date
format, accent colour and header layout to use. The React preview
(``frontend/src/features/resume-studio/preview``) and both exporters (``render.py``) read
the same definition, so what the user sees is what the PDF/DOCX contain.

Every template is ATS-friendly on purpose: a single column, real headings, real bullet
lists, standard fonts, no tables, no text boxes, no images.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.modules.ai.schemas import RESUME_SECTION_KEYS

DEFAULT_TEMPLATE_ID = "classic"

#: Section heading text. Each one is a heading the resume parser recognises, so an
#: exported resume can be imported again without losing its structure.
SECTION_LABELS: dict[str, str] = {
    "summary": "Summary",
    "skills": "Skills",
    "experience": "Experience",
    "projects": "Projects",
    "education": "Education",
    "certifications": "Certifications",
    "achievements": "Achievements",
    "languages": "Languages",
}


class TemplateFonts(BaseModel):
    #: CSS font stack for the browser preview.
    css: str
    #: One of the 14 standard PDF fonts (no embedding needed, text stays selectable).
    pdf: str
    pdf_bold: str
    pdf_italic: str
    #: A font every Word install has.
    docx: str


class TemplateSizes(BaseModel):
    """Point sizes."""

    name: float
    headline: float
    heading: float
    body: float
    small: float


class TemplateSpacing(BaseModel):
    """Points, except ``margin_in`` (inches) and ``line_height`` (multiple of the body size)."""

    margin_in: float
    line_height: float
    section_before: float
    section_after: float
    entry_gap: float
    bullet_indent: float


class ResumeTemplate(BaseModel):
    id: str
    name: str
    description: str
    section_order: list[str] = Field(default_factory=lambda: list(RESUME_SECTION_KEYS))
    fonts: TemplateFonts
    heading_fonts: TemplateFonts
    sizes: TemplateSizes
    spacing: TemplateSpacing
    #: ``MMM YYYY`` (Mar 2023), ``MM/YYYY`` (03/2023) or ``YYYY``.
    date_format: Literal["MMM YYYY", "MM/YYYY", "YYYY"] = "MMM YYYY"
    #: Hex colour for headings / rules; black keeps a template print-safe.
    accent: str = "#000000"
    #: ``centered``: name and contact lines centred; ``left``: left-aligned;
    #: ``two-line``: name + headline on one line, contacts on the next (compact).
    header_layout: Literal["centered", "left", "two-line"] = "centered"
    #: ``caps-rule``: UPPERCASE heading over a thin rule; ``accent-rule``: accent-coloured
    #: heading with an accent rule; ``bold``: bold heading, no rule.
    heading_style: Literal["caps-rule", "accent-rule", "bold"] = "caps-rule"
    #: Skills as one comma-separated line, or grouped one-per-line bullets.
    skills_style: Literal["inline", "bullets"] = "inline"
    bullet: str = "•"


_SERIF = TemplateFonts(
    css="'Times New Roman', Times, 'Liberation Serif', serif",
    pdf="Times-Roman",
    pdf_bold="Times-Bold",
    pdf_italic="Times-Italic",
    docx="Times New Roman",
)
_SANS = TemplateFonts(
    css="Arial, Helvetica, 'Liberation Sans', sans-serif",
    pdf="Helvetica",
    pdf_bold="Helvetica-Bold",
    pdf_italic="Helvetica-Oblique",
    docx="Arial",
)

TEMPLATES: dict[str, ResumeTemplate] = {
    "classic": ResumeTemplate(
        id="classic",
        name="Classic",
        description="Single column with serif headings over thin rules. Traditional and safe for every ATS.",
        fonts=_SERIF,
        heading_fonts=_SERIF,
        sizes=TemplateSizes(name=20, headline=11.5, heading=11.5, body=10.5, small=9.5),
        spacing=TemplateSpacing(
            margin_in=0.75, line_height=1.25, section_before=10, section_after=4, entry_gap=6, bullet_indent=14
        ),
        date_format="MMM YYYY",
        accent="#1f2937",
        header_layout="centered",
        heading_style="caps-rule",
    ),
    "modern": ResumeTemplate(
        id="modern",
        name="Modern",
        description="Clean sans-serif with an accent-coloured rule under each heading. Still one column, still plain text.",
        fonts=_SANS,
        heading_fonts=_SANS,
        sizes=TemplateSizes(name=21, headline=11, heading=11, body=10, small=9),
        spacing=TemplateSpacing(
            margin_in=0.7, line_height=1.3, section_before=11, section_after=4, entry_gap=6, bullet_indent=13
        ),
        date_format="MMM YYYY",
        accent="#2563eb",
        header_layout="left",
        heading_style="accent-rule",
    ),
    "compact": ResumeTemplate(
        id="compact",
        name="Compact",
        description="Tighter spacing and a two-line header to fit more on one page. Good for experienced candidates.",
        section_order=["summary", "experience", "skills", "projects", "education", "certifications", "achievements", "languages"],
        fonts=_SANS,
        heading_fonts=_SANS,
        sizes=TemplateSizes(name=16, headline=10, heading=10, body=9.5, small=8.5),
        spacing=TemplateSpacing(
            margin_in=0.55, line_height=1.18, section_before=7, section_after=2, entry_gap=3, bullet_indent=11
        ),
        date_format="MM/YYYY",
        accent="#111827",
        header_layout="two-line",
        heading_style="bold",
    ),
}


def list_templates() -> list[ResumeTemplate]:
    return list(TEMPLATES.values())


def get_template(template_id: str | None) -> ResumeTemplate:
    """The template with that id, falling back to the default for an unknown id."""
    return TEMPLATES.get((template_id or "").strip().lower()) or TEMPLATES[DEFAULT_TEMPLATE_ID]


def is_known_template(template_id: str | None) -> bool:
    return (template_id or "").strip().lower() in TEMPLATES


def effective_section_order(section_order: list[str] | None, template: ResumeTemplate) -> list[str]:
    """The resume's own order when it has one, else the template default."""
    order = [key for key in (section_order or []) if key in SECTION_LABELS]
    return order or list(template.section_order)


__all__ = [
    "DEFAULT_TEMPLATE_ID",
    "SECTION_LABELS",
    "TEMPLATES",
    "ResumeTemplate",
    "effective_section_order",
    "get_template",
    "is_known_template",
    "list_templates",
]
