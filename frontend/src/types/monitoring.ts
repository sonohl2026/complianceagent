export interface ScheduledRecrawl {
  id: string;
  project_id: string;
  start_url: string;
  crawl_settings_json: Record<string, unknown>;
  interval_hours: number;
  is_active: boolean;
  last_run_at: string | null;
  next_run_at: string;
  created_at: string;
}

export interface ScheduledRecrawlCreate {
  start_url: string;
  interval_hours: number;
  max_pages?: number;
  max_depth?: number;
  follow_subdomains?: boolean;
  include_pdfs?: boolean;
}

export interface Alert {
  id: string;
  project_id: string;
  project_name: string;
  crawl_snapshot_id: string;
  canonical_url: string;
  category: string;
  summary: string;
  acknowledged: boolean;
  created_at: string;
}
