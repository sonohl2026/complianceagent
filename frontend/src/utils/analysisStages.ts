// Mirrors the stage order in app/services/analysis/pipeline.py::run_analysis
// (set_stage() calls) -- kept here rather than fetched from the API since the
// backend doesn't expose stage position, only the current stage name.
// Was 11 stages; regulatory/coverage/payment/billing/marketing analysis
// were merged into one "domain_analysis" call as a cost optimization
// (see docs/data-model.md). claim_extraction and coding_analysis run
// concurrently (both only depend on product_facts, not on each other) under
// one combined "claim_extraction_and_coding" progress step.
const ANALYSIS_STAGE_ORDER = [
  "input_audit",
  "product_fact_extraction",
  "claim_extraction_and_coding",
  "domain_analysis",
  "synthesis",
  "citation_audit",
];

const STAGE_LABELS: Record<string, string> = {
  input_audit: "Input audit",
  product_fact_extraction: "Product fact extraction",
  claim_extraction_and_coding: "Claim extraction & coding analysis",
  domain_analysis: "Domain analysis",
  synthesis: "Synthesis",
  citation_audit: "Citation audit",
};

// quick_scan (app/services/quick_scan/pipeline.py::run_quick_scan) has its
// own, much shorter 3-stage sequence -- kept separate from
// ANALYSIS_STAGE_ORDER above since the two pipelines' stage names don't
// overlap and mixing them into one ordered list would misnumber both.
const QUICK_SCAN_STAGE_ORDER = ["stage1_extraction", "retrieval", "stage3_synthesis"];

const QUICK_SCAN_STAGE_LABELS: Record<string, string> = {
  stage1_extraction: "Identifying product",
  retrieval: "Retrieving evidence (openFDA, CMS)",
  stage3_synthesis: "Synthesizing assessment",
};

/** "synthesis" -> "Synthesis (5/6)". Falls back to the raw stage name for
 * anything not in either stage list (e.g. "complete", "cancelled"), and to
 * "starting…" when there's no stage yet. */
export function formatAnalysisStage(stage: string | null | undefined): string {
  if (!stage) return "starting…";
  const quickScanIndex = QUICK_SCAN_STAGE_ORDER.indexOf(stage);
  if (quickScanIndex !== -1) {
    return `${QUICK_SCAN_STAGE_LABELS[stage]} (${quickScanIndex + 1}/${QUICK_SCAN_STAGE_ORDER.length})`;
  }
  const index = ANALYSIS_STAGE_ORDER.indexOf(stage);
  if (index === -1) return stage;
  return `${STAGE_LABELS[stage] ?? stage} (${index + 1}/${ANALYSIS_STAGE_ORDER.length})`;
}
