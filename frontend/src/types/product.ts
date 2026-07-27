import type { AnalysisStatus, MaturityState, RiskFlag } from "./analysis";

// One row of the Products list -- the app's home page (MVP lockdown Step 1).
export interface ProductSummary {
  id: string;
  name: string;
  updated_at: string;
  latest_run_id: string | null;
  latest_run_status: AnalysisStatus | null;
  latest_run_created_at: string | null;
  maturity: number | null;
  maturity_state: MaturityState | null;
  risk_flag: RiskFlag | null;
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
