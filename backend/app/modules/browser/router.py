"""Browser automation API (CONTRACTS.md section 12).

Thin router: sessions the user owns, the screenshots automation captured for their own
applications, and whether a browser is usable on this deployment at all.
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError, ValidationFailed
from app.models.application import Application
from app.models.automation import BrowserSession
from app.models.enums import Actor
from app.models.user import User
from app.modules.browser.schemas import BrowserSessionRead, BrowserStatus
from app.modules.browser.session import is_browser_available

logger = logging.getLogger(__name__)
router = APIRouter()

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


@router.get("/sessions", response_model=list[BrowserSessionRead])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[BrowserSessionRead]:
    """Browser contexts stored for the current user. Storage state is never returned."""
    rows = db.scalars(
        select(BrowserSession).where(BrowserSession.user_id == user.id).order_by(BrowserSession.created_at.desc())
    ).all()
    return [
        BrowserSessionRead(
            id=row.id,
            source=row.source,
            status=row.status,
            user_agent=row.user_agent,
            last_used_at=row.last_used_at,
            expires_at=row.expires_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            has_stored_state=bool(row.encrypted_storage_state),
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Forget a stored browser context (cookies/localStorage) for this user."""
    row = db.scalars(
        select(BrowserSession).where(BrowserSession.id == session_id, BrowserSession.user_id == user.id)
    ).first()
    if row is None:
        raise NotFoundError("Browser session not found")
    source = row.source
    db.delete(row)
    audit(
        db,
        action="browser.session_deleted",
        message=f"Browser session for {source} deleted",
        user_id=user.id,
        actor=Actor.USER,
        meta={"source": str(source), "session_id": str(session_id)},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/screenshots/{application_id}/{name}")
def get_screenshot(
    application_id: uuid.UUID,
    name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve an automation screenshot, but only for the caller's own application."""
    if not _SAFE_NAME.match(name) or ".." in name:
        raise ValidationFailed("Invalid screenshot name")
    application = db.scalars(
        select(Application).where(Application.id == application_id, Application.user_id == user.id)
    ).first()
    if application is None:
        raise NotFoundError("Application not found")

    base = (Path(settings.UPLOAD_DIR) / "screenshots" / str(application_id)).resolve()
    filename = name if name.lower().endswith(".png") else f"{name}.png"
    path = (base / filename).resolve()
    if base not in path.parents or not path.is_file():
        raise NotFoundError("Screenshot not found")
    return FileResponse(str(path), media_type="image/png", filename=filename)


@router.get("/status", response_model=BrowserStatus)
def browser_status(user: User = Depends(get_current_user)) -> BrowserStatus:
    """Whether Playwright Chromium can be launched here (sync probe, cached)."""
    return BrowserStatus(available=is_browser_available(), headless=settings.PLAYWRIGHT_HEADLESS)
