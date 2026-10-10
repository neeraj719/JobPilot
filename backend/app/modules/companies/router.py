"""Company endpoints (contract §4). Mounted at ``/api/v1/companies``."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import CompanyPriority
from app.models.user import User
from app.modules.common.pagination import Pagination
from app.modules.common.schemas import OkResponse, PageResponse
from app.modules.companies import board_detect, service
from app.modules.companies.schemas import (
    BoardDetection,
    BoardDetectRequest,
    CompanyBoardResult,
    CompanyBoardUpdate,
    CompanyCreate,
    CompanyDetectResult,
    CompanyPreferenceItem,
    CompanyPreferenceRead,
    CompanyPreferencesReplace,
    CompanyRead,
    CompanySuggestions,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def detect_rate_limit(user: User = Depends(get_current_user)) -> User:
    """Board look-ups reach third-party sites: 10 per minute per user."""
    board_detect.enforce_rate_limit(user.id)
    return user


# --------------------------------------------------------------------------- preferences
# Declared before "/{company_id}" so "preferences" is never parsed as an id.


@router.get("/preferences", response_model=list[CompanyPreferenceRead], summary="The user's company priority list")
def list_preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[CompanyPreferenceRead]:
    return [CompanyPreferenceRead.model_validate(p) for p in service.list_user_preferences(db, user.id)]


@router.put("/preferences", response_model=list[CompanyPreferenceRead], summary="Replace the whole priority list")
def replace_preferences(
    payload: CompanyPreferencesReplace,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CompanyPreferenceRead]:
    prefs = service.replace_preferences(db, user.id, payload.items)
    return [CompanyPreferenceRead.model_validate(p) for p in prefs]


@router.post("/preferences", response_model=CompanyPreferenceRead, summary="Add or update one company priority")
def upsert_preference(
    payload: CompanyPreferenceItem,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyPreferenceRead:
    pref = service.upsert_preference(db, user.id, payload.company_name, payload.priority, notes=payload.notes)
    return CompanyPreferenceRead.model_validate(pref)


@router.delete("/preferences/{preference_id}", response_model=OkResponse, summary="Remove one company priority")
def delete_preference(
    preference_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    service.delete_preference(db, user.id, preference_id)
    return OkResponse(ok=True, message="Company preference removed")


# --------------------------------------------------------------------------- companies


@router.get("", response_model=PageResponse[CompanyRead], summary="Companies with the user's priority and counts")
@router.get("/", response_model=PageResponse[CompanyRead], include_in_schema=False)
def list_companies(
    pagination: Pagination = Depends(),
    q: str | None = Query(default=None, max_length=255, description="Name search"),
    priority: CompanyPriority | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PageResponse[CompanyRead]:
    return service.list_companies(db, user.id, pagination, q=q, priority=priority)


@router.post("", response_model=CompanyDetectResult, status_code=status.HTTP_201_CREATED, summary="Add a company by name")
@router.post("/", response_model=CompanyDetectResult, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_company(
    payload: CompanyCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyDetectResult:
    if payload.auto_detect or payload.board_url:  # both reach third-party sites
        board_detect.enforce_rate_limit(user.id)
    return service.create_company(
        db,
        user.id,
        payload.name,
        website=payload.website,
        board_url=payload.board_url,
        ats_type=payload.ats_type,
        auto_detect=payload.auto_detect,
    )


@router.post("/detect-board", response_model=BoardDetection, summary="Find a company's public job board (nothing is saved)")
def detect_board(
    payload: BoardDetectRequest,
    user: User = Depends(detect_rate_limit),
) -> BoardDetection:
    return service.detect_board(payload.name, payload.website)


@router.get("/suggestions", response_model=CompanySuggestions, summary="Known-board companies for the Quick start panel")
def list_suggestions(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanySuggestions:
    return service.list_suggestions(db, user.id, limit=limit)


@router.put("/{company_id}/board", response_model=CompanyBoardResult, summary="Verify and save the company's public job board")
def set_company_board(
    company_id: uuid.UUID,
    payload: CompanyBoardUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyBoardResult:
    return service.set_company_board(db, user.id, company_id, payload.ats_type, payload.board_url)


@router.post(
    "/{company_id}/detect-board", response_model=CompanyDetectResult, summary="Re-run board detection and save a found board"
)
def detect_company_board(
    company_id: uuid.UUID,
    user: User = Depends(detect_rate_limit),
    db: Session = Depends(get_db),
) -> CompanyDetectResult:
    return service.detect_company_board(db, user.id, company_id)


@router.delete("/{company_id}/board", response_model=CompanyRead, summary="Stop reading the company's job board")
def clear_company_board(
    company_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyRead:
    return service.clear_company_board(db, user.id, company_id)


@router.get("/{company_id}", response_model=CompanyRead, summary="One company")
def get_company(
    company_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyRead:
    return service.get_company_read(db, user.id, company_id)


@router.post("/{company_id}/blacklist", response_model=CompanyPreferenceRead, summary="Avoid a company and skip its open applications")
def blacklist_company(
    company_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyPreferenceRead:
    return CompanyPreferenceRead.model_validate(service.blacklist_company(db, user.id, company_id))
