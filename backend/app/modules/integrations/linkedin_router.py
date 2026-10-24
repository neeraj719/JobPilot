"""LinkedIn connection endpoints, mounted by ``app.main`` at the API prefix.

``/integrations/linkedin/*`` (this file) and ``/resumes/from-linkedin``
(``app.modules.resumes.router_linkedin``) share one router so ``app.main`` needs a single
``include_router`` line. Every route but the OAuth callback requires the ``resume`` workspace
module; the callback is public (LinkedIn's redirect carries no bearer token) and is identified
by the signed single-use ``state`` plus the matching ``HttpOnly`` cookie.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_module
from app.core.exceptions import AppError, RateLimitedError, ValidationFailed
from app.core.rate_limit import rate_limiter
from app.models.user import User
from app.modules.integrations import linkedin_oauth, linkedin_service
from app.modules.integrations.linkedin_schemas import (
    LinkedInApplyRequest,
    LinkedInApplyResult,
    LinkedInStatus,
    LinkedInSyncResult,
    LinkedInUpdate,
)
from app.modules.integrations.schemas import AuthorizationUrlResponse
from app.modules.integrations.service import frontend_redirect
from app.modules.resumes.router_linkedin import router as resumes_linkedin_router

logger = logging.getLogger(__name__)

router = APIRouter()
linkedin = APIRouter(prefix="/integrations/linkedin", tags=["integrations"])
resume_module = [Depends(require_module("resume"))]

#: The SPA page the callback returns to.
RETURN_ROUTE = "/resume/new?source=linkedin"
_STATE_COOKIE_PATH = f"{settings.API_PREFIX}/integrations/linkedin"
CONNECT_PER_MINUTE = 10
SYNC_PER_MINUTE = 6
EXPORT_MAX_FILES = 12


def _limit(user: User, bucket: str, per_minute: int) -> None:
    allowed, _ = rate_limiter.check(f"linkedin:{bucket}:{user.id}", per_minute, 60)
    if not allowed:
        raise RateLimitedError("Too many LinkedIn requests. Try again in a minute.")


def _safe_code(value: str | None) -> str:
    """LinkedIn's ``error`` is echoed into the SPA URL: keep it an opaque code."""
    cleaned = "".join(ch for ch in (value or "") if ch.isalnum() or ch in "_-.")[:64]
    if cleaned in ("user_cancelled_login", "user_cancelled_authorize"):
        return "access_denied"
    return cleaned or "connection_failed"


def _clear_state_cookie(response: Response) -> None:
    response.delete_cookie(
        key=linkedin_oauth.STATE_COOKIE_NAME,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=_STATE_COOKIE_PATH,
    )


def _back(query: str) -> RedirectResponse:
    redirect = RedirectResponse(frontend_redirect(f"{RETURN_ROUTE}&{query}"), status_code=status.HTTP_302_FOUND)
    _clear_state_cookie(redirect)
    return redirect


@linkedin.get("", response_model=LinkedInStatus, dependencies=resume_module, summary="LinkedIn connection status (no tokens)")
@linkedin.get("/", response_model=LinkedInStatus, dependencies=resume_module, include_in_schema=False)
def get_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> LinkedInStatus:
    return linkedin_service.status_of(db, user.id)


@linkedin.post("/connect", response_model=AuthorizationUrlResponse, dependencies=resume_module, summary="Start LinkedIn OAuth (OIDC + PKCE)")
def connect(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AuthorizationUrlResponse:
    _limit(user, "connect", CONNECT_PER_MINUTE)
    url, state = linkedin_oauth.start_authorization(db, user.id)
    response.set_cookie(
        key=linkedin_oauth.STATE_COOKIE_NAME,
        value=state,
        max_age=linkedin_oauth.STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=_STATE_COOKIE_PATH,
    )
    return AuthorizationUrlResponse(authorization_url=url)


@linkedin.get("/callback", response_class=RedirectResponse, summary="OAuth redirect target (public; identified by the signed state)")
def callback(
    request: Request,
    code: str | None = Query(default=None, max_length=2000),
    state: str | None = Query(default=None, max_length=2000),
    error: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    cookie_state = request.cookies.get(linkedin_oauth.STATE_COOKIE_NAME)
    if error:
        logger.info("LinkedIn OAuth returned error=%s", _safe_code(error))
        return _back(f"error={_safe_code(error)}")
    try:
        linkedin_oauth.handle_callback(db, code or "", state or "", cookie_state=cookie_state)
    except AppError as exc:
        db.commit()  # keep the burnt state and the rejection audit row
        logger.warning("LinkedIn OAuth callback failed: %s", exc.code)
        return _back(f"error={_safe_code(exc.code)}")
    except Exception as exc:  # noqa: BLE001 - a redirect is friendlier than a 500 here
        db.rollback()
        logger.exception("Unexpected LinkedIn OAuth callback failure: %s", type(exc).__name__)
        return _back("error=connection_failed")
    return _back("connected=1")


@linkedin.post("/sync", response_model=LinkedInSyncResult, dependencies=resume_module, summary="Re-read LinkedIn and diff it against your profile")
def sync(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> LinkedInSyncResult:
    _limit(user, "sync", SYNC_PER_MINUTE)
    try:
        return linkedin_service.sync(db, user.id, trigger="manual")
    except AppError:
        db.commit()  # keep the expired / revoked / last_error marker for the UI
        raise


@linkedin.get("/diff", response_model=LinkedInSyncResult, dependencies=resume_module, summary="The stored snapshot diffed against your profile now")
def diff(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> LinkedInSyncResult:
    return linkedin_service.current_diff(db, user.id)


@linkedin.post("/apply", response_model=LinkedInApplyResult, dependencies=resume_module, summary="Write the selected changes to your profile")
def apply(payload: LinkedInApplyRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> LinkedInApplyResult:
    return linkedin_service.apply_changes(db, user.id, payload.change_ids)


@linkedin.post("/export", response_model=LinkedInSyncResult, dependencies=resume_module, summary="Add a LinkedIn export ZIP for the full history")
def add_export(
    files: list[UploadFile] = File(..., description="The LinkedIn export ZIP, or its CSV files"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LinkedInSyncResult:
    from app.modules.resumes import storage

    _limit(user, "export", SYNC_PER_MINUTE)
    if len(files) > EXPORT_MAX_FILES:
        raise ValidationFailed(f"Upload at most {EXPORT_MAX_FILES} files.", code="too_many_files")
    loaded = [(upload.filename or "file", storage.read_within_limit(upload.file)) for upload in files]
    return linkedin_service.import_export(db, user.id, loaded)


@linkedin.patch("", response_model=LinkedInStatus, dependencies=resume_module, summary="Turn the scheduled check on or off")
@linkedin.patch("/", response_model=LinkedInStatus, dependencies=resume_module, include_in_schema=False)
def update(payload: LinkedInUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> LinkedInStatus:
    return linkedin_service.set_auto_sync(db, user.id, payload.auto_sync)


@linkedin.delete("", response_model=LinkedInStatus, dependencies=resume_module, summary="Revoke and forget the LinkedIn connection")
@linkedin.delete("/", response_model=LinkedInStatus, dependencies=resume_module, include_in_schema=False)
def disconnect(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> LinkedInStatus:
    return linkedin_service.disconnect(db, user.id)


router.include_router(linkedin)
router.include_router(resumes_linkedin_router, prefix="/resumes", tags=["resumes"], dependencies=resume_module)
