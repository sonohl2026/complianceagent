import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.schemas.retrieval import SearchRequest, SearchResultChunk
from app.services.retrieval.hybrid_search import RetrievalFilter, hybrid_search

router = APIRouter()


@router.post("/projects/{project_id}/search", response_model=list[SearchResultChunk])
async def search_project(
    project_id: uuid.UUID, payload: SearchRequest, db: AsyncSession = Depends(get_db)
) -> list[SearchResultChunk]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    filters = RetrievalFilter(project_id=project_id, collection_types=payload.collection_types)
    results = await hybrid_search(db, payload.query, filters, top_k=payload.top_k)
    return [SearchResultChunk(**result.__dict__) for result in results]
