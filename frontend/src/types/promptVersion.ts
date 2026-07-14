export interface PromptVersionSummary {
  id: string;
  version_label: string;
  is_active: boolean;
  change_summary: string | null;
  created_at: string;
}

export interface PromptVersionDetail extends PromptVersionSummary {
  content: string;
  word_count: number;
  character_count: number;
}
