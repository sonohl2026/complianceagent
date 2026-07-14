"""add prompt_versions, analysis_runs, findings, citations, extracted_claims,
coding_candidates, coding_requirements; add projects.system_prompt_version_id FK

Revision ID: 0004_analysis_tables
Revises: 0003_crawl_tables
Create Date: 2026-07-02

Hand-authored and cross-checked against app.models via the same mock-engine
DDL-dump technique used for earlier migrations. No FK cycle this time (unlike
0001): prompt_versions -> analysis_runs -> findings -> citations, and
analysis_runs -> coding_candidates -> coding_requirements, all one direction.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_analysis_tables"
down_revision: Union[str, None] = "0003_crawl_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

analysis_status_enum = postgresql.ENUM(
    "QUEUED", "RUNNING", "COMPLETE", "FAILED", "CANCELLED", name="analysis_status"
)
verdict_enum = postgresql.ENUM("GO", "CONDITIONAL_GO", "STOP", name="verdict")
risk_level_enum = postgresql.ENUM("CRITICAL", "HIGH", "MEDIUM", "LOW", name="risk_level")
finding_domain_enum = postgresql.ENUM(
    "PRODUCT_DEFINITION", "FDA_REGULATORY", "CLINICAL_EVIDENCE", "QUALITY_SYSTEM", "MARKETING",
    "CODING", "COVERAGE", "PAYMENT", "BILLING", "PROVIDER_ECONOMICS", "MANUFACTURER_ECONOMICS",
    "FRAUD_ABUSE", "PRIVACY", "CYBERSECURITY", "RESEARCH_COMPLIANCE", "POSTMARKET",
    name="finding_domain",
)
finding_risk_enum = postgresql.ENUM("CRITICAL", "HIGH", "MEDIUM", "LOW", name="finding_risk")
finding_verdict_enum = postgresql.ENUM("GO", "CONDITIONAL_GO", "STOP", name="finding_verdict")
citation_role_enum = postgresql.ENUM(
    "COMPANY_EVIDENCE", "CONTROLLING_AUTHORITY", "SUPPORTING_AUTHORITY", "CONTRADICTORY_EVIDENCE",
    "SECONDARY_CONTEXT", name="citation_role",
)
citation_verification_status_enum = postgresql.ENUM(
    "VERIFIED", "UNVERIFIED", "FAILED", name="citation_verification_status"
)
claim_category_enum = postgresql.ENUM(
    "PRODUCT_CONFIGURATION", "TECHNICAL_CAPABILITY", "TECHNICAL_PERFORMANCE", "ALGORITHMIC",
    "CLINICAL_PERFORMANCE", "SAFETY", "EFFECTIVENESS", "DIAGNOSTIC", "SCREENING", "MONITORING",
    "TREATMENT", "CLINICAL_UTILITY", "HEALTH_OUTCOME", "WORKFLOW", "ECONOMIC", "ACCESS", "EQUITY",
    "COMPARISON", "SUPERIORITY", "REGULATORY_STATUS", "TRIAL_STATUS", "AVAILABILITY", "PRICING",
    "COVERAGE", "CODING", "PAYMENT", "ENDORSEMENT", "TESTIMONIAL", "THIRD_PARTY_STATISTIC",
    "DISEASE_AWARENESS", "FUTURE_LOOKING", name="claim_category",
)
express_or_implied_enum = postgresql.ENUM("EXPRESS", "IMPLIED", "BOTH", name="express_or_implied")
claim_evidence_status_enum = postgresql.ENUM(
    "VERIFIED", "LIKELY", "CONDITIONAL", "UNRESOLVED", "MISSING", "CONFLICTING", "STALE",
    "NOT_APPLICABLE", name="claim_evidence_status",
)
claim_risk_enum = postgresql.ENUM("CRITICAL", "HIGH", "MEDIUM", "LOW", name="claim_risk")
claim_disposition_enum = postgresql.ENUM(
    "RETAIN", "QUALIFY", "REWRITE", "REMOVE", "QUARANTINE", name="claim_disposition"
)
coding_eligibility_status_enum = postgresql.ENUM(
    "POTENTIALLY_ALIGNED", "CONDITIONALLY_ALIGNED", "NOT_CURRENTLY_SUPPORTED", "NOT_APPLICABLE",
    "EXPERT_REVIEW_REQUIRED", name="coding_eligibility_status",
)


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, server_default="master_system_prompt"),
        sa.Column("version_label", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("change_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "extracted_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_documents.id", ondelete="SET NULL")),
        sa.Column("source_chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_chunks.id", ondelete="SET NULL")),
        sa.Column("exact_text", sa.Text(), nullable=False),
        sa.Column("claim_category", claim_category_enum, nullable=False),
        sa.Column("express_or_implied", express_or_implied_enum, nullable=False),
        sa.Column("audience", sa.String(255)),
        sa.Column("evidence_status", claim_evidence_status_enum, nullable=False),
        sa.Column("intended_use_alignment", sa.String(64)),
        sa.Column("regulatory_status_alignment", sa.String(64)),
        sa.Column("risk", claim_risk_enum, nullable=False),
        sa.Column("recommended_disposition", claim_disposition_enum, nullable=False),
        sa.Column("proposed_replacement", sa.Text()),
        sa.Column("review_status", sa.String(32), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL")),
        sa.Column("analysis_type", sa.String(64), nullable=False, server_default="FULL_COMPLIANCE_ANALYSIS"),
        sa.Column("status", analysis_status_enum, nullable=False, server_default="QUEUED"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("system_prompt_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_versions.id", ondelete="SET NULL")),
        sa.Column("analysis_model", sa.String(255)),
        sa.Column("model_provider", sa.String(64), nullable=False, server_default="openrouter"),
        sa.Column("model_response_identifier", sa.String(255)),
        sa.Column("source_cutoff_date", sa.Date()),
        sa.Column("input_snapshot_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("overall_verdict", verdict_enum),
        sa.Column("overall_risk", risk_level_enum),
        sa.Column("readiness_score", sa.Integer()),
        sa.Column("confidence_score", sa.Integer()),
        sa.Column("executive_summary", sa.Text()),
        sa.Column("critical_blockers", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("missing_inputs", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("priority_actions", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("required_reviewers", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("token_usage_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("cost_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_summary", sa.Text()),
        sa.Column("current_stage", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", finding_domain_enum, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("finding_type", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("risk", finding_risk_enum, nullable=False),
        sa.Column("verdict", finding_verdict_enum),
        sa.Column("verified_fact", sa.Text()),
        sa.Column("missing_information", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("applicable_requirement", sa.Text()),
        sa.Column("recommended_action", sa.Text()),
        sa.Column("responsible_owner", sa.String(255)),
        sa.Column("priority", sa.Integer()),
        sa.Column("due_timing", sa.String(255)),
        sa.Column("confidence", sa.Integer()),
        sa.Column("human_review_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "coding_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_system", sa.String(64), nullable=False),
        sa.Column("code", sa.String(32)),
        sa.Column("code_year", sa.String(16)),
        sa.Column("descriptor_reference", sa.Text()),
        sa.Column("service_definition", sa.Text(), nullable=False),
        sa.Column("eligibility_status", coding_eligibility_status_enum, nullable=False),
        sa.Column("coverage_status", sa.String(64)),
        sa.Column("payment_status", sa.String(64)),
        sa.Column("billing_status", sa.String(64)),
        sa.Column("major_gaps", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("expert_review_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_documents.id", ondelete="SET NULL")),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_chunks.id", ondelete="SET NULL")),
        sa.Column("citation_role", citation_role_enum, nullable=False),
        sa.Column("quoted_text", sa.Text()),
        sa.Column("page_number", sa.Integer()),
        sa.Column("section_title", sa.String(512)),
        sa.Column("url", sa.String(2048)),
        sa.Column("accessed_at", sa.DateTime(timezone=True)),
        sa.Column("supports_claim", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("verification_status", citation_verification_status_enum, nullable=False, server_default="UNVERIFIED"),
    )

    op.create_table(
        "coding_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("coding_candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("coding_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requirement_name", sa.String(255), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("verified_company_fact", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("company_source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_documents.id", ondelete="SET NULL")),
        sa.Column("authority_source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_documents.id", ondelete="SET NULL")),
        sa.Column("gap", sa.Text()),
        sa.Column("owner", sa.String(255)),
    )

    op.create_foreign_key(
        "fk_projects_system_prompt_version_id",
        "projects",
        "prompt_versions",
        ["system_prompt_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_system_prompt_version_id", "projects", type_="foreignkey")
    op.drop_table("coding_requirements")
    op.drop_table("citations")
    op.drop_table("coding_candidates")
    op.drop_table("findings")
    op.drop_table("analysis_runs")
    op.drop_table("extracted_claims")
    op.drop_table("prompt_versions")

    bind = op.get_bind()
    coding_eligibility_status_enum.drop(bind, checkfirst=True)
    claim_disposition_enum.drop(bind, checkfirst=True)
    claim_risk_enum.drop(bind, checkfirst=True)
    claim_evidence_status_enum.drop(bind, checkfirst=True)
    express_or_implied_enum.drop(bind, checkfirst=True)
    claim_category_enum.drop(bind, checkfirst=True)
    citation_verification_status_enum.drop(bind, checkfirst=True)
    citation_role_enum.drop(bind, checkfirst=True)
    finding_verdict_enum.drop(bind, checkfirst=True)
    finding_risk_enum.drop(bind, checkfirst=True)
    finding_domain_enum.drop(bind, checkfirst=True)
    risk_level_enum.drop(bind, checkfirst=True)
    verdict_enum.drop(bind, checkfirst=True)
    analysis_status_enum.drop(bind, checkfirst=True)
