export interface ComplianceIssue {
  id: string;
  product_id: string;
  domain: string;
  title: string;
  description: string;
  risk: string;
  status: "OPEN" | "RESOLVED";
  first_detected_run_id: string | null;
  last_seen_run_id: string | null;
  resolved_run_id: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}
