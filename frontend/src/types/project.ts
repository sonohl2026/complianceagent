export interface Project {
  id: string;
  company_id: string;
  name: string;
  description: string | null;
  default_product_id: string | null;
  jurisdiction: string | null;
  target_payers: string[];
  analysis_scope: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  company_id: string;
  name: string;
  description?: string;
  jurisdiction?: string;
}

export interface Product {
  id: string;
  company_id: string;
  name: string;
  description: string | null;
  product_type: string | null;
  regulatory_stage: string | null;
  fda_status: string | null;
  intended_use: string | null;
  indications_for_use: string | null;
  target_population: string | null;
  intended_user: string | null;
  site_of_service: string | null;
  care_setting: string | null;
  clinical_output: string | null;
  ai_role: string | null;
  hardware_version: string | null;
  software_version: string | null;
  model_version: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductCreate {
  name: string;
  description?: string;
  product_type?: string;
  regulatory_stage?: string;
  fda_status?: string;
  intended_use?: string;
}
