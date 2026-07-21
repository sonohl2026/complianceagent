from fastapi import APIRouter

from app.api.v1 import (
    analyses,
    authority,
    companies,
    crawls,
    dashboard,
    documents,
    health,
    jobs,
    metrics,
    monitoring,
    projects,
    prompts,
    quick_scans,
    retrieval,
    settings,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(companies.router, tags=["companies"])
api_router.include_router(projects.router, tags=["projects"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(authority.router, tags=["authority"])
api_router.include_router(retrieval.router, tags=["retrieval"])
api_router.include_router(crawls.router, tags=["crawls"])
api_router.include_router(analyses.router, tags=["analyses"])
api_router.include_router(quick_scans.router, tags=["quick_scans"])
api_router.include_router(jobs.router, tags=["jobs"])
api_router.include_router(prompts.router, tags=["prompts"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(monitoring.router, tags=["monitoring"])
api_router.include_router(metrics.router, tags=["metrics"])
