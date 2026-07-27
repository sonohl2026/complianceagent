export interface AppSettings {
  openrouter_api_key_configured: boolean;
  openrouter_api_key_masked: string;
  brave_search_api_key_configured: boolean;
  brave_search_api_key_masked: string;
  openrouter_model: string;
  openrouter_extraction_model: string;
  openrouter_synthesis_model: string;
  openrouter_citation_model: string;
  openrouter_zdr: boolean;
  openrouter_prompt_caching: boolean;
  allowed_model_slugs: string[];
  redact_emails: boolean;
  redact_phone_numbers: boolean;
  redact_patient_identifiers: boolean;
  exclude_restricted_documents: boolean;
  allow_ocr: boolean;
  allow_lan_access: boolean;
  cms_license_accepted: boolean;
  cpt_license: boolean;
  local_data_notice: string;
}

export interface AppSettingsUpdate {
  openrouter_api_key?: string;
  brave_search_api_key?: string;
  openrouter_model?: string;
  openrouter_extraction_model?: string;
  openrouter_synthesis_model?: string;
  openrouter_citation_model?: string;
  openrouter_zdr?: boolean;
  openrouter_prompt_caching?: boolean;
  redact_emails?: boolean;
  redact_phone_numbers?: boolean;
  redact_patient_identifiers?: boolean;
  exclude_restricted_documents?: boolean;
  allow_ocr?: boolean;
  allow_lan_access?: boolean;
  cms_license_accepted?: boolean;
  cpt_license?: boolean;
}
