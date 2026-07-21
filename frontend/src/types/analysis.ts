export type AnalysisStatus = "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED" | "CANCELLED";
export type Verdict = "GO" | "CONDITIONAL_GO" | "STOP";
export type RiskLevel = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

// quick_scan pipeline (v2 spec section 4) -- a different, fixed shape from
// the legacy Finding/CodingCandidate rows, stored as JSON on the same
// AnalysisRun row rather than a relational schema.
export type MaturityState = "SCORED" | "NOT_SCORED";
export type PillarStatus = "VERIFIED_POSITIVE" | "VERIFIED_NEGATIVE" | "MIXED" | "UNKNOWN" | "NA" | "RETRIEVAL_FAILURE";
export type PillarName = "fda_status" | "coding" | "coverage" | "payment" | "evidence" | "billing_workflow";
export type RiskFlag = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type DevStage =
  | "concept"
  | "investigational"
  | "submission_pending"
  | "authorized_prelaunch"
  | "commercial"
  | "restricted_or_recalled";

export interface QuickScanIdentifier {
  type: "510k" | "pma" | "denovo" | "product_code" | "udi" | "ncd" | "lcd" | "cpt" | "hcpcs";
  value: string;
  match_confidence: "exact" | "probable" | "uncertain";
}

export interface QuickScanPillar {
  pillar: PillarName;
  status: PillarStatus;
  score: number | null;
  finding: string;
  detail: string;
  citation: string | null;
  gap: string | null;
  action: "PROCEED" | "FIX" | "INVESTIGATE" | null;
}

export interface QuickScanAssessment {
  product: {
    name: string;
    manufacturer: string;
    fda_status: string;
    identifiers: QuickScanIdentifier[];
    dev_stage: DevStage;
  };
  scores: {
    maturity: number | null;
    maturity_state: MaturityState;
    not_scored_reason: string | null;
    assessment_coverage_pct: number;
    research_confidence: number;
    risk_flag: RiskFlag;
    stage_context: string;
  };
  pillars: QuickScanPillar[];
  top_gaps: string[];
  next_steps: string[];
  disclaimer: string;
}

export interface RetrievalProgressEntry {
  status: "HIT" | "MISS" | "RETRIEVAL_FAILURE";
  latency_ms: number;
  data: Record<string, unknown> | null;
  error: string | null;
  match_confidence: string | null;
}

export interface AnalysisRun {
  id: string;
  project_id: string;
  product_id: string | null;
  analysis_type: string;
  status: AnalysisStatus;
  current_stage: string | null;
  started_at: string | null;
  completed_at: string | null;
  analysis_model: string | null;
  model_response_identifier: string | null;
  source_cutoff_date: string | null;
  overall_verdict: Verdict | null;
  overall_risk: RiskLevel | null;
  readiness_score: number | null;
  readiness_score_note: string | null;
  confidence_score: number | null;
  executive_summary: string | null;
  critical_blockers: string[];
  missing_inputs: string[];
  priority_actions: string[];
  required_reviewers: string[];
  token_usage_json: Record<string, { prompt_tokens: number; completion_tokens: number; total_tokens: number }>;
  cost_json: Record<string, number>;
  error_summary: string | null;
  created_at: string;
  quick_scan_result_json: QuickScanAssessment | Record<string, never>;
  retrieval_bundle_json: Record<string, unknown>;
  retrieval_progress_json: Record<string, RetrievalProgressEntry>;
  overrides_json: Record<string, { value: string; edited_at: string }>;
  revision: number;
}

export interface Citation {
  id: string;
  document_id: string | null;
  chunk_id: string | null;
  citation_role: string;
  quoted_text: string | null;
  page_number: number | null;
  section_title: string | null;
  url: string | null;
  supports_claim: boolean;
  verification_status: string;
}

export interface Finding {
  id: string;
  analysis_run_id: string;
  domain: string;
  title: string;
  description: string;
  finding_type: string | null;
  status: string;
  risk: string;
  verdict: string | null;
  verified_fact: string | null;
  missing_information: string[];
  applicable_requirement: string | null;
  recommended_action: string | null;
  responsible_owner: string | null;
  priority: number | null;
  due_timing: string | null;
  confidence: number | null;
  human_review_required: boolean;
  citations: Citation[];
}

export interface CodingRequirement {
  id: string;
  requirement_name: string;
  requirement_text: string;
  verified_company_fact: string | null;
  status: string;
  gap: string | null;
  owner: string | null;
}

export interface CodingCandidate {
  id: string;
  code_system: string;
  code: string | null;
  code_year: string | null;
  descriptor_reference: string | null;
  service_definition: string;
  eligibility_status: string;
  coverage_status: string | null;
  payment_status: string | null;
  billing_status: string | null;
  major_gaps: string[];
  expert_review_required: boolean;
  requirements: CodingRequirement[];
}
