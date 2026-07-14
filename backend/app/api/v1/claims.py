"""Claims Register (Milestone 7): claims were already being extracted and
persisted by the claim_extraction pipeline stage, but had no review UI at
all -- this is read/filter/mark-reviewed, not new extraction logic."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.claim import ExtractedClaim
from app.models.project import Project
from app.schemas.claim import ExtractedClaimRead, ExtractedClaimUpdate, ExtractedClaimWithProject

router = APIRouter()


@router.get("/claims", response_model=list[ExtractedClaimWithProject])
async def list_claims(
    project_id: uuid.UUID | None = None,
    risk: str | None = None,
    review_status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ExtractedClaimWithProject]:
    query = select(ExtractedClaim, Project.name).join(Project, ExtractedClaim.project_id == Project.id)
    if project_id is not None:
        query = query.where(ExtractedClaim.project_id == project_id)
    if risk is not None:
        query = query.where(ExtractedClaim.risk == risk)
    if review_status is not None:
        query = query.where(ExtractedClaim.review_status == review_status)
    query = query.order_by(ExtractedClaim.created_at.desc())

    rows = (await db.execute(query)).all()
    return [
        ExtractedClaimWithProject(
            **ExtractedClaimRead.model_validate(claim).model_dump(),
            project_name=project_name,
        )
        for claim, project_name in rows
    ]


@router.put("/claims/{claim_id}", response_model=ExtractedClaimRead)
async def update_claim(
    claim_id: uuid.UUID, payload: ExtractedClaimUpdate, db: AsyncSession = Depends(get_db)
) -> ExtractedClaim:
    claim = await db.get(ExtractedClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    claim.review_status = payload.review_status
    await db.commit()
    await db.refresh(claim)
    return claim
