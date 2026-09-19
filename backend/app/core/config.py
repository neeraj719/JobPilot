"""Application settings.

All configuration comes from environment variables (see ``.env.example``).
Nothing secret is hardcoded here; defaults exist only so the app can boot in
local development.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Development-only secrets. They are published in this repository (and in
#: ``.env.example``), so a production deployment must override both.
DEV_SECRET_KEY = "dev-only-change-me-in-production-0123456789"
DEV_ENCRYPTION_KEY = "u5c7P0N4T6bD9K4xhrgxIB9V4gVAsl9XBEU4D9m0rhg="
MIN_SECRET_KEY_LENGTH = 32

#: Gmail scopes JobPilot is allowed to request. Widening this by configuration is
#: refused at startup: the product promise is read-only mailbox access.
ALLOWED_GMAIL_SCOPES = frozenset(
    {
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.metadata",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid",
        "email",
        "profile",
    }
)


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
    # NOTE: these two defaults are *development only* and are published in this
    # repository. ``_reject_insecure_production_defaults`` refuses to boot with them
    # when ENV=production, so a deployment can never sign tokens / encrypt secrets
    # with a key an attacker already has.
    SECRET_KEY: str = DEV_SECRET_KEY
    # Fernet key (urlsafe base64, 32 bytes). Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = DEV_ENCRYPTION_KEY
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    COOKIE_SECURE: bool = False  # set True behind HTTPS (forced on in production)
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    RATE_LIMIT_PER_MINUTE: int = 120
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10
    #: Only honour ``X-Forwarded-For`` when the app really sits behind a trusted proxy.
    #: Off by default: otherwise any client can pick its own rate-limit bucket.
    TRUST_PROXY_HEADERS: bool = False
    #: Expose /docs, /redoc and /openapi.json (off in production by default).
    ENABLE_API_DOCS: bool | None = None

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
    #: Chromium's renderer sandbox is what protects this host from a hostile page.
    #: Only turn it off where the container runtime forbids user namespaces.
    BROWSER_DISABLE_SANDBOX: bool = False
    BROWSER_ACTION_DELAY_MS: int = 250
    BROWSER_TIMEOUT_MS: int = 15000
    # Base URL the *browser* uses to reach the demo ATS (inside docker this is the backend service name)
    DEMO_ATS_BASE_URL: str = "http://localhost:8000"
    #: A real employer's system sends its "thank you for applying" mail *after* it has
    #: processed the submission, not inside the applicant's own HTTP request. The demo ATS
    #: models that delay, which also gives the submitting side time to record the
    #: application reference the mail quotes. Zero delivers it inline (used by the tests).
    DEMO_ATS_EMAIL_DELAY_SECONDS: float = 2.0

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

    @field_validator("GMAIL_SCOPES")
    @classmethod
    def _only_read_only_gmail_scopes(cls, scopes: list[str]) -> list[str]:
        """Refuse any Gmail scope outside the read-only allow-list (spec §22).

        The user-facing promise is that JobPilot can only *read* mail, so a scope
        cannot be widened through configuration — not even to ``gmail.modify``.
        """
        unexpected = [s for s in scopes if s.strip() not in ALLOWED_GMAIL_SCOPES]
        if unexpected:
            raise ValueError(
                "GMAIL_SCOPES may only contain read-only Gmail scopes; refused: " + ", ".join(sorted(unexpected))
            )
        if not scopes:
            raise ValueError("GMAIL_SCOPES cannot be empty")
        return [s.strip() for s in scopes]

    @model_validator(mode="after")
    def _reject_insecure_production_defaults(self) -> "Settings":
        """Never let a production deployment run on the published development keys."""
        if self.ENV != "production":
            return self
        problems: list[str] = []
        if self.SECRET_KEY == DEV_SECRET_KEY:
            problems.append("SECRET_KEY is still the published development default")
        if len(self.SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
            problems.append(f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters")
        if self.ENCRYPTION_KEY == DEV_ENCRYPTION_KEY:
            problems.append("ENCRYPTION_KEY is still the published development default")
        if any(origin.strip() == "*" for origin in self.CORS_ORIGINS):
            # CORSMiddleware runs with allow_credentials=True; a wildcard origin makes it
            # echo any site back, so a hostile page could drive the credentialed endpoints.
            problems.append("CORS_ORIGINS cannot contain '*' (credentials are allowed)")
        if problems:
            raise ValueError(
                "Refusing to start in production: " + "; ".join(problems) + ". Generate fresh values (see .env.example)."
            )
        # Cookies must not travel over plain HTTP once we are live.
        object.__setattr__(self, "COOKIE_SECURE", True)
        return self

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def docs_enabled(self) -> bool:
        """Whether the interactive API docs are served (off in production by default)."""
        if self.ENABLE_API_DOCS is not None:
            return self.ENABLE_API_DOCS
        return not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
