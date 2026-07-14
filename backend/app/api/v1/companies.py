import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate

router = APIRouter()


@router.post("/companies", response_model=CompanyRead, status_code=201)
async def create_company(payload: CompanyCreate, db: AsyncSession = Depends(get_db)) -> Company:
    company = Company(**payload.model_dump())
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


@router.get("/companies", response_model=list[CompanyRead])
async def list_companies(db: AsyncSession = Depends(get_db)) -> list[Company]:
    result = await db.execute(select(Company).order_by(Company.name))
    return list(result.scalars().all())


@router.get("/companies/{company_id}", response_model=CompanyRead)
async def get_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.put("/companies/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: uuid.UUID, payload: CompanyUpdate, db: AsyncSession = Depends(get_db)
) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    await db.commit()
    await db.refresh(company)
    return company


@router.delete("/companies/{company_id}", status_code=204)
async def delete_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    await db.delete(company)
    await db.commit()
