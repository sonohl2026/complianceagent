import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import AnalysisRun
from app.models.product import Product
from app.schemas.analysis import AnalysisRunRead
from app.schemas.product import ProductRead
from app.schemas.product_summary import ProductSummary

router = APIRouter()


async def _latest_run(db: AsyncSession, product_id: uuid.UUID) -> AnalysisRun | None:
    result = await db.execute(
        select(AnalysisRun)
        .where(AnalysisRun.product_id == product_id, AnalysisRun.analysis_type == "quick_scan")
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


@router.get("/products", response_model=list[ProductSummary])
async def list_products(db: AsyncSession = Depends(get_db)) -> list[ProductSummary]:
    """MVP lockdown Step 1: the app's home page. One row per Product, each
    carrying just enough of its latest quick_scan run to sort/scan by --
    the full result lives on the product's own results page."""
    products = (await db.execute(select(Product).order_by(Product.updated_at.desc()))).scalars().all()
    summaries = []
    for product in products:
        latest = await _latest_run(db, product.id)
        scores = (latest.quick_scan_result_json.get("scores") if latest else None) or {}
        summaries.append(
            ProductSummary(
                id=product.id,
                name=product.name,
                updated_at=product.updated_at,
                latest_run_id=latest.id if latest else None,
                latest_run_status=latest.status if latest else None,
                latest_run_created_at=latest.created_at if latest else None,
                maturity=scores.get("maturity"),
                maturity_state=scores.get("maturity_state"),
                risk_flag=scores.get("risk_flag"),
            )
        )
    return summaries


@router.get("/products/{product_id}", response_model=ProductRead)
async def get_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Product:
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/products/{product_id}/runs", response_model=list[AnalysisRunRead])
async def list_product_runs(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[AnalysisRun]:
    result = await db.execute(
        select(AnalysisRun)
        .where(AnalysisRun.product_id == product_id, AnalysisRun.analysis_type == "quick_scan")
        .order_by(AnalysisRun.created_at.desc())
    )
    return list(result.scalars().all())
