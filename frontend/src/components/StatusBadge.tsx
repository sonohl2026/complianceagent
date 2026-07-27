const COLORS: Record<string, string> = {
  COMPLETE: "bg-risk-low/15 text-risk-low",
  PENDING: "bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  QUEUED: "bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  PROCESSING: "bg-risk-medium/15 text-risk-medium",
  RUNNING: "bg-risk-medium/15 text-risk-medium",
  FAILED: "bg-risk-critical/15 text-risk-critical",
  QUARANTINED: "bg-risk-critical/15 text-risk-critical",
  CANCELLED: "bg-slate-200 text-slate-500 dark:bg-slate-800",
  STALE: "bg-risk-high/15 text-risk-high",
  AWAITING_CONFIRMATION: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
};

export function StatusBadge({ status }: { status: string }) {
  const classes = COLORS[status] ?? "bg-slate-200 text-slate-600 dark:bg-slate-800";
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${classes}`}>
      {status}
    </span>
  );
}
