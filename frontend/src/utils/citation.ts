// Citations from Stage 3 are sometimes a bare URL, sometimes
// "https://... (trailing context)" -- only the leading token up to
// whitespace is ever a real link. Shared by every place that renders a
// citation as a clickable source (pillar cards, billing codes, exports).
export function extractCitationUrl(citation: string | null | undefined): string | null {
  if (!citation) return null;
  const match = citation.match(/^(https?:\/\/\S+)/);
  return match ? match[1] : null;
}

// The CMS Physician Fee Schedule Look-up Tool -- the real, official,
// public source for the "Medicare rate" figures Billing Codes shows. Used
// as a fallback source link only when a given run has no more specific,
// evidence-grounded citation of its own for the coding pillar.
export const CMS_PFS_LOOKUP_URL = "https://www.cms.gov/medicare/physician-fee-schedule/search";
