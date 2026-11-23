
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.leads import router as leads_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.api.gmail import router as gmail_router
from app.api.automation import router as automation_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.emails import router as emails_router
from app.services.gmail_sync_service import (
    start_sync_scheduler,
    stop_sync_scheduler,
)
from app.services.automation_store import automation_store
from app.services.automation_service import (
    start_automation_worker,
    stop_automation_worker,
)

@asynccontextmanager
async def lifespan(app: FastAPI):

    setup_logging()
    settings.validate()
    automation_store.initialize()
    await start_sync_scheduler()
    await start_automation_worker()
    try:
        yield
    finally:
        await stop_automation_worker()
        await stop_sync_scheduler()


app = FastAPI(
    title="LeadFlow AI",
    description=(
        "AI-powered Lead Capture, "
        "Personalization and Automation System"
    ),
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_v1_compatibility_middleware(request: Request, call_next):
    """
    Ensure backwards and forwards compatibility for dashboard and API requests.
    If a request is sent to /dashboard/..., /leads..., /automation/..., /gmail/..., /auth/...
    without the /api/v1 prefix, transparently route it to /api/v1/...
    """
    path = request.scope.get("path", "")
    api_prefixes = ("/dashboard", "/leads", "/automation", "/gmail", "/auth")
    if not path.startswith("/api/v1") and any(path.startswith(prefix) for prefix in api_prefixes):
        request.scope["path"] = f"/api/v1{path}"

    return await call_next(request)


@app.get("/")
def root():

    return {
        "project": settings.PROJECT_NAME,
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME
    }


app.include_router(leads_router)
app.include_router(gmail_router)
app.include_router(automation_router)
app.include_router(emails_router)
app.include_router(auth_router)
app.include_router(dashboard_router)