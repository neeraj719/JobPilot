"""Automation endpoints (contract §14). Thin — every rule lives in the service."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.modules.automation import service
from app.modules.automation.schemas import (
    AutomationConfigRead,
    AutomationConfigUpdate,
    AutomationRunRead,
    AutomationStatusRead,
    RunRequest,
)
from app.modules.common.pagination import Pagination
from app.modules.common.schemas import PageResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/config", response_model=AutomationConfigRead)
def get_config(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationConfigRead:
    return service.to_config_read(service.get_config(db, user.id))


@router.put("/config", response_model=AutomationConfigRead)
def update_config(
    payload: AutomationConfigUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationConfigRead:
    return service.to_config_read(service.update_config(db, user.id, payload))


@router.post("/run", response_model=AutomationRunRead, status_code=202)
def start_run(
    payload: RunRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationRunRead:
    """Start the pipeline in a background thread; returns the RUNNING run."""
    request = payload or RunRequest()
    run = service.start_manual_run(db, user.id, dry_run=request.dry_run)
    return service.to_run_read(run)


@router.get("/runs", response_model=PageResponse[AutomationRunRead])
def list_runs(
    pagination: Pagination = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PageResponse[AutomationRunRead]:
    return service.list_runs(db, user.id, pagination)


@router.get("/runs/{run_id}", response_model=AutomationRunRead)
def get_run(
    run_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationRunRead:
    return service.to_run_read(service.get_run(db, user.id, run_id))


@router.post("/runs/{run_id}/cancel", response_model=AutomationRunRead)
def cancel_run(
    run_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationRunRead:
    return service.to_run_read(service.cancel_run(db, user.id, run_id))


@router.get("/status", response_model=AutomationStatusRead)
def get_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationStatusRead:
    return service.get_status(db, user.id)
