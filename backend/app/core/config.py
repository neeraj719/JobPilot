"""Application settings.

All configuration comes from environment variables (see ``.env.example``).
Nothing secret is hardcoded here; defaults exist only so the app can boot in
local development.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "JobPilot AI"
    ENV: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    API_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:5173"
    PUBLIC_API_URL: str = "http://localhost:8000"
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"])

    # --- Security ---
    SECRET_KEY: str = "dev-only-change-me-in-production-0123456789"
    # Fernet key (urlsafe base64, 32 bytes). Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = "u5c7P0N4T6bD9K4xhrgxIB9V4gVAsl9XBEU4D9m0rhg="
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    COOKIE_SECURE: bool = False  # set True behind HTTPS
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    RATE_LIMIT_PER_MINUTE: int = 120
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10

    # --- Database / cache ---
    DATABASE_URL: str = "postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot"
    REDIS_URL: str = "redis://localhost:6379/0"
    DB_ECHO: bool = False

    # --- Storage ---
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 10

    # --- AI ---
    LLM_PROVIDER: Literal["mock", "openai", "anthropic"] = "mock"
    LLM_MODEL: str | None = None
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    LLM_TIMEOUT_SECONDS: int = 60

    # --- Gmail OAuth (least privilege: gmail.readonly only) ---
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/gmail/callback"
    GMAIL_SCOPES: list[str] = Field(
        default_factory=lambda: [
            "https://www.googleapis.com/auth/gmail.readonly",
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
        ]
    )

    # --- Browser automation ---
    PLAYWRIGHT_HEADLESS: bool = True
    BROWSER_ACTION_DELAY_MS: int = 250
    BROWSER_TIMEOUT_MS: int = 15000
    # Base URL the *browser* uses to reach the demo ATS (inside docker this is the backend service name)
    DEMO_ATS_BASE_URL: str = "http://localhost:8000"

    # --- Automation safety rails ---
    DEFAULT_DAILY_APPLICATION_LIMIT: int = 20
    MAX_DAILY_APPLICATION_LIMIT: int = 100
    DEFAULT_MIN_MATCH_SCORE: int = 75
    AUTOMATION_RETRY_LIMIT: int = 3
    AUTOMATION_DELAY_SECONDS: float = 1.0

    # --- Demo / seed ---
    SEED_DEMO_DATA: bool = True
    DEMO_USER_EMAIL: str = "demo@jobpilot.ai"
    DEMO_USER_PASSWORD: str = "DemoPass123!"

    @field_validator("CORS_ORIGINS", "GMAIL_SCOPES", mode="before")
    @classmethod
    def _split_csv(cls, v):  # noqa: ANN001
        if isinstance(v, str):
            if v.strip().startswith("["):
                import json

                return json.loads(v)
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
