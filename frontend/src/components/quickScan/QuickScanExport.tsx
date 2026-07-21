import { useState } from "react";

import type { QuickScanAssessment } from "../../types/analysis";
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

export function QuickScanExport({ result, analysisId }: { result: QuickScanAssessment; analysisId: string }) {
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
        onClick={copySummary}
        className="text-xs rounded border border-slate-300 dark:border-slate-700 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-900"
      >
        {copyState === "copied" ? "Copied ✓" : "Copy summary"}
      </button>
      <button
        onClick={() => download(`quick-scan-${analysisId}.json`, JSON.stringify(result, null, 2), "application/json")}
        className="text-xs rounded border border-slate-300 dark:border-slate-700 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-900"
      >
        Download JSON
      </button>
      <button
        onClick={() => download(`quick-scan-${analysisId}-pillars.csv`, toCsv(result), "text/csv")}
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
