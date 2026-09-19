"""Email endpoints (contract §13). Mounted at ``/api/v1/emails``."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import EmailClassification
from app.models.user import User
from app.modules.common.pagination import Pagination
from app.modules.common.schemas import PageResponse
from app.modules.emails import service
from app.modules.emails.schemas import (
    EmailClassifyRequest,
    EmailLinkRequest,
    EmailMessageRead,
    EmailSimulateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=PageResponse[EmailMessageRead], summary="The user's recruiting emails")
@router.get("/", response_model=PageResponse[EmailMessageRead], include_in_schema=False)
def list_emails(
    pagination: Pagination = Depends(),
    classification: EmailClassification | None = Query(default=None, description="Filter by classification"),
    application_id: uuid.UUID | None = Query(default=None, description="Only emails linked to this application"),
    unlinked: bool | None = Query(default=None, description="true = only unlinked, false = only linked"),
    q: str | None = Query(default=None, max_length=255, description="Search subject, sender and body"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PageResponse[EmailMessageRead]:
    return service.list_emails(
        db,
        user.id,
        pagination,
        classification=classification,
        application_id=application_id,
        unlinked=unlinked,
        q=q,
    )


@router.post(
    "/simulate",
    response_model=EmailMessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Inject a realistic simulated email (demo + tests)",
)
def simulate_email(
    payload: EmailSimulateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailMessageRead:
    email = service.simulate(
        db,
        user.id,
        kind=payload.kind,
        application_id=payload.application_id,
        subject=payload.subject,
        body=payload.body,
        sender=payload.sender,
    )
    return service.to_read(email)


@router.get("/{email_id}", response_model=EmailMessageRead, summary="One email with its full body")
def get_email(
    email_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailMessageRead:
    return service.to_read(service.get_email(db, user.id, email_id))


@router.post("/{email_id}/link", response_model=EmailMessageRead, summary="Link an email to an application")
def link_email(
    email_id: uuid.UUID,
    payload: EmailLinkRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailMessageRead:
    return service.to_read(service.link_to_application(db, user.id, email_id, payload.application_id))


@router.post("/{email_id}/unlink", response_model=EmailMessageRead, summary="Detach a wrongly linked email")
def unlink_email(
    email_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailMessageRead:
    return service.to_read(service.unlink(db, user.id, email_id))


@router.post("/{email_id}/classify", response_model=EmailMessageRead, summary="Override the classification")
def classify_email(
    email_id: uuid.UUID,
    payload: EmailClassifyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailMessageRead:
    return service.to_read(service.reclassify(db, user.id, email_id, payload.classification))


@router.post("/{email_id}/read", response_model=EmailMessageRead, summary="Mark an email as read")
def mark_read(
    email_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailMessageRead:
    return service.to_read(service.mark_read(db, user.id, email_id))
