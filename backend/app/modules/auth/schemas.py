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


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX_LENGTH, description=PASSWORD_POLICY)
    full_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


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

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead
