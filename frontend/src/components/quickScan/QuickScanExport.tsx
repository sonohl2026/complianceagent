import { useState } from "react";

import type { AnalysisRun, FeeScheduleVerifiedCode, QuickScanAssessment } from "../../types/analysis";
import { CMS_PFS_LOOKUP_URL, extractCitationUrl } from "../../utils/citation";
import { PILLAR_ORDER } from "./PillarCard";

// Unlike the legacy pipeline's ExportButtons (server-side report assembly
// across relational Finding/CodingCandidate tables), the whole quick_scan
// result is already one flat JSON blob on the client after polling -- no
// server round-trip needed for any of these.
function download(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function toCsv(result: QuickScanAssessment): string {
  const header = ["pillar", "status", "score", "finding", "detail", "citation", "gap", "action"];
  const rows = PILLAR_ORDER.map(({ key }) => {
    const p = result.pillars.find((x) => x.pillar === key);
    if (!p) return header.map(() => "");
    return [p.pillar, p.status, p.score ?? "", p.finding, p.detail, p.citation ?? "", p.gap ?? "", p.action ?? ""];
  });
  const escape = (v: unknown) => `"${String(v).replace(/"/g, '""')}"`;
  return [header, ...rows].map((row) => row.map(escape).join(",")).join("\n");
}

interface FeeScheduleSource {
  status: "HIT" | "MISS" | "RETRIEVAL_FAILURE";
  data: { verified_codes?: FeeScheduleVerifiedCode[] } | null;
}

function formatRate(rateUsd: number | null): string {
  return rateUsd !== null ? `$${rateUsd.toFixed(2)}` : "not separately priced";
}

/** The plain-language, human-readable version of this page -- what a
 * founder would actually want to hand to a reimbursement consultant or
 * keep on file: what the product is, what it bills under (with citations),
 * and exactly what's missing. Deliberately Markdown, not PDF -- no new
 * rendering dependency, opens/prints cleanly from any editor or browser. */
function toReimbursementReport(result: QuickScanAssessment, run: AnalysisRun): string {
  const stage1 = (run.retrieval_bundle_json.stage1 as { intended_use?: string; technology_type?: string }) ?? {};
  const feeSchedule = run.retrieval_bundle_json.sources as Record<string, FeeScheduleSource> | undefined;
  const codes = feeSchedule?.fee_schedule_lookup?.data?.verified_codes ?? [];
  const codingPillar = result.pillars.find((p) => p.pillar === "coding");
  const fdaPillar = result.pillars.find((p) => p.pillar === "fda_status");
  const citationUrl = extractCitationUrl(codingPillar?.citation) ?? (codes.length > 0 ? CMS_PFS_LOOKUP_URL : null);

  const lines: string[] = [
    `# Reimbursement Readiness Report -- ${result.product.name}`,
    "",
    `Generated ${new Date().toLocaleString()} -- ${result.product.manufacturer || "manufacturer unknown"}`,
    "",
    "## What this product is",
    stage1.technology_type || "(not determined)",
    stage1.intended_use ? `\nIntended use: ${stage1.intended_use}` : "",
    "",
    "## Regulatory status",
    fdaPillar ? `${fdaPillar.finding} ${fdaPillar.detail}` : "Not assessed.",
    "",
    "## Billing codes",
  ];

  if (codes.length === 0) {
    lines.push("No verified billing code found against current CMS fee-schedule data yet.");
  } else {
    lines.push("| Code | Description | Medicare rate | Source |", "| --- | --- | --- | --- |");
    for (const c of codes) {
      const desc = c.description ?? "licensed text -- see source";
      lines.push(`| ${c.code} | ${desc} | ${formatRate(c.rate_usd)} | ${citationUrl ?? "--"} |`);
    }
  }
  if (codingPillar?.finding) {
    lines.push("", `_Coding assessment: ${codingPillar.finding}${codingPillar.gap ? ` ${codingPillar.gap}` : ""}_`);
  }

  lines.push(
    "",
    "## Evidence gaps blocking coverage",
    ...(result.top_gaps.length > 0 ? result.top_gaps.map((g) => `- ${g}`) : ["(none identified)"]),
    "",
    "## What to do about it",
    ...(result.next_steps.length > 0 ? result.next_steps.map((s) => `- ${s}`) : ["(none identified)"]),
    "",
    "---",
    result.disclaimer,
  );

  return lines.join("\n");
}

export function QuickScanExport({ result, run }: { result: QuickScanAssessment; run: AnalysisRun }) {
  const [copyState, setCopyState] = useState<"idle" | "copied">("idle");

  const copySummary = async () => {
    const lines = [
      `${result.product.name} (${result.product.manufacturer || "manufacturer unknown"})`,
      `Maturity: ${result.scores.maturity_state === "SCORED" ? result.scores.maturity : "NOT SCORED"}`,
      `Risk: ${result.scores.risk_flag}`,
      result.scores.stage_context,
      "",
      ...PILLAR_ORDER.map(({ label, key }) => {
        const p = result.pillars.find((x) => x.pillar === key);
        return `${label}: ${p?.status ?? "UNKNOWN"}${p?.score !== null && p?.score !== undefined ? ` (${p.score})` : ""} -- ${p?.finding ?? ""}`;
      }),
    ];
    await navigator.clipboard.writeText(lines.join("\n"));
    setCopyState("copied");
    setTimeout(() => setCopyState("idle"), 2000);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        onClick={() => download(`reimbursement-report-${run.id}.md`, toReimbursementReport(result, run), "text/markdown")}
        className="text-xs rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1.5 hover:opacity-90"
      >
        Download reimbursement report
      </button>
      <button
        onClick={copySummary}
        className="text-xs rounded border border-slate-300 dark:border-slate-700 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-900"
      >
        {copyState === "copied" ? "Copied ✓" : "Copy summary"}
      </button>
      <button
        onClick={() => download(`quick-scan-${run.id}.json`, JSON.stringify(result, null, 2), "application/json")}
        className="text-xs rounded border border-slate-300 dark:border-slate-700 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-900"
      >
        Download JSON
      </button>
      <button
        onClick={() => download(`quick-scan-${run.id}-pillars.csv`, toCsv(result), "text/csv")}
        className="text-xs rounded border border-slate-300 dark:border-slate-700 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-900"
      >
        Download CSV
      </button>
      <button
        onClick={() => window.print()}
        className="text-xs rounded border border-slate-300 dark:border-slate-700 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-900 print:hidden"
      >
        Print
      </button>
    </div>
  );
}
