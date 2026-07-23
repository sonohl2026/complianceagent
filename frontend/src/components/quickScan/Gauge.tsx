// Compact arc gauge for the 3 quick_scan headline measures (maturity,
// assessment coverage, research confidence). Deliberately a single neutral
// accent color rather than a red/green semantic scale: per system_prompt_v2,
// a low maturity number can be entirely on-track for an early-stage device
// (e.g. 15 for a pre-market investigational device), so coloring low values
// "alarming red" would contradict the stage-aware framing the dashboard is
// supposed to carry via stage_context and the separate risk_flag pill.
const ACCENT = "#0f766e"; // teal-700
const TRACK = "#e2e8f0"; // slate-200
const NOT_SCORED_STROKE = "#94a3b8"; // slate-400 -- deliberately not TRACK: a
// NOT_SCORED reading must never render as "the same ring a real, even
// zero-adjacent, score would produce." A real score (including 0, which the
// schema forbids here anyway) always draws the solid 270-degree gauge arc
// below; NOT_SCORED gets a genuinely different shape -- a full dashed ring,
// never that arc -- so the two states can't be confused at a glance, without
// having to read the caption text.

export function Gauge({
  value,
  label,
  sublabel,
}: {
  value: number | null;
  label: string;
  sublabel?: string;
}) {
  const size = 96;
  const stroke = 9;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  // 270-degree arc (leave a gap at the bottom) for a "gauge" rather than
  // full-circle "donut" read.
  const arcFraction = 0.75;
  const arcLength = circumference * arcFraction;
  const isNotScored = value === null;
  const filled = isNotScored ? 0 : (Math.max(0, Math.min(100, value)) / 100) * arcLength;

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="rotate-[135deg]">
        {isNotScored ? (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={NOT_SCORED_STROKE}
            strokeWidth={stroke}
            strokeDasharray="3 7"
            strokeLinecap="round"
            className="dark:opacity-70"
          />
        ) : (
          <>
            <circle
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={TRACK}
              strokeWidth={stroke}
              strokeDasharray={`${arcLength} ${circumference}`}
              strokeLinecap="round"
              className="dark:opacity-20"
            />
            <circle
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={ACCENT}
              strokeWidth={stroke}
              strokeDasharray={`${filled} ${circumference}`}
              strokeLinecap="round"
            />
          </>
        )}
      </svg>
      <div className="-mt-16 flex h-24 w-24 flex-col items-center justify-center">
        <span className={`text-2xl font-semibold tabular-nums ${isNotScored ? "text-slate-400" : ""}`}>
          {isNotScored ? "?" : Math.round(value as number)}
        </span>
        {sublabel && <span className="text-[10px] text-slate-500">{sublabel}</span>}
      </div>
      <span className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">{label}</span>
    </div>
  );
}
