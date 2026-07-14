"""Cross-company/project summary for the home dashboard (Milestone 7).
Everything here is a read-only aggregate over existing tables -- no new
domain model, this just answers "what's going on across everything" in one
request instead of the frontend fanning out to a dozen per-project calls."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import AnalysisRun
from app.models.company import Company
from app.models.compliance_issue import ComplianceIssue
from app.models.enums import ComplianceIssueStatus
from app.models.product import Product
from app.models.project import Project
from app.schemas.dashboard import DashboardSummary, RecentAnalysisRow

router = APIRouter()


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def get_dashboard_summary(db: AsyncSession = Depends(get_db)) -> DashboardSummary:
    company_count = await db.scalar(select(func.count()).select_from(Company)) or 0
    project_count = await db.scalar(select(func.count()).select_from(Project)) or 0
    product_count = await db.scalar(select(func.count()).select_from(Product)) or 0
    analysis_count = await db.scalar(select(func.count()).select_from(AnalysisRun)) or 0
    open_issue_count = (
        await db.scalar(
            select(func.count())
            .select_from(ComplianceIssue)
            .where(ComplianceIssue.status == ComplianceIssueStatus.OPEN)
        )
        or 0
    )

    rows = (
        await db.execute(
            select(AnalysisRun, Project.name, Product.name)
            .join(Project, AnalysisRun.project_id == Project.id)
            .outerjoin(Product, AnalysisRun.product_id == Product.id)
            .order_by(AnalysisRun.created_at.desc())
            .limit(10)
        )
    ).all()

    recent_analyses = [
        RecentAnalysisRow(
            id=run.id,
            project_id=run.project_id,
            project_name=project_name,
            product_name=product_name,
            status=run.status.value,
            overall_verdict=run.overall_verdict.value if run.overall_verdict else None,
            overall_risk=run.overall_risk.value if run.overall_risk else None,
            readiness_score=run.readiness_score,
            created_at=run.created_at,
        )
        for run, project_name, product_name in rows
    ]

    return DashboardSummary(
        company_count=company_count,
        project_count=project_count,
        product_count=product_count,
        analysis_count=analysis_count,
        open_compliance_issue_count=open_issue_count,
        recent_analyses=recent_analyses,
    )
