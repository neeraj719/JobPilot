"""Auth request/response schemas (contract §2).

Note: request models deliberately avoid custom validators that raise ``ValueError``.
The project-wide ``RequestValidationError`` handler serialises ``exc.errors()`` as-is,
and pydantic puts the raw exception object into ``ctx`` for those - which is not JSON
serialisable. Business rules (password policy) are therefore enforced in the service
layer, which raises ``ValidationFailed`` (422) with a clean message and no echo of the
submitted password.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
PASSWORD_POLICY = "Password must be at least 8 characters and contain at least one letter and one digit."


def is_password_acceptable(value: str | None) -> bool:
    if not value or len(value) < PASSWORD_MIN_LENGTH or len(value) > PASSWORD_MAX_LENGTH:
        return False
    return bool(re.search(r"[A-Za-z]", value)) and bool(re.search(r"\d", value))


def check_password_policy(value: str) -> str:
    """Raise ``ValueError`` when the password does not satisfy the contract policy."""
    if not is_password_acceptable(value):
        raise ValueError(PASSWORD_POLICY)
    return value


#: Shared description of the "Stay signed in on this device" flag.
REMEMBER_ME_DESCRIPTION = (
    "Stay signed in on this device. true: the refresh cookie is persistent and the session "
    "lasts REFRESH_TOKEN_EXPIRE_DAYS. false (default): a browser-session cookie and a "
    "12-hour session."
)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX_LENGTH, description=PASSWORD_POLICY)
    full_name: str = Field(min_length=1, max_length=255)
    remember_me: bool = Field(default=False, description=REMEMBER_ME_DESCRIPTION)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)
    remember_me: bool = Field(default=False, description=REMEMBER_ME_DESCRIPTION)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(max_length=PASSWORD_MAX_LENGTH, description=PASSWORD_POLICY)


class UserRead(BaseModel):
    """Public user view - never exposes ``hashed_password``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    #: The single most privileged role held, derived from ``master.user_roles``.
    #: Kept as a scalar because every client and guard reads one value.
    role: UserRole
    #: Every role held, additive to ``role``: a user can hold more than one.
    roles: list[str] = Field(default_factory=list)
    #: The role this session acts as (the access token's ``role`` claim). Guards check
    #: this, not ``role``. ``None`` only where no session is involved.
    active_role: str | None = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: datetime | None = None

    @field_validator("roles", mode="before")
    @classmethod
    def _role_names(cls, value: object) -> list[str]:
        """``User.roles`` is a list of ``Role`` rows; the contract exposes their names."""
        if value is None:
            return []
        return sorted(getattr(item, "name", item) for item in value)


class TokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    #: Discriminator against :class:`RoleSelectionRequired`; always ``false`` here.
    requires_role_selection: Literal[False] = False
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    #: The role this access token acts as.
    active_role: str
    #: Every role the user may switch to (``POST /auth/switch-role``).
    available_roles: list[str] = Field(default_factory=list)
    #: Whether the refresh cookie set with this response is a remembered-device one
    #: ("Stay signed in"). ``None`` when no cookie was set (a no-op role switch).
    remembered: bool | None = None
    user: UserRead


class RoleSelectionRequired(BaseModel):
    """Returned by login/register instead of tokens when the account holds several roles.

    No session exists yet: no access token and no refresh cookie. The client answers with
    ``POST /auth/select-role`` before ``selection_token`` expires (5 minutes).
    """

    requires_role_selection: Literal[True] = True
    selection_token: str
    available_roles: list[str]
    user: UserRead


#: What ``POST /auth/login`` and ``POST /auth/register`` return: tokens, or a request to
#: pick a role first. Discriminated on ``requires_role_selection`` so OpenAPI shows both.
LoginResponse = Annotated[Union[TokenResponse, RoleSelectionRequired], Field(discriminator="requires_role_selection")]


class SelectRoleRequest(BaseModel):
    selection_token: str = Field(min_length=1, max_length=4096)
    role: str = Field(min_length=1, max_length=50)
    #: The client remembers the choice per device; the server only records it in the audit.
    remember: bool = False
    #: "Stay signed in on this device", repeated from the login form (see LoginRequest).
    remember_me: bool = Field(default=False, description=REMEMBER_ME_DESCRIPTION)


class SwitchRoleRequest(BaseModel):
    role: str = Field(min_length=1, max_length=50)


class SessionRead(BaseModel):
    """One signed-in session (a live refresh token) in the "Sessions and devices" list.

    Built only from columns ``master.refresh_tokens`` already has. ``id`` is the current
    refresh-token row of that session, so it changes whenever that device refreshes.
    """

    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    user_agent: str | None = None
    #: Friendly parse of ``user_agent`` ("Chrome on Windows"); a hint, not an identity.
    device_label: str
    #: The session whose refresh cookie came with this request.
    is_current: bool
    #: Started with "Stay signed in on this device".
    remembered: bool


class RememberDeviceRequest(BaseModel):
    #: true: keep this device signed in (persistent cookie); false: end with the browser.
    remember: bool = True


class SessionsRevoked(BaseModel):
    ok: bool = True
    message: str | None = None
    #: How many sessions were signed out.
    revoked: int
