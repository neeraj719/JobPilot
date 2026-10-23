"""Company look-up: a company's real open roles from its public job board.

Where the board comes from, in order (no guessing about the *role*, ever):

1. **REGISTRY** - a company already in ``master.companies`` with a readable board
   (``ats_type`` + ``ats_board_token``, set through the Companies page);
2. **KNOWN** - the bundled known-board list (``companies.board_detect.find_known_board``,
   no network);
3. **DETECTED** - ``companies.service.detect_board`` (probes the four public board APIs; it
   has its own request cap and politeness rules);
4. **NONE** - nothing readable: the UI asks the user to paste the job description.

The board's postings are read through the board adapters (cached 30 minutes). When a role is
given, every posting whose title is that kind of role (``recommendations.role_matches``, the
same rule the resume analysis uses) is returned in ``matching_roles``; the user picks one.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import JobSourceType
from app.modules.adapters.boards.urls import BOARD_VENDORS, TOKEN_RE, public_board_url
from app.modules.ats.fetch import TIMEOUT_SECONDS
from app.modules.ats.schemas import CompanyLookupResult, LookupCompany, OpenRole

logger = logging.getLogger(__name__)

#: Open roles returned at most (a FAANG board lists thousands).
MAX_OPEN_ROLES = 200
MAX_MATCHING_ROLES = 50


def _vendor(value: str | None) -> JobSourceType | None:
    try:
        vendor = JobSourceType(str(value or "").strip().upper())
    except ValueError:
        return None
    return vendor if vendor in BOARD_VENDORS else None


def _board_for(db: Session, name: str) -> tuple[str, LookupCompany | None, JobSourceType | None, str | None]:
    from app.modules.companies import board_detect
    from app.modules.companies import service as companies

    company = companies.find_company_by_name(db, name)
    if company is not None:
        vendor = _vendor(company.ats_type)
        if vendor and company.ats_board_token and TOKEN_RE.match(company.ats_board_token):
            return (
                "REGISTRY",
                LookupCompany(
                    id=company.id, name=company.name, ats_type=vendor.value,
                    board_url=company.ats_board_url or public_board_url(vendor, company.ats_board_token),
                    token=company.ats_board_token,
                ),
                vendor,
                company.ats_board_token,
            )
    known = board_detect.find_known_board(name, company.website if company is not None else None)
    if known is not None:
        return (
            "KNOWN",
            LookupCompany(
                id=company.id if company else None, name=company.name if company else known.name,
                ats_type=known.ats_type.value, board_url=known.board_url, token=known.token,
            ),
            known.ats_type,
            known.token,
        )
    detection = companies.detect_board(name, company.website if company is not None else None)
    vendor = _vendor(detection.ats_type)
    if detection.supported and vendor and detection.token:
        return (
            "DETECTED",
            LookupCompany(
                id=company.id if company else None,
                name=(company.name if company else None) or detection.board_company or name,
                ats_type=vendor.value, board_url=detection.board_url, token=detection.token,
            ),
            vendor,
            detection.token,
        )
    return "NONE", LookupCompany(id=company.id, name=company.name) if company else None, None, None


def lookup_company(db: Session, user_id: uuid.UUID, name: str, role: str | None = None) -> CompanyLookupResult:
    """Open roles of ``name``'s public board; never picks a role for the user."""
    from app.modules.adapters.base import BoardToken
    from app.modules.adapters.boards import http as board_http
    from app.modules.adapters.registry import get_adapter
    from app.modules.resumes.recommendations import role_matches

    query = " ".join((name or "").split())[:255]
    role_text = " ".join((role or "").split())[:255] or None
    method, company, vendor, token = _board_for(db, query)
    if vendor is None or token is None:
        return CompanyLookupResult(
            query=query,
            role=role_text,
            company=company,
            method="NONE",
            message=(
                f"No public job board JobPilot can read was found for {query}. Paste the job description from the "
                "posting instead."
            ),
        )
    try:
        with board_http.request_timeout(TIMEOUT_SECONDS):
            postings = get_adapter(vendor).fetch_board(BoardToken(company.id if company else None, token, company.name if company else query, None, vendor))
    except board_http.BoardFetchError as exc:
        logger.info("Company lookup: %s/%s unreadable: %s", vendor.value, token, exc)
        return CompanyLookupResult(
            query=query, role=role_text, company=company, method=method, supported=True,  # type: ignore[arg-type]
            message=f"{company.name if company else query}'s {vendor.value.title()} board could not be read right now. "
            "Try again, or paste the job description.",
        )
    roles = [
        OpenRole(
            title=p.title,
            location=p.location,
            url=p.url,
            external_id=p.external_id,
            vendor=vendor.value,
            token=token,
            work_mode=p.work_mode,
            posted_at=p.posted_at,
        )
        for p in postings
        if p.title
    ]
    roles.sort(key=lambda r: (r.title.lower(), r.location or ""))
    matching = [r for r in roles if role_text and role_matches(r.title, [role_text])][:MAX_MATCHING_ROLES]
    label = company.name if company else query
    if not roles:
        message = f"{label}'s board has no open roles right now. Paste the job description if you have it."
    elif role_text and not matching:
        message = f"None of {label}'s {len(roles)} open roles is a {role_text} role. Pick one below or paste the job description."
    elif role_text and len(matching) > 1:
        message = f"{label} has {len(matching)} open {role_text} roles. Choose the one you are applying for."
    elif role_text:
        message = f"Found one open {role_text} role at {label}. Confirm it is the one you mean."
    else:
        message = f"{label} has {len(roles)} open roles. Choose the one you are applying for."
    return CompanyLookupResult(
        query=query,
        role=role_text,
        company=company,
        method=method,  # type: ignore[arg-type]
        supported=True,
        total_open=len(roles),
        open_roles=roles[:MAX_OPEN_ROLES],
        matching_roles=matching,
        message=message,
    )


__all__ = ["lookup_company"]
