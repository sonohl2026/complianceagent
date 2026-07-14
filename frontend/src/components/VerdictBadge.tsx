const VERDICT_COLORS: Record<string, string> = {
  GO: "bg-risk-low/15 text-risk-low",
  CONDITIONAL_GO: "bg-risk-medium/15 text-risk-medium",
  STOP: "bg-risk-critical/15 text-risk-critical",
};

const RISK_COLORS: Record<string, string> = {
  CRITICAL: "bg-risk-critical/15 text-risk-critical",
  HIGH: "bg-risk-high/15 text-risk-high",
  MEDIUM: "bg-risk-medium/15 text-risk-medium",
  LOW: "bg-risk-low/15 text-risk-low",
};

export function VerdictBadge({ verdict }: { verdict: string | null }) {
  if (!verdict) return <span className="text-slate-400 text-xs">—</span>;
  const classes = VERDICT_COLORS[verdict] ?? "bg-slate-200 text-slate-600";
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${classes}`}>
      {verdict.replace("_", " ")}
    </span>
  );
}

export function RiskBadge({ risk }: { risk: string | null }) {
  if (!risk) return <span className="text-slate-400 text-xs">—</span>;
  const classes = RISK_COLORS[risk] ?? "bg-slate-200 text-slate-600";
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${classes}`}>{risk}</span>
  );
}
