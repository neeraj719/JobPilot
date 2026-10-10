"""Auth endpoints (contract §2). Thin router - all logic lives in ``auth.service``."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import active_role_of, bearer_scheme, get_current_user, require_recent_auth
from app.core.rate_limit import auth_rate_limit, client_ip
from app.models.user import User
from app.modules.auth import service
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    RegisterRequest,
    RememberDeviceRequest,
    RoleSelectionRequired,
    SelectRoleRequest,
    SessionRead,
    SessionsRevoked,
    SwitchRoleRequest,
    TokenResponse,
    UserRead,
)
from app.modules.common.schemas import OkResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- cookie helpers


def _client_ip(request: Request) -> str | None:
    """Client address for the audit trail.

    Uses the shared helper so a spoofed ``X-Forwarded-For`` cannot forge the IP
    recorded against a failed login (it is only trusted behind a real proxy).
    """
    ip = client_ip(request)
    return ip if ip != "unknown" else None


def _set_refresh_cookie(response: Response, raw_token: str, *, remembered: bool) -> None:
    """Persistent cookie for a remembered device; otherwise a browser-session cookie
    (no ``Max-Age``/``Expires``), which the browser drops when it closes."""
    response.set_cookie(
        key=service.REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=service.refresh_cookie_max_age(remembered),
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


def _token_response(response: Response, session: service.IssuedSession) -> TokenResponse:
    """Serialise an issued session; sets the refresh cookie when one was minted."""
    if session.refresh_token is not None:
        _set_refresh_cookie(response, session.refresh_token, remembered=session.remembered)
    return TokenResponse(
        access_token=session.access_token,
        token_type="bearer",
        expires_in=session.expires_in,
        active_role=session.active_role,
        available_roles=session.available_roles,
        remembered=session.remembered if session.refresh_token is not None else None,
        user=UserRead.model_validate(session.user),
    )


def _login_response(
    response: Response, outcome: service.IssuedSession | service.RoleSelectionChallenge
) -> TokenResponse | RoleSelectionRequired:
    if isinstance(outcome, service.RoleSelectionChallenge):
        # No session yet, so no refresh cookie: it is set by /auth/select-role.
        return RoleSelectionRequired(
            selection_token=outcome.selection_token,
            available_roles=outcome.available_roles,
            user=UserRead.model_validate(outcome.user),
        )
    return _token_response(response, outcome)


# --------------------------------------------------------------------------- endpoints


@router.post(
    "/register",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth_rate_limit)],
    summary="Create an account (also creates the empty profile, preferences and automation config)",
)
def register(
    payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse | RoleSelectionRequired:
    user = service.create_user(db, payload.email, payload.password, payload.full_name)
    user.last_login_at = None
    outcome = service.begin_session(
        db, user, user_agent=request.headers.get("user-agent"), remember_me=payload.remember_me
    )
    return _login_response(response, outcome)


@router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[Depends(auth_rate_limit)],
    summary="Exchange email + password for an access token, or for a role choice when the account holds several",
)
def login(
    payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse | RoleSelectionRequired:
    user = service.authenticate(db, payload.email, payload.password, ip_address=_client_ip(request))
    outcome = service.begin_session(
        db, user, user_agent=request.headers.get("user-agent"), remember_me=payload.remember_me
    )
    return _login_response(response, outcome)


@router.post(
    "/select-role",
    response_model=TokenResponse,
    dependencies=[Depends(auth_rate_limit)],
    summary="Trade the role-selection token from login for a session acting as the chosen role",
)
def select_role(
    payload: SelectRoleRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    session = service.select_role(
        db,
        payload.selection_token,
        payload.role,
        remember=payload.remember,
        remember_me=payload.remember_me,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    return _token_response(response, session)


@router.post(
    "/switch-role",
    response_model=TokenResponse,
    dependencies=[Depends(auth_rate_limit)],
    summary="Change the active role without signing out (rotates the refresh cookie)",
)
def switch_role(
    payload: SwitchRoleRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> TokenResponse:
    session = service.switch_role(
        db,
        user,
        payload.role,
        current_role=active_role_of(user),
        current_access_token=credentials.credentials if credentials else "",
        current_access_exp=getattr(request.state, "access_token_exp", None),
        raw_refresh_token=request.cookies.get(service.REFRESH_COOKIE_NAME),
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    return _token_response(response, session)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(auth_rate_limit)],
    summary="Rotate the refresh cookie and issue a new access token (same active role)",
)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    session = service.refresh_session(
        db,
        request.cookies.get(service.REFRESH_COOKIE_NAME),
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    return _token_response(response, session)


@router.post("/logout", response_model=OkResponse, summary="Revoke the refresh token and clear the cookie")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> OkResponse:
    raw_token = request.cookies.get(service.REFRESH_COOKIE_NAME)
    service.revoke_refresh_token(db, raw_token, ip_address=_client_ip(request))
    _clear_refresh_cookie(response)
    return OkResponse(ok=True, message="Logged out")


@router.get("/me", response_model=UserRead, summary="Current user")
def me(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)


@router.put(
    "/me/password",
    response_model=OkResponse,
    summary="Change the password; signs out every other session and rotates this one (needs recent sign-in)",
)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    user: User = Depends(require_recent_auth),
    db: Session = Depends(get_db),
) -> OkResponse:
    outcome = service.change_password(
        db,
        user,
        payload.current_password,
        payload.new_password,
        raw_refresh_token=request.cookies.get(service.REFRESH_COOKIE_NAME),
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    if outcome.refresh_token is not None:
        _set_refresh_cookie(response, outcome.refresh_token, remembered=outcome.remembered)
    else:
        _clear_refresh_cookie(response)
    return OkResponse(ok=True, message="Password changed. Your other devices have been signed out.")


@router.get("/sessions", response_model=list[SessionRead], summary="Signed-in sessions and devices of the current user")
def list_sessions(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[SessionRead]:
    return service.list_sessions(db, user, request.cookies.get(service.REFRESH_COOKIE_NAME))


@router.post(
    "/sessions/revoke-others",
    response_model=SessionsRevoked,
    summary="Sign out of every other device (needs recent sign-in)",
)
def revoke_other_sessions(
    request: Request, user: User = Depends(require_recent_auth), db: Session = Depends(get_db)
) -> SessionsRevoked:
    revoked = service.revoke_other_sessions(
        db, user, request.cookies.get(service.REFRESH_COOKIE_NAME), ip_address=_client_ip(request)
    )
    return SessionsRevoked(ok=True, revoked=revoked, message=f"Signed out of {revoked} other session(s).")


@router.post(
    "/sessions/current/remember",
    response_model=SessionRead,
    summary="Turn 'Stay signed in' on or off for this device (rotates the cookie; needs recent sign-in)",
)
def remember_this_device(
    payload: RememberDeviceRequest,
    request: Request,
    response: Response,
    user: User = Depends(require_recent_auth),
    db: Session = Depends(get_db),
) -> SessionRead:
    rotation, session = service.set_current_session_remembered(
        db,
        user,
        request.cookies.get(service.REFRESH_COOKIE_NAME),
        payload.remember,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, rotation.refresh_token, remembered=rotation.remembered)
    return session


@router.delete(
    "/sessions/{session_id}",
    response_model=SessionsRevoked,
    summary="Sign out one session (needs recent sign-in); clears the cookie when it is this device",
)
def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    response: Response,
    user: User = Depends(require_recent_auth),
    db: Session = Depends(get_db),
) -> SessionsRevoked:
    was_current = service.revoke_session(
        db, user, session_id, request.cookies.get(service.REFRESH_COOKIE_NAME), ip_address=_client_ip(request)
    )
    if was_current:
        _clear_refresh_cookie(response)
    return SessionsRevoked(ok=True, revoked=1, message="Signed out of that session.")
