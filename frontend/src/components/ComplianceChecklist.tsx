import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { RiskBadge } from "./VerdictBadge";
import type { ComplianceIssue } from "../types/complianceIssue";

/**
 * Persists across analysis runs for this product (unlike a single run's
 * findings): shows what's still open vs. what got resolved after a small
 * incremental site/document change, without re-reading a whole new report.
 * Matching a new run's findings against these is a normalized-title +
 * domain check (server-side, see app/services/analysis/checklist.py) --
 * an approximation that can miss a match if the model rewords a finding
 * between runs, not a guarantee.
 */
export function ComplianceChecklist({ productId }: { productId: string }) {
  const { data: issues } = useQuery({
    queryKey: ["compliance-checklist", productId],
    queryFn: () => api.get<ComplianceIssue[]>(`/products/${productId}/compliance-checklist`),
  });

  if (!issues || issues.length === 0) {
    return (
      <p className="text-xs text-slate-500">
        No tracked issues yet — these populate after the first completed analysis for this product.
      </p>
    );
  }

  const open = issues.filter((i) => i.status === "OPEN");
  const resolved = issues.filter((i) => i.status === "RESOLVED");

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        {open.length} open · {resolved.length} resolved across all analysis runs for this product.
      </p>
      {open.length > 0 && (
        <ul className="space-y-1.5">
          {open.map((issue) => (
            <li key={issue.id} className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={false} disabled className="mt-1 shrink-0" />
              <RiskBadge risk={issue.risk} />
              <span className="text-slate-500 text-xs shrink-0">{issue.domain}</span>
              <span className="flex-1">{issue.title}</span>
            </li>
          ))}
        </ul>
      )}
      {resolved.length > 0 && (
        <details>
          <summary className="text-xs text-slate-500 cursor-pointer">
            {resolved.length} resolved issue{resolved.length === 1 ? "" : "s"}
          </summary>
          <ul className="space-y-1.5 mt-2">
            {resolved.map((issue) => (
              <li key={issue.id} className="flex items-start gap-2 text-sm text-slate-400 line-through">
                <input type="checkbox" checked disabled className="mt-1 shrink-0" />
                <span className="text-xs shrink-0">{issue.domain}</span>
                <span className="flex-1">{issue.title}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
