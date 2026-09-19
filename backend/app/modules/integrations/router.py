"""Integration endpoints (contract §13). Mounted at ``/api/v1/integrations``."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.models.user import User
from app.modules.common.schemas import OkResponse
from app.modules.integrations import gmail_oauth, service
from app.modules.integrations.schemas import (
    AuthorizationUrlResponse,
    ConnectedAccountCreate,
    ConnectedAccountRead,
    GmailStatus,
    IntegrationsOverview,
    SyncResult,
)

logger = logging.getLogger(__name__)

router = APIRouter()

#: Where the OAuth callback sends the browser once it is done.
EMAILS_ROUTE = "/emails"
#: Scope of the short-lived OAuth state cookie (connect + callback live under it).
_STATE_COOKIE_PATH = f"{settings.API_PREFIX}/integrations/gmail"


@router.get("", response_model=IntegrationsOverview, summary="Gmail status, platform accounts and adapters")
@router.get("/", response_model=IntegrationsOverview, include_in_schema=False)
def get_integrations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntegrationsOverview:
    return service.overview(db, user.id)


# --------------------------------------------------------------------------- gmail


def _safe_error_code(value: str | None) -> str:
    """Google's ``error`` is echoed into the SPA URL; keep it to an opaque code.

    Never reflect raw query input into a redirect the browser (or the SPA) will read.
    """
    cleaned = "".join(ch for ch in (value or "") if ch.isalnum() or ch in "_-.")[:64]
    return cleaned or "connection_failed"


def _set_state_cookie(response: Response, state: str) -> None:
    """Pin the OAuth ``state`` to this browser for the length of the consent round-trip."""
    response.set_cookie(
        key=gmail_oauth.STATE_COOKIE_NAME,
        value=state,
        max_age=gmail_oauth.STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=_STATE_COOKIE_PATH,
    )


def _clear_state_cookie(response: Response) -> None:
    response.delete_cookie(
        key=gmail_oauth.STATE_COOKIE_NAME,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=_STATE_COOKIE_PATH,
    )


@router.post("/gmail/connect", response_model=AuthorizationUrlResponse, summary="Start the read-only Gmail OAuth flow")
def connect_gmail(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthorizationUrlResponse:
    authorization_url, state = service.connect_gmail(db, user.id)
    _set_state_cookie(response, state)
    return AuthorizationUrlResponse(authorization_url=authorization_url)


@router.get(
    "/gmail/callback",
    response_class=RedirectResponse,
    summary="OAuth redirect target (unauthenticated: identified by the one-time state)",
)
def gmail_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Google sends the browser here without our bearer token, so the flow is identified
    by the single-use ``state`` **and** by the matching ``HttpOnly`` cookie set when the
    user started it — otherwise anyone could hand a victim a consent URL of their own and
    have the victim's mailbox attached to the attacker's account."""
    cookie_state = request.cookies.get(gmail_oauth.STATE_COOKIE_NAME)
    if error:
        logger.warning("Gmail OAuth returned an error: %s", error)
        redirect = RedirectResponse(
            service.frontend_redirect(f"{EMAILS_ROUTE}?error={_safe_error_code(error)}"),
            status_code=status.HTTP_302_FOUND,
        )
        _clear_state_cookie(redirect)
        return redirect
    try:
        service.complete_gmail_connect(db, code or "", state or "", cookie_state=cookie_state)
    except AppError as exc:
        db.commit()  # keep the burnt state / rejection audit record
        logger.warning("Gmail OAuth callback failed: %s", exc.message)
        redirect = RedirectResponse(
            service.frontend_redirect(f"{EMAILS_ROUTE}?error={service.error_code_of(exc)}"),
            status_code=status.HTTP_302_FOUND,
        )
        _clear_state_cookie(redirect)
        return redirect
    except Exception as exc:  # noqa: BLE001 - a redirect is always friendlier than a 500 here
        db.rollback()
        logger.exception("Unexpected Gmail OAuth callback failure: %s", exc)
        redirect = RedirectResponse(
            service.frontend_redirect(f"{EMAILS_ROUTE}?error=connection_failed"),
            status_code=status.HTTP_302_FOUND,
        )
        _clear_state_cookie(redirect)
        return redirect
    redirect = RedirectResponse(service.frontend_redirect(f"{EMAILS_ROUTE}?connected=1"), status_code=status.HTTP_302_FOUND)
    _clear_state_cookie(redirect)
    return redirect


@router.post("/gmail/sync", response_model=SyncResult, summary="Fetch and classify recent recruiting mail")
def sync_gmail(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SyncResult:
    return service.sync_gmail(db, user.id)


@router.delete("/gmail", response_model=GmailStatus, summary="Revoke and wipe the Gmail connection")
def disconnect_gmail(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GmailStatus:
    return service.disconnect_gmail(db, user.id)


# --------------------------------------------------------------------------- platform accounts


@router.get("/accounts", response_model=list[ConnectedAccountRead], summary="Connected job-platform accounts")
def list_accounts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConnectedAccountRead]:
    return service.list_accounts(db, user.id)


@router.post(
    "/accounts",
    response_model=ConnectedAccountRead,
    status_code=status.HTTP_201_CREATED,
    summary="Connect (or update) a job-platform account",
)
def connect_account(
    payload: ConnectedAccountCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectedAccountRead:
    return service.connect_account(db, user.id, payload)


@router.delete("/accounts/{account_id}", response_model=OkResponse, summary="Remove a connected account")
def remove_account(
    account_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    service.remove_account(db, user.id, account_id)
    return OkResponse(ok=True, message="Account removed")
