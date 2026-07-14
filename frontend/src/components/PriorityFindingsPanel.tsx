import { RiskBadge } from "./VerdictBadge";
import type { Finding } from "../types/analysis";

const RISK_ORDER: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

function rankFindings(findings: Finding[]): Finding[] {
  return [...findings].sort((a, b) => {
    const riskDiff = (RISK_ORDER[a.risk] ?? 99) - (RISK_ORDER[b.risk] ?? 99);
    if (riskDiff !== 0) return riskDiff;
    const aPriority = a.priority ?? 99;
    const bPriority = b.priority ?? 99;
    return aPriority - bPriority;
  });
}

/**
 * A ranked, most-to-least-important view of the same findings already
 * returned by the API -- computed client-side from the risk/priority the
 * model already assigned to each finding, rather than issuing another
 * billed LLM call to re-summarize what's already structured data.
 */
export function PriorityFindingsPanel({ findings, limit = 8 }: { findings: Finding[]; limit?: number }) {
  if (findings.length === 0) return null;
  const ranked = rankFindings(findings).slice(0, limit);

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        Key findings, most to least important
      </h3>
      <p className="text-xs text-slate-500">
        Ranked by risk severity, then the model's own priority ranking. Not a separate AI call — this
        re-orders the {findings.length} finding{findings.length === 1 ? "" : "s"} below.
      </p>
      <ol className="space-y-1.5">
        {ranked.map((f, i) => (
          <li key={f.id} className="flex items-start gap-2 text-sm">
            <span className="text-slate-400 w-5 shrink-0 text-right">{i + 1}.</span>
            <RiskBadge risk={f.risk} />
            <span className="text-slate-500 text-xs shrink-0">{f.domain}</span>
            <span className="flex-1">{f.title}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
