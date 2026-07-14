export interface Company {
  id: string;
  name: string;
  legal_name: string | null;
  website_url: string | null;
  description: string | null;
  headquarters: string | null;
  jurisdictions: string[];
  created_at: string;
  updated_at: string;
}

export interface CompanyCreate {
  name: string;
  legal_name?: string;
  website_url?: string;
  description?: string;
  headquarters?: string;
  jurisdictions?: string[];
}
