"""add compliance_issues (durable, product-level compliance checklist tracked across runs)

Revision ID: 0007_compliance_issues
Revises: 0006_widen_code_cols
Create Date: 2026-07-13

Supports the "auto-checked-off checklist" feature: unlike Finding (scoped to
one AnalysisRun and effectively write-once), ComplianceIssue persists across
runs for a given product so a re-run after a small site/document tweak can
show what's newly resolved vs. still open, without generating a whole new
report to find out. Reconciliation logic lives in
app.services.analysis.checklist, called from the end of run_analysis.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_compliance_issues"
down_revision: Union[str, None] = "0006_widen_code_cols"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Distinct type names per this project's established convention (see
# 0004_analysis_tables: finding_risk vs risk_level vs claim_risk are all
# separate Postgres enum types for the same conceptual RiskLevel values,
# one per column, to avoid any cross-table type-reuse entanglement).
compliance_issue_domain_enum = postgresql.ENUM(
    "PRODUCT_DEFINITION", "FDA_REGULATORY", "CLINICAL_EVIDENCE", "QUALITY_SYSTEM", "MARKETING",
    "CODING", "COVERAGE", "PAYMENT", "BILLING", "PROVIDER_ECONOMICS", "MANUFACTURER_ECONOMICS",
    "FRAUD_ABUSE", "PRIVACY", "CYBERSECURITY", "RESEARCH_COMPLIANCE", "POSTMARKET",
    name="compliance_issue_domain",
)
compliance_issue_risk_enum = postgresql.ENUM("CRITICAL", "HIGH", "MEDIUM", "LOW", name="compliance_issue_risk")
compliance_issue_status_enum = postgresql.ENUM("OPEN", "RESOLVED", name="compliance_issue_status")


def upgrade() -> None:
    # No explicit enum .create() calls here: op.create_table() below already
    # auto-creates each enum type the first time it's used in a column (this
    # is what every other migration in this project relies on -- see
    # 0004_analysis_tables). Calling .create() explicitly AND embedding the
    # enum in the column both trying to create the same type in one
    # transaction is exactly what caused a real
    # "type ... already exists" failure in production.
    op.create_table(
        "compliance_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", compliance_issue_domain_enum, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("normalized_title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk", compliance_issue_risk_enum, nullable=False),
        sa.Column("status", compliance_issue_status_enum, nullable=False, server_default="OPEN"),
        sa.Column("first_detected_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="SET NULL")),
        sa.Column("last_seen_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="SET NULL")),
        sa.Column("resolved_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="SET NULL")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_compliance_issues_normalized_title", "compliance_issues", ["normalized_title"])
    op.create_index("ix_compliance_issues_product_id", "compliance_issues", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_compliance_issues_product_id", table_name="compliance_issues")
    op.drop_index("ix_compliance_issues_normalized_title", table_name="compliance_issues")
    op.drop_table("compliance_issues")
    bind = op.get_bind()
    compliance_issue_status_enum.drop(bind, checkfirst=True)
    compliance_issue_risk_enum.drop(bind, checkfirst=True)
    compliance_issue_domain_enum.drop(bind, checkfirst=True)
