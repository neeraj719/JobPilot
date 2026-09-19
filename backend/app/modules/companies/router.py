"""Company endpoints (contract §4). Mounted at ``/api/v1/companies``."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import CompanyPriority
from app.models.user import User
from app.modules.common.pagination import Pagination
from app.modules.common.schemas import OkResponse, PageResponse
from app.modules.companies import service
from app.modules.companies.schemas import (
    CompanyPreferenceItem,
    CompanyPreferenceRead,
    CompanyPreferencesReplace,
    CompanyRead,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
