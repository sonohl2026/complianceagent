export type CrawlStatus = "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED" | "CANCELLED";

export interface CrawlSnapshot {
  id: string;
  project_id: string;
  root_url: string;
  started_at: string | null;
  completed_at: string | null;
  status: CrawlStatus;
  page_count: number;
  crawl_settings_json: Record<string, unknown>;
  error_summary: string | null;
  previous_snapshot_id: string | null;
  created_at: string;
}

export interface CrawlSnapshotWithProject extends CrawlSnapshot {
  project_name: string;
}

export interface CrawledPage {
  id: string;
  url: string;
  canonical_url: string;
  title: string | null;
  http_status: number | null;
  content_type: string | null;
  sha256: string | null;
  word_count: number | null;
  robots_status: "ALLOWED" | "DISALLOWED" | "UNKNOWN";
  changed_from_prior: boolean | null;
  change_summary: string | null;
  source_document_id: string | null;
}

export interface CrawlCreateRequest {
  start_url: string;
  max_pages?: number;
  max_depth?: number;
  follow_subdomains?: boolean;
  include_pdfs?: boolean;
}

export interface CrawlDiffEntry {
  canonical_url: string;
  change_type: "added" | "removed" | "changed" | "unchanged";
  old_title: string | null;
  new_title: string | null;
}

export interface CrawlDiffResponse {
  previous_snapshot_id: string | null;
  current_snapshot_id: string;
  summary: Record<string, number>;
  entries: CrawlDiffEntry[];
}
