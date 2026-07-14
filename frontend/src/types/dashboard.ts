export interface RecentAnalysisRow {
  id: string;
  project_id: string;
  project_name: string;
  product_name: string | null;
  status: string;
  overall_verdict: string | null;
  overall_risk: string | null;
  readiness_score: number | null;
  created_at: string;
}

export interface DashboardSummary {
  company_count: number;
  project_count: number;
  product_count: number;
  analysis_count: number;
  open_compliance_issue_count: number;
  recent_analyses: RecentAnalysisRow[];
}
