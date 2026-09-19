"""Auth endpoints (contract §2). Thin router - all logic lives in ``auth.service``."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import auth_rate_limit
from app.models.user import User
from app.modules.auth import service
from app.modules.auth.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
)
from app.modules.common.schemas import OkResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- cookie helpers


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=service.REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=service.refresh_cookie_max_age(),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=service.refresh_cookie_path(),
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=service.REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=service.refresh_cookie_path(),
    )


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=service.issue_access_token(user),
        token_type="bearer",
        expires_in=service.access_token_ttl_seconds(),
        user=UserRead.model_validate(user),
    )


# --------------------------------------------------------------------------- endpoints


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth_rate_limit)],
    summary="Create an account (also creates the empty profile, preferences and automation config)",
)
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    user = service.create_user(db, payload.email, payload.password, payload.full_name)
    user.last_login_at = None
    raw_refresh = service.create_refresh_token(db, user, user_agent=request.headers.get("user-agent"))
    _set_refresh_cookie(response, raw_refresh)
    return _token_response(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(auth_rate_limit)],
    summary="Exchange email + password for an access token (sets the refresh cookie)",
)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    user = service.authenticate(db, payload.email, payload.password, ip_address=_client_ip(request))
    raw_refresh = service.create_refresh_token(db, user, user_agent=request.headers.get("user-agent"))
    _set_refresh_cookie(response, raw_refresh)
    return _token_response(user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(auth_rate_limit)],
    summary="Rotate the refresh cookie and issue a new access token",
)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    raw_token = request.cookies.get(service.REFRESH_COOKIE_NAME)
    user, new_raw = service.rotate_refresh_token(
        db,
        raw_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, new_raw)
    return _token_response(user)


@router.post("/logout", response_model=OkResponse, summary="Revoke the refresh token and clear the cookie")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> OkResponse:
    raw_token = request.cookies.get(service.REFRESH_COOKIE_NAME)
    service.revoke_refresh_token(db, raw_token, ip_address=_client_ip(request))
    _clear_refresh_cookie(response)
    return OkResponse(ok=True, message="Logged out")


@router.get("/me", response_model=UserRead, summary="Current user")
def me(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)


@router.put("/me/password", response_model=OkResponse, summary="Change the current user's password")
def change_password(
    payload: PasswordChangeRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    service.change_password(db, user, payload.current_password, payload.new_password)
    _clear_refresh_cookie(response)
    return OkResponse(ok=True, message="Password changed. Please sign in again on your other devices.")
