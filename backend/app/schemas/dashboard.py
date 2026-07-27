import uuid
from datetime import datetime

from pydantic import BaseModel


class RecentAnalysisRow(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    project_name: str | None
    product_name: str | None
    status: str
    overall_verdict: str | None
    overall_risk: str | None
    readiness_score: int | None
    created_at: datetime


class DashboardSummary(BaseModel):
    company_count: int
    project_count: int
    product_count: int
    analysis_count: int
    open_compliance_issue_count: int
    recent_analyses: list[RecentAnalysisRow]
