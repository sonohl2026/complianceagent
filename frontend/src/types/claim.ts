export interface ExtractedClaim {
  id: string;
  project_id: string;
  project_name: string;
  source_document_id: string | null;
  source_chunk_id: string | null;
  exact_text: string;
  claim_category: string;
  express_or_implied: string;
  audience: string | null;
  evidence_status: string;
  intended_use_alignment: string | null;
  regulatory_status_alignment: string | null;
  risk: string;
  recommended_disposition: string;
  proposed_replacement: string | null;
  review_status: string;
  created_at: string;
}
