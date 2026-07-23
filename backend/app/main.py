from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.config import get_settings
from app.services.quick_scan.model_tier import warn_if_tier_split_inactive
from app.services.storage.settings_store import load_runtime_settings

settings = get_settings()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Loud on purpose -- this exact state (both model-tier settings empty,
    # Stage 1 and Stage 3 silently sharing one model) went unnoticed for a
    # full week on this deployment with nothing surfacing it anywhere.
    warn_if_tier_split_inactive(load_runtime_settings(), context="startup")
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Local decision-support tool for medtech regulatory and reimbursement "
        "readiness analysis. Not legal, regulatory, coding, or billing advice."
    ),
    lifespan=_lifespan,
)

# Local-first: the frontend dev server is the only expected browser origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{settings.frontend_port}",
        f"http://127.0.0.1:{settings.frontend_port}",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


app.include_router(api_router)
