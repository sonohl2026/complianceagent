import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import JobStatus, RiskLevel, Verdict


class AnalysisCreateRequest(BaseModel):
    product_id: uuid.UUID | None = None
    analysis_type: str = "FULL_COMPLIANCE_ANALYSIS"


class AnalysisRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    product_id: uuid.UUID | None
    analysis_type: str
    status: JobStatus
    current_stage: str | None
    started_at: datetime | None
    completed_at: datetime | None
    analysis_model: str | None
    model_response_identifier: str | None
    source_cutoff_date: date | None
    overall_verdict: Verdict | None
    overall_risk: RiskLevel | None
    readiness_score: int | None
    readiness_score_note: str | None
    confidence_score: int | None
    executive_summary: str | None
    critical_blockers: list[str]
    missing_inputs: list[str]
    priority_actions: list[str]
    required_reviewers: list[str]
    token_usage_json: dict
    cost_json: dict
    error_summary: str | None
    created_at: datetime
    quick_scan_result_json: dict
    retrieval_bundle_json: dict
    retrieval_progress_json: dict
    overrides_json: dict
    revision: int


class CitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID | None
    chunk_id: uuid.UUID | None
    citation_role: str
    quoted_text: str | None
    page_number: int | None
    section_title: str | None
    url: str | None
    supports_claim: bool
    verification_status: str


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    domain: str
    title: str
    description: str
    finding_type: str | None
    status: str
    risk: str
    verdict: str | None
    verified_fact: str | None
    missing_information: list[str]
    applicable_requirement: str | None
    recommended_action: str | None
    responsible_owner: str | None
    priority: int | None
    due_timing: str | None
    confidence: int | None
    human_review_required: bool
    citations: list[CitationRead] = []


class CodingRequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requirement_name: str
    requirement_text: str
    verified_company_fact: str | None
    status: str
    gap: str | None
    owner: str | None


class CodingCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code_system: str
    code: str | None
    code_year: str | None
    descriptor_reference: str | None
    service_definition: str
    eligibility_status: str
    coverage_status: str | None
    payment_status: str | None
    billing_status: str | None
    major_gaps: list[str]
    expert_review_required: bool
    requirements: list[CodingRequirementRead] = []
