export type AnalysisStatus = "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED" | "CANCELLED";
export type Verdict = "GO" | "CONDITIONAL_GO" | "STOP";
export type RiskLevel = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

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
