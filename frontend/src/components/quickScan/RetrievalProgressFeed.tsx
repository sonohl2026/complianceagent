import type { RetrievalProgressEntry } from "../../types/analysis";

// No dedicated streaming transport -- retrieval_progress_json is just
// another field on the already-3-second-polled AnalysisRun row, so this
// re-renders from whatever the parent's poll last returned.
const SOURCE_LABELS: Record<string, string> = {
  openfda_510k: "openFDA · 510(k)",
  openfda_pma: "openFDA · PMA",
  openfda_classification: "openFDA · Classification / De Novo",
  openfda_recall: "openFDA · Recalls",
  openfda_enforcement: "openFDA · Enforcement",
  openfda_event: "openFDA · MAUDE events",
  openfda_udi: "openFDA · UDI",
  cms_ncd: "CMS · National Coverage",
  cms_lcd: "CMS · Local Coverage",
  cms_article: "CMS · Coverage Articles",
};

const STATUS_ICON: Record<RetrievalProgressEntry["status"] | "PENDING", { icon: string; classes: string }> = {
  HIT: { icon: "●", classes: "text-teal-700 dark:text-teal-400" },
  MISS: { icon: "○", classes: "text-slate-400" },
  RETRIEVAL_FAILURE: { icon: "▲", classes: "text-risk-high" },
  PENDING: { icon: "…", classes: "text-slate-300 dark:text-slate-600 animate-pulse" },
};

export function RetrievalProgressFeed({
  progress,
}: {
  progress: Record<string, RetrievalProgressEntry>;
}) {
  const sources = Object.keys(SOURCE_LABELS);

  return (
    <div className="rounded border border-slate-200 dark:border-slate-800 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-3">Retrieving evidence</p>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
        {sources.map((key) => {
          const entry = progress[key];
          const state = entry ? STATUS_ICON[entry.status] : STATUS_ICON.PENDING;
          return (
            <li key={key} className="flex items-center gap-2">
              <span className={state.classes}>{state.icon}</span>
              <span className="text-slate-600 dark:text-slate-300">{SOURCE_LABELS[key]}</span>
              {entry && <span className="text-xs text-slate-400 ml-auto">{entry.latency_ms}ms</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
