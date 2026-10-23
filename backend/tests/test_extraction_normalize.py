"""Text extraction turns typographic characters into plain text (DOCX and PDF)."""
from __future__ import annotations

import pytest

from app.modules.resumes.extraction import extract_docx_text, extract_pdf_text, normalize_text

try:  # pytest puts ``tests/`` on sys.path; the package path is the fallback
    from helpers.documents import build_docx, build_pdf
except ImportError:  # pragma: no cover
    from tests.helpers.documents import build_docx, build_pdf  # type: ignore[no-redef]

TYPOGRAPHIC = (
    "Neeraj Mishra\n"
    "Software Developer Nov 2024 \u2013 Present\n"
    "Leading the project\u2014 guiding a team of developers.\n"
    "\u2022 Built \u201csmart\u201d search with the team\u2019s\u00a0OCR pipeline\u2026\n"
    "Skills: Python \u2022 FastAPI \u2022 React\n"
    "co\u00adoperation with zero\u200bwidth and lost \ufffd characters\n"
)

EXPECTED_LINES = [
    "Neeraj Mishra",
    "Software Developer Nov 2024 - Present",
    "Leading the project - guiding a team of developers.",
    '- Built "smart" search with the team\'s OCR pipeline...',
    "Skills: Python \u2022 FastAPI \u2022 React",
    "cooperation with zerowidth and lost characters",
]


def _assert_plain(text: str) -> None:
    assert "\ufffd" not in text
    allowed = {"\u2022"}  # the inline bullet separator split_bullets understands
    assert all(ord(ch) < 127 or ch in allowed for ch in text), sorted({hex(ord(c)) for c in text if ord(c) >= 127})


def test_normalize_text_maps_dashes_quotes_spaces_and_bullets():
    text = normalize_text(TYPOGRAPHIC)
    _assert_plain(text)
    assert "\u2014" not in text and "\u2013" not in text


def test_docx_extraction_is_plain_text():
    text = extract_docx_text(build_docx(TYPOGRAPHIC))
    _assert_plain(text)
    assert text.splitlines() == EXPECTED_LINES


def test_pdf_extraction_is_plain_text():
    # The helper PDF uses WinAnsiEncoding, so dashes, quotes, the bullet and the NBSP are real
    # glyphs in the file; zero-width/soft-hyphen/U+FFFD cannot be encoded and are left out.
    source = TYPOGRAPHIC.replace("\u00ad", "").replace("\u200b", "").replace(" \ufffd", "")
    text = extract_pdf_text(build_pdf(source))
    _assert_plain(text)
    assert "Leading the project - guiding a team of developers." in text
    assert "Nov 2024 - Present" in text
    assert '- Built "smart" search' in text


@pytest.mark.parametrize("glyph", ["\u25cf", "\u25aa", "\uf0b7", "\u00b7", "\u27a2"])
def test_leading_bullet_glyphs_become_a_plain_marker(glyph):
    assert normalize_text(f"{glyph} Shipped the API") == "- Shipped the API"
