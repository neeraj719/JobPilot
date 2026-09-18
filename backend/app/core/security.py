"""Password hashing, JWT issuance/verification and symmetric encryption.

* Passwords: bcrypt (12 rounds).
* Access tokens: short-lived HS256 JWTs carried in the ``Authorization`` header.
* Refresh tokens: opaque random strings, stored **hashed** in the DB, delivered in an
  ``HttpOnly`` cookie and rotated on every use.
* Sensitive data at rest (OAuth tokens, platform credentials, browser storage state):
  Fernet symmetric encryption with ``ENCRYPTION_KEY``.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

# --------------------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# --------------------------------------------------------------------------- JWT


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: uuid.UUID | str, role: str, extra: dict[str, Any] | None = None) -> str:
    expire = _now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": int(_now().timestamp()),
        "exp": int(expire.timestamp()),
        "jti": secrets.token_hex(8),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token. Raises ``jwt.PyJWTError`` on failure."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return payload


# --------------------------------------------------------------------------- refresh tokens


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return _now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


# --------------------------------------------------------------------------- encryption


class SecretBox:
    """Thin Fernet wrapper for encrypting sensitive strings at rest."""

    def __init__(self, key: str | None = None) -> None:
        self._fernet = Fernet((key or settings.ENCRYPTION_KEY).encode("utf-8"))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:  # pragma: no cover - defensive
            raise ValueError("Could not decrypt secret (wrong ENCRYPTION_KEY?)") from exc


secret_box = SecretBox()


def encrypt_str(value: str) -> str:
    return secret_box.encrypt(value)


def decrypt_str(value: str) -> str:
    return secret_box.decrypt(value)


def mask_secret(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]
