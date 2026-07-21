import { useState } from "react";

import type { QuickScanPillar } from "../../types/analysis";

// Fixed display order + labels for the 6 quick_scan pillars (spec §4) --
// never sorted/filtered, so a pillar that came back UNKNOWN still shows up
// in its slot rather than silently disappearing.
export const PILLAR_ORDER: { key: QuickScanPillar["pillar"]; label: string }[] = [
  { key: "fda_status", label: "FDA status" },
  { key: "coding", label: "Coding" },
  { key: "coverage", label: "Coverage" },
  { key: "payment", label: "Payment" },
  { key: "evidence", label: "Clinical evidence" },
  { key: "billing_workflow", label: "Billing workflow" },
];

// Status color reflects EPISTEMIC confidence (do we have real evidence),
// not favorability -- VERIFIED_NEGATIVE is just as "assessed" as
// VERIFIED_POSITIVE (e.g. "confirmed: no CPT code exists yet" is a real,
// useful finding for an early-stage device, not a bad outcome).
const STATUS_STYLE: Record<QuickScanPillar["status"], { label: string; classes: string }> = {
  VERIFIED_POSITIVE: { label: "Verified", classes: "bg-teal-700/10 text-teal-800 dark:text-teal-400" },
  VERIFIED_NEGATIVE: { label: "Verified (absence)", classes: "bg-teal-700/10 text-teal-800 dark:text-teal-400" },
  MIXED: { label: "Mixed evidence", classes: "bg-amber-500/10 text-amber-700 dark:text-amber-400" },
  UNKNOWN: { label: "Not assessed", classes: "bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-400" },
  NA: { label: "N/A", classes: "bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-400" },
  RETRIEVAL_FAILURE: { label: "Retrieval failed", classes: "bg-risk-high/15 text-risk-high" },
};

const ACTION_STYLE: Record<NonNullable<QuickScanPillar["action"]>, string> = {
  PROCEED: "bg-risk-low/15 text-risk-low",
  INVESTIGATE: "bg-risk-medium/15 text-risk-medium",
  FIX: "bg-risk-critical/15 text-risk-critical",
};

export function PillarCard({ pillar }: { pillar: QuickScanPillar }) {
  const [open, setOpen] = useState(false);
  const status = STATUS_STYLE[pillar.status];
  const label = PILLAR_ORDER.find((p) => p.key === pillar.pillar)?.label ?? pillar.pillar;

  return (
    <div className="rounded border border-slate-200 dark:border-slate-800">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 p-3 text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-medium truncate">{label}</span>
          <span className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-medium ${status.classes}`}>
            {status.label}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {pillar.score !== null && <span className="text-sm font-semibold tabular-nums">{pillar.score}</span>}
          <span className="text-slate-400 text-xs">{open ? "▲" : "▼"}</span>
        </div>
      </button>
      <p className="px-3 pb-3 -mt-2 text-sm text-slate-600 dark:text-slate-300">{pillar.finding}</p>
      {open && (
        <div className="border-t border-slate-100 dark:border-slate-900 p-3 space-y-2 text-sm">
          <p className="text-slate-600 dark:text-slate-300">{pillar.detail}</p>
          {pillar.citation && (
            <p className="text-xs">
              <span className="font-medium text-slate-500">Citation: </span>
              {(() => {
                // Citations from Stage 3 are sometimes a bare URL, sometimes
                // "https://... (trailing context)" -- only the leading token
                // up to whitespace is ever a real link.
                const match = pillar.citation.match(/^(https?:\/\/\S+)(.*)$/);
                if (!match) return <span className="text-slate-500">{pillar.citation}</span>;
                const [, url, rest] = match;
                return (
                  <>
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-teal-700 dark:text-teal-400 hover:underline break-all"
                    >
                      {url}
                    </a>
                    {rest && <span className="text-slate-500">{rest}</span>}
                  </>
                );
              })()}
            </p>
          )}
          {pillar.gap && (
            <p className="text-xs">
              <span className="font-medium text-slate-500">Gap: </span>
              <span className="text-slate-600 dark:text-slate-300">{pillar.gap}</span>
            </p>
          )}
          {pillar.action && (
            <span className={`inline-block rounded px-2 py-0.5 text-[11px] font-medium ${ACTION_STYLE[pillar.action]}`}>
              {pillar.action}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
