"""Duplicate detection for job postings (``docs/CONTRACTS.md`` §9).

The same role is typically published on LinkedIn, Naukri, Indeed *and* the company's
own careers page. JobPilot stores it as **one** :class:`~app.models.job.Job` with one
:class:`~app.models.job.JobSource` row per platform.

Matching cascade, cheapest first::

    1. (source, external_id)  — we have seen this exact listing before
    2. canonical_url          — identical URL
    3. dedupe_hash            — company + normalised title + normalised location
    4. fuzzy                  — title token_set_ratio >= 90 within the same company
                                AND description similarity >= 0.8
"""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from typing import Any

from rapidfuzz import fuzz

from app.modules.jobs.normalize import normalize_location, normalize_title

logger = logging.getLogger(__name__)

#: rapidfuzz ``token_set_ratio`` threshold (0-100) for two titles to be the same role.
TITLE_SIMILARITY_THRESHOLD = 90
#: Normalised (0-1) description similarity required on top of a title match.
DESCRIPTION_SIMILARITY_THRESHOLD = 0.8

__all__ = [
    "compute_dedupe_hash",
    "dedupe_hash_for",
    "title_similarity",
    "description_similarity",
    "is_duplicate",
    "find_fuzzy_duplicate",
    "TITLE_SIMILARITY_THRESHOLD",
    "DESCRIPTION_SIMILARITY_THRESHOLD",
]


def compute_dedupe_hash(company_norm: str, title_norm: str, location_norm: str | None) -> str:
    """Stable 32-char fingerprint of (company, title, location).

    All three parts must already be normalised — see :mod:`app.modules.jobs.normalize`.
    """
    payload = "|".join([(company_norm or "").strip(), (title_norm or "").strip(), (location_norm or "").strip()])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def dedupe_hash_for(company_norm: str, title: str | None, location: str | None) -> str:
    """Convenience wrapper that normalises ``title``/``location`` first."""
    return compute_dedupe_hash(company_norm, normalize_title(title), normalize_location(location) or "")


def title_similarity(left: str | None, right: str | None) -> float:
    """0-100 similarity of two titles after normalisation."""
    return float(fuzz.token_set_ratio(normalize_title(left), normalize_title(right)))


def description_similarity(left: str | None, right: str | None) -> float:
    """0-1 similarity of two descriptions (empty descriptions score 0)."""
    if not left or not right:
        return 0.0
    return float(fuzz.token_set_ratio(left, right)) / 100.0


def is_duplicate(
    title_a: str | None,
    description_a: str | None,
    title_b: str | None,
    description_b: str | None,
) -> bool:
    """True when two postings *of the same company* describe the same role."""
    if title_similarity(title_a, title_b) < TITLE_SIMILARITY_THRESHOLD:
        return False
    return description_similarity(description_a, description_b) >= DESCRIPTION_SIMILARITY_THRESHOLD


def find_fuzzy_duplicate(
    title: str | None,
    description: str | None,
    candidates: Iterable[Any],
) -> Any | None:
    """Return the best fuzzy match among ``candidates`` (Job rows of the same company)."""
    best: Any | None = None
    best_score = 0.0
    for candidate in candidates:
        score = title_similarity(title, getattr(candidate, "title", None))
        if score < TITLE_SIMILARITY_THRESHOLD:
            continue
        if description_similarity(description, getattr(candidate, "description", None)) < DESCRIPTION_SIMILARITY_THRESHOLD:
            continue
        if score > best_score:
            best, best_score = candidate, score
    if best is not None:
        logger.debug("Fuzzy duplicate matched %r with score %.1f", title, best_score)
    return best
