import type { AnalysisRun, FeeScheduleVerifiedCode, QuickScanPillar } from "../../types/analysis";

interface FeeScheduleSource {
  status: "HIT" | "MISS" | "RETRIEVAL_FAILURE";
  data: { verified_codes?: FeeScheduleVerifiedCode[] } | null;
}

function formatRate(rateUsd: number | null, statusCode: string | null): string {
  if (rateUsd !== null) return `$${rateUsd.toFixed(2)}`;
  return statusCode ? `not separately priced (status ${statusCode})` : "not separately priced";
}

/** MVP lockdown Step 4: billing codes promoted out of the coding pillar's
 * expander into their own first-class section -- code, verified rate,
 * citation. This reads data already persisted by the existing pipeline
 * (code_candidates.py::resolve_fee_schedule_evidence, carried through as any
 * other retrieval source) -- a presentation change only, no pipeline change. */
export function BillingCodesSection({
  run,
  codingPillar,
  cptLicenseEnabled,
}: {
  run: AnalysisRun;
  codingPillar: QuickScanPillar | undefined;
  cptLicenseEnabled: boolean;
}) {
  const feeSchedule = run.retrieval_bundle_json.sources as Record<string, FeeScheduleSource> | undefined;
  const source = feeSchedule?.fee_schedule_lookup;
  const codes = source?.data?.verified_codes ?? [];

  return (
    <section className="rounded border border-slate-200 dark:border-slate-800 p-4 space-y-3">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Billing codes</h3>

      {codes.length === 0 && (
        <p className="text-sm text-slate-500">
          No verified billing code found against current CMS fee-schedule data yet. This is
          expected pre-clearance -- see Coding in the pillars below for what's still needed.
        </p>
      )}

      {codes.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-800">
                <th className="py-2 pr-4">Code</th>
                <th className="py-2 pr-4">Format</th>
                <th className="py-2 pr-4">Paraphrase</th>
                <th className="py-2 pr-4">Verified rate</th>
              </tr>
            </thead>
            <tbody>
              {codes.map((c) => (
                <tr key={c.code} className="border-b border-slate-100 dark:border-slate-900 align-top">
                  <td className="py-2 pr-4 font-medium tabular-nums">{c.code}</td>
                  <td className="py-2 pr-4 text-slate-500">{c.code_format}</td>
                  <td className="py-2 pr-4 max-w-sm text-slate-600 dark:text-slate-300">
                    {c.description ?? (
                      <span className="text-slate-400 italic">
                        not shown -- AMA-licensed descriptor text
                        {cptLicenseEnabled ? " (cpt_license is on, but this app never reproduces it)" : ""}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-4 tabular-nums text-slate-600 dark:text-slate-300">
                    {formatRate(c.rate_usd, c.status_code)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {codingPillar?.citation && (
        <p className="text-xs">
          <span className="font-medium text-slate-500">Source: </span>
          <a
            href={codingPillar.citation.match(/^https?:\/\/\S+/)?.[0] ?? undefined}
            target="_blank"
            rel="noreferrer"
            className="text-teal-700 dark:text-teal-400 hover:underline break-all"
          >
            {codingPillar.citation}
          </a>
        </p>
      )}
    </section>
  );
}
