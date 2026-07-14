export interface SearchResultChunk {
  chunk_id: string;
  document_id: string;
  document_title: string;
  collection_type: string;
  authority_level: string | null;
  text: string;
  citation_label: string;
  page_number: number | null;
  heading_path: string | null;
  score: number;
}
