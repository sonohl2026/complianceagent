import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.compliance_issue import ComplianceIssue
from app.models.crawl import CrawledPage, CrawlSnapshot
from app.models.enums import ComplianceIssueStatus, RiskLevel
from app.models.product import Product
from app.models.project import Project
from app.models.source_document import SourceDocument
from app.schemas.compliance_issue import ComplianceIssueRead
from app.schemas.product import ProductCreate, ProductRead
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.storage.file_storage import get_storage

_RISK_ORDER = {RiskLevel.CRITICAL: 0, RiskLevel.HIGH: 1, RiskLevel.MEDIUM: 2, RiskLevel.LOW: 3}

router = APIRouter()


@router.post("/projects", response_model=ProjectRead, status_code=201)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)) -> Project:
    project = Project(**payload.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(
    company_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
) -> list[Project]:
    query = select(Project).order_by(Project.name)
    if company_id is not None:
        query = query.where(Project.company_id == company_id)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/projects/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, db: AsyncSession = Depends(get_db)
) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Collect on-disk file paths before the cascade delete removes the rows
    # that reference them -- DB foreign keys cascade the relational data, but
    # nothing on the filesystem is cleaned up automatically.
    doc_paths = (
        await db.execute(
            select(SourceDocument.local_path).where(
                SourceDocument.project_id == project_id, SourceDocument.local_path.is_not(None)
            )
        )
    ).scalars().all()
    page_paths = (
        await db.execute(
            select(CrawledPage.html_path, CrawledPage.screenshot_path, CrawledPage.text_path)
            .join(CrawlSnapshot, CrawledPage.snapshot_id == CrawlSnapshot.id)
            .where(CrawlSnapshot.project_id == project_id)
        )
    ).all()

    await db.delete(project)
    await db.commit()

    storage = get_storage()
    for path in doc_paths:
        storage.delete(path)
    for html_path, screenshot_path, text_path in page_paths:
        for path in (html_path, screenshot_path, text_path):
            if path:
                storage.delete(path)


@router.post("/projects/{project_id}/products", response_model=ProductRead, status_code=201)
async def create_product(
    project_id: uuid.UUID, payload: ProductCreate, db: AsyncSession = Depends(get_db)
) -> Product:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    product = Product(company_id=project.company_id, **payload.model_dump())
    db.add(product)
    await db.flush()
    if project.default_product_id is None:
        project.default_product_id = product.id
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/projects/{project_id}/products", response_model=list[ProductRead])
async def list_products_for_project(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[Product]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(Product).where(Product.company_id == project.company_id).order_by(Product.name)
    )
    return list(result.scalars().all())


@router.get("/products/{product_id}/compliance-checklist", response_model=list[ComplianceIssueRead])
async def get_compliance_checklist(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ComplianceIssue]:
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    result = await db.execute(select(ComplianceIssue).where(ComplianceIssue.product_id == product_id))
    issues = list(result.scalars().all())
    # Open issues first (most urgent risk first within that), resolved issues
    # last (most recently resolved first) -- this is the ordering a checklist
    # UI actually wants: what still needs attention, up top.
    issues.sort(
        key=lambda i: (
            0 if i.status == ComplianceIssueStatus.OPEN else 1,
            _RISK_ORDER.get(i.risk, 99),
            -(i.resolved_at.timestamp() if i.resolved_at else 0),
        )
    )
    return issues
