export type CollectionType = "COMPANY" | "AUTHORITY" | "THIRD_PARTY" | "COMPETITOR";
export type ParseStatus = "PENDING" | "PROCESSING" | "COMPLETE" | "FAILED" | "QUARANTINED";
export type EmbeddingStatus = "PENDING" | "PROCESSING" | "COMPLETE" | "FAILED" | "STALE";
export type ConfidentialityLevel = "PUBLIC" | "INTERNAL" | "RESTRICTED";

export interface SourceDocument {
  id: string;
  project_id: string | null;
  collection_type: CollectionType;
  source_type: string | null;
  authority_level: string | null;
  title: string;
  issuer: string | null;
  url: string | null;
  original_filename: string | null;
  mime_type: string | null;
  jurisdiction: string | null;
  document_category: string | null;
  publication_date: string | null;
  effective_date: string | null;
  expiration_date: string | null;
  version: string | null;
  is_current: boolean;
  is_superseded: boolean;
  sha256: string | null;
  parse_status: ParseStatus;
  embedding_status: EmbeddingStatus;
  confidentiality_level: ConfidentialityLevel;
  parse_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface SourceDocumentWithProject extends SourceDocument {
  project_name: string | null;
}

export interface SourceChunk {
  id: string;
  document_id: string;
  chunk_index: number;
  text: string;
  token_count: number | null;
  page_number: number | null;
  section_title: string | null;
  heading_path: string | null;
  citation_label: string;
}

export type JobStatus = "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED" | "CANCELLED";

export interface Job {
  id: string;
  job_type: string;
  project_id: string | null;
  related_id: string | null;
  status: JobStatus;
  progress_percent: number;
  current_stage: string | null;
  logs: Array<{ stage?: string; message: string }>;
  error_summary: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}
