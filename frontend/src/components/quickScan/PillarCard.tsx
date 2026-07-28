import { useState } from "react";

import type { QuickScanPillar } from "../../types/analysis";
import { extractCitationUrl } from "../../utils/citation";

// Six raw pillars come back from Stage 3, but shown as three plain-language
// groups: Coding is dropped entirely here (superseded by the first-class
// Billing Codes section -- same data, no loss, just not a second card
// saying the same thing two different ways). Coverage/Payment/Billing
// workflow are merged into one "Coverage & reimbursement" card because
// they're really one underlying question a founder asks ("will this get
// paid, and how") that six separate blocks fragmented into confusing pieces.
export const PILLAR_GROUPS: {
  id: string;
  label: string;
  subtitle: string;
  pillars: { key: QuickScanPillar["pillar"]; subLabel: string }[];
}[] = [
  {
    id: "regulatory",
    label: "Regulatory status",
    subtitle: "Can this legally be sold or marketed in the US right now?",
    pillars: [{ key: "fda_status", subLabel: "FDA status" }],
  },
  {
    id: "coverage_reimbursement",
    label: "Coverage & reimbursement",
    subtitle: "Will insurance actually cover it, pay for it, and can it be billed correctly in practice?",
    pillars: [
      { key: "coverage", subLabel: "Coverage policy" },
      { key: "payment", subLabel: "Payment rate" },
      { key: "billing_workflow", subLabel: "Billing workflow" },
    ],
  },
  {
    id: "evidence",
    label: "Clinical evidence",
    subtitle: "Is there real data backing up what this product claims to do?",
    pillars: [{ key: "evidence", subLabel: "Clinical evidence" }],
  },
];

// Kept for the CSV/plain-text exports, which still want every one of the
// 6 raw pillars (including coding) even though the UI only shows 3 groups.
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

function CitationLine({ citation }: { citation: string }) {
  const url = extractCitationUrl(citation);
  return (
    <p className="text-xs">
      <span className="font-medium text-slate-500">Source: </span>
      {url ? (
        <a href={url} target="_blank" rel="noreferrer" className="text-teal-700 dark:text-teal-400 hover:underline break-all">
          {citation}
        </a>
      ) : (
        <span className="text-slate-500">{citation}</span>
      )}
    </p>
  );
}

function PillarSubItem({ subLabel, pillar }: { subLabel: string; pillar: QuickScanPillar }) {
  const status = STATUS_STYLE[pillar.status];
  return (
    <div className="space-y-1.5 py-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium">{subLabel}</span>
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${status.classes}`}>{status.label}</span>
        {pillar.score !== null && <span className="text-xs tabular-nums text-slate-500">{pillar.score}</span>}
      </div>
      <p className="text-sm text-slate-600 dark:text-slate-300">{pillar.finding}</p>
      <p className="text-xs text-slate-500">{pillar.detail}</p>
      {pillar.citation && <CitationLine citation={pillar.citation} />}
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
  );
}

/** One card per plain-language group (see PILLAR_GROUPS) -- collapsed by
 * default showing just the group's own sub-pillars' one-line findings;
 * expanding reveals detail/citation/gap/action for each. */
export function PillarGroupCard({
  group,
  pillars,
}: {
  group: (typeof PILLAR_GROUPS)[number];
  pillars: QuickScanPillar[];
}) {
  const [open, setOpen] = useState(false);
  const items = group.pillars
    .map(({ key, subLabel }) => ({ subLabel, pillar: pillars.find((p) => p.pillar === key) }))
    .filter((x): x is { subLabel: string; pillar: QuickScanPillar } => x.pillar !== undefined);

  if (items.length === 0) return null;

  return (
    <div className="rounded border border-slate-200 dark:border-slate-800">
      <button onClick={() => setOpen((o) => !o)} className="block w-full p-3 text-left">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium">{group.label}</span>
          <span className="text-slate-400 text-xs shrink-0">{open ? "▲" : "▼"}</span>
        </div>
        <p className="text-xs text-slate-500 mt-0.5">{group.subtitle}</p>
        <div className="flex flex-wrap items-center gap-1.5 mt-2">
          {items.map(({ subLabel, pillar }) => (
            <span
              key={subLabel}
              title={subLabel}
              className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${STATUS_STYLE[pillar.status].classes}`}
            >
              {STATUS_STYLE[pillar.status].label}
            </span>
          ))}
        </div>
      </button>
      {!open && (
        <div className="px-3 pb-3 -mt-1 space-y-1">
          {items.map(({ subLabel, pillar }) => (
            <p key={subLabel} className="text-sm text-slate-600 dark:text-slate-300">
              <span className="text-slate-500">{subLabel}: </span>
              {pillar.finding}
            </p>
          ))}
        </div>
      )}
      {open && (
        <div className="border-t border-slate-100 dark:border-slate-900 px-3 divide-y divide-slate-100 dark:divide-slate-900">
          {items.map(({ subLabel, pillar }) => (
            <PillarSubItem key={subLabel} subLabel={subLabel} pillar={pillar} />
          ))}
        </div>
      )}
    </div>
  );
}
