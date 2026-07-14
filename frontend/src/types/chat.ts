export interface ChatCitation {
  role: string;
  document_title: string | null;
  section_title: string | null;
  page_number: number | null;
  url: string | null;
  quoted_text: string | null;
}

export interface ChatMessage {
  id: string;
  project_id: string;
  role: "user" | "assistant";
  content: string;
  citations_json: ChatCitation[];
  created_at: string;
}
