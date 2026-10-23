"""FastAPI application factory.

Layering (spec §21)::

    Frontend → API routers → module services → AI / Browser / Adapters → DB
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.actor import ActorMiddleware
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # noqa: ANN001, ANN201
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/demo-ats"):
            # demo ATS pages are plain HTML forms; allow them to be framed by nothing, scripts inline.
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    configure_logging()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    logger.info("%s starting (env=%s, llm=%s)", settings.APP_NAME, settings.ENV, settings.LLM_PROVIDER)
    scheduler = None
    if os.getenv("RUN_SCHEDULER_IN_API", "false").lower() == "true":
        try:
            from app.worker.scheduler import build_scheduler

            scheduler = build_scheduler()
            scheduler.start()
            logger.info("In-process scheduler started")
        except Exception as exc:  # pragma: no cover
            logger.exception("Could not start in-process scheduler: %s", exc)
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    logger.info("%s shutting down", settings.APP_NAME)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description=(
            "JobPilot AI — discover relevant jobs across platforms, match them to your resume, "
            "prepare and autofill applications with human approval, and track every response."
        ),
        lifespan=lifespan,
        # The interactive docs enumerate every endpoint and schema; they are a
        # reconnaissance aid in production, so they are off there by default.
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    # Wraps everything but CORS (Starlette nests in reverse order of registration), so
    # the acting user is published before any handler runs and is still set while the
    # response is produced. Plain ASGI on purpose — see app/core/actor.py.
    app.add_middleware(ActorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-RateLimit-Remaining"],
    )
    register_exception_handlers(app)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV, "llm_provider": settings.LLM_PROVIDER}

    _include_routers(app)
    _mount_demo_ats(app)
    return app


def _include_routers(app: FastAPI) -> None:
    from app.modules.ai.router import router as ai_router
    from app.modules.applications.router import router as applications_router
    from app.modules.audit.router import router as audit_router
    from app.modules.automation.router import router as automation_router
    from app.modules.auth.router import router as auth_router
    from app.modules.browser.router import router as browser_router
    from app.modules.companies.router import router as companies_router
    from app.modules.dashboard.router import router as dashboard_router
    from app.modules.emails.router import router as emails_router
    from app.modules.integrations.router import router as integrations_router
    from app.modules.interviews.router import router as interviews_router
    from app.modules.jobs.router import router as jobs_router
    from app.modules.matching.router import router as matching_router
    from app.modules.notifications.router import router as notifications_router
    from app.modules.profiles.router import router as profiles_router
    from app.modules.resumes.router import router as resumes_router

    p = settings.API_PREFIX
    app.include_router(auth_router, prefix=f"{p}/auth", tags=["auth"])
    app.include_router(profiles_router, prefix=f"{p}", tags=["profile"])  # /profile, /preferences/job
    app.include_router(resumes_router, prefix=f"{p}/resumes", tags=["resumes"])
    app.include_router(companies_router, prefix=f"{p}/companies", tags=["companies"])
    app.include_router(jobs_router, prefix=f"{p}/jobs", tags=["jobs"])
    app.include_router(matching_router, prefix=f"{p}/matching", tags=["matching"])
    app.include_router(applications_router, prefix=f"{p}/applications", tags=["applications"])
    app.include_router(automation_router, prefix=f"{p}/automation", tags=["automation"])
    app.include_router(emails_router, prefix=f"{p}/emails", tags=["emails"])
    app.include_router(integrations_router, prefix=f"{p}/integrations", tags=["integrations"])
    app.include_router(dashboard_router, prefix=f"{p}/dashboard", tags=["dashboard"])
    app.include_router(interviews_router, prefix=f"{p}/interviews", tags=["interviews"])
    app.include_router(notifications_router, prefix=f"{p}/notifications", tags=["notifications"])
    app.include_router(audit_router, prefix=f"{p}/audit", tags=["audit"])
    app.include_router(ai_router, prefix=f"{p}/ai", tags=["ai"])
    app.include_router(browser_router, prefix=f"{p}/browser", tags=["browser"])
    from app.modules.ats.router import router as ats_router  # ats stream (resume studio)
    app.include_router(ats_router, prefix=f"{p}/ats", tags=["ats"])


def _mount_demo_ats(app: FastAPI) -> None:
    """The demo ATS is a tiny Greenhouse-style career site served by this backend so the
    Playwright autofill flow can be demonstrated end-to-end without touching third-party sites.

    It is deliberately unauthenticated (it plays the part of a third-party site), which
    makes it the only writable surface on this API that does not require a token. That is
    acceptable for a demo host but not for a production deployment, so it is never mounted
    when ``ENV=production``.
    """
    if settings.is_production:
        logger.info("Demo ATS not mounted (ENV=production)")
        return
    from app.demo_ats.router import router as demo_ats_router

    app.include_router(demo_ats_router, prefix="/demo-ats", tags=["demo-ats"], include_in_schema=False)


app = create_app()
