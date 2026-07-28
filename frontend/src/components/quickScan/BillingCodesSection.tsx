import type { AnalysisRun, FeeScheduleVerifiedCode, QuickScanPillar } from "../../types/analysis";
import { CMS_PFS_LOOKUP_URL, extractCitationUrl } from "../../utils/citation";

interface FeeScheduleSource {
  status: "HIT" | "MISS" | "RETRIEVAL_FAILURE";
  data: { verified_codes?: FeeScheduleVerifiedCode[] } | null;
}

function formatRate(rateUsd: number | null, statusCode: string | null): string {
  if (rateUsd !== null) return `$${rateUsd.toFixed(2)}`;
  return statusCode ? `not separately priced (status ${statusCode})` : "not separately priced";
}

/** MVP lockdown Step 4 + plain-language pass: billing codes as their own
 * first-class section -- code, description, Medicare rate, source link.
 * Reads data already persisted by the existing pipeline
 * (code_candidates.py::resolve_fee_schedule_evidence) -- a presentation
 * change only, no pipeline change. */
export function BillingCodesSection({
  run,
  codingPillar,
}: {
  run: AnalysisRun;
  codingPillar: QuickScanPillar | undefined;
}) {
  const feeSchedule = run.retrieval_bundle_json.sources as Record<string, FeeScheduleSource> | undefined;
  const source = feeSchedule?.fee_schedule_lookup;
  const codes = source?.data?.verified_codes ?? [];
  const citationUrl = extractCitationUrl(codingPillar?.citation) ?? (codes.length > 0 ? CMS_PFS_LOOKUP_URL : null);
  const citationLabel = extractCitationUrl(codingPillar?.citation)
    ? "Verify this code"
    : "Look up on CMS.gov";

  return (
    <section className="rounded border border-slate-200 dark:border-slate-800 p-4 space-y-3">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Billing codes</h3>

      {codes.length === 0 && (
        <p className="text-sm text-slate-500">
          No verified billing code found against current CMS fee-schedule data yet. This is
          expected pre-clearance -- see "What's still needed" below.
        </p>
      )}

      {codes.length > 0 && (
        <>
          <p className="text-xs text-slate-500 max-w-2xl">
            These are the real U.S. billing codes (CPT/HCPCS) this product maps to, each checked
            against current, official Medicare fee-schedule data before being shown here -- not a
            guess. <strong>Description</strong> is left blank for CPT codes specifically: U.S.
            copyright law (the AMA owns CPT's official wording) blocks this app from reproducing
            that text, so click the source link instead to read the real description on the
            government site. <strong>Medicare rate</strong> is the actual national payment amount
            Medicare currently pays for that code.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-800">
                  <th className="py-2 pr-4">Code</th>
                  <th className="py-2 pr-4">Description</th>
                  <th className="py-2 pr-4">Medicare rate</th>
                  <th className="py-2 pr-4">Source</th>
                </tr>
              </thead>
              <tbody>
                {codes.map((c) => (
                  <tr key={c.code} className="border-b border-slate-100 dark:border-slate-900 align-top">
                    <td className="py-2 pr-4 font-medium tabular-nums">{c.code}</td>
                    <td className="py-2 pr-4 max-w-sm text-slate-600 dark:text-slate-300">
                      {c.description ?? <span className="text-slate-400 italic">licensed text -- see source</span>}
                    </td>
                    <td className="py-2 pr-4 tabular-nums text-slate-600 dark:text-slate-300">
                      {formatRate(c.rate_usd, c.status_code)}
                    </td>
                    <td className="py-2 pr-4">
                      {citationUrl ? (
                        <a
                          href={citationUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="text-teal-700 dark:text-teal-400 hover:underline text-xs"
                        >
                          {citationLabel} ↗
                        </a>
                      ) : (
                        <span className="text-xs text-slate-400">--</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {codingPillar?.finding && (
        <p className="text-xs text-slate-500 pt-2 border-t border-slate-100 dark:border-slate-900">
          <span className="font-medium">Coding assessment: </span>
          {codingPillar.finding}
          {codingPillar.gap ? ` ${codingPillar.gap}` : ""}
        </p>
      )}
    </section>
  );
}
