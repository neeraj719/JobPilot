"""Audit log endpoints (contract §5). Mounted at ``/api/v1/audit``."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.modules.audit import service
from app.modules.audit.schemas import AuditLogRead
from app.modules.common.pagination import Pagination
from app.modules.common.schemas import PageResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=PageResponse[AuditLogRead], summary="The user's audit trail")
@router.get("/", response_model=PageResponse[AuditLogRead], include_in_schema=False)
def list_audit(
    pagination: Pagination = Depends(),
    application_id: uuid.UUID | None = Query(default=None),
    automation_run_id: uuid.UUID | None = Query(default=None),
    action_prefix: str | None = Query(default=None, max_length=80, description='e.g. "application." or "auth."'),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PageResponse[AuditLogRead]:
    return service.list_logs(
        db,
        user.id,
        pagination,
        application_id=application_id,
        automation_run_id=automation_run_id,
        action_prefix=action_prefix,
    )
