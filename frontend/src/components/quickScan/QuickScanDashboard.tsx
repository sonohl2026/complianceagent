import { RiskBadge } from "../VerdictBadge";
import { StatusBadge } from "../StatusBadge";
import type { AnalysisRun, QuickScanAssessment } from "../../types/analysis";
import { formatAnalysisStage } from "../../utils/analysisStages";
import { Gauge } from "./Gauge";
import { PILLAR_ORDER, PillarCard } from "./PillarCard";
import { ProductIdentityEdit } from "./ProductIdentityEdit";
import { QuickScanExport } from "./QuickScanExport";
import { RetrievalProgressFeed } from "./RetrievalProgressFeed";

function asResult(value: AnalysisRun["quick_scan_result_json"]): QuickScanAssessment | null {
  return Object.keys(value).length > 0 ? (value as QuickScanAssessment) : null;
}

export function QuickScanDashboard({ run }: { run: AnalysisRun }) {
  const isRunning = run.status === "QUEUED" || run.status === "RUNNING";
  const result = asResult(run.quick_scan_result_json);

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Quick Scan</h2>
          <p className="text-xs text-slate-500">
            Live regulatory/coding/coverage/payment lookup against openFDA and the CMS Coverage
            API -- revision {run.revision}
          </p>
        </div>
        {result && <QuickScanExport result={result} analysisId={run.id} />}
      </div>

      {isRunning && (
        <div className="space-y-4">
          <div className="rounded border border-slate-200 dark:border-slate-800 p-4 text-sm">
            <StatusBadge status={run.status} /> <span className="ml-2">{formatAnalysisStage(run.current_stage)}</span>
          </div>
          {Object.keys(run.retrieval_progress_json).length > 0 && (
            <RetrievalProgressFeed progress={run.retrieval_progress_json} />
          )}
        </div>
      )}

      {run.status === "FAILED" && (
        <div className="rounded border border-risk-critical/40 bg-risk-critical/5 p-4 text-sm text-risk-critical">
          Quick scan failed: {run.error_summary}
        </div>
      )}

      {run.status === "COMPLETE" && result && (
        <>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="space-y-1">
              <p className="text-xl font-semibold">{result.product.name}</p>
              <p className="text-sm text-slate-500">{result.product.manufacturer || "Manufacturer unknown"}</p>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <span className="text-xs rounded bg-slate-200 dark:bg-slate-800 px-2 py-0.5 uppercase tracking-wide">
                  {result.product.dev_stage.replace(/_/g, " ")}
                </span>
                {result.product.identifiers.map((id, i) => (
                  <span
                    key={i}
                    className="text-xs rounded border border-slate-300 dark:border-slate-700 px-2 py-0.5"
                    title={`match confidence: ${id.match_confidence}`}
                  >
                    {id.type}: {id.value}
                  </span>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className="text-xs text-slate-500 mb-1">Risk flag</p>
                <RiskBadge risk={result.scores.risk_flag} />
              </div>
              <ProductIdentityEdit run={run} />
            </div>
          </div>

          <div className="rounded border border-slate-200 dark:border-slate-800 p-4">
            <div className="flex flex-wrap justify-center gap-8">
              <Gauge
                value={result.scores.maturity_state === "SCORED" ? result.scores.maturity : null}
                label="Maturity"
                sublabel={result.scores.maturity_state === "NOT_SCORED" ? "NOT SCORED" : undefined}
              />
              <Gauge value={result.scores.assessment_coverage_pct} label="Coverage" sublabel="of 6 pillars" />
              <Gauge value={result.scores.research_confidence} label="Confidence" />
            </div>
            {result.scores.maturity_state === "NOT_SCORED" && (
              <p className="mt-3 text-center text-sm text-amber-700 dark:text-amber-400">
                {result.scores.not_scored_reason === "INSUFFICIENT_DATA_RETRIEVED"
                  ? "Not enough real evidence was retrieved to assess maturity -- this is never shown as a numeric 0."
                  : result.scores.not_scored_reason}
              </p>
            )}
            <p className="mt-3 text-center text-sm text-slate-600 dark:text-slate-300 max-w-2xl mx-auto">
              {result.scores.stage_context}
            </p>
          </div>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Pillars</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {PILLAR_ORDER.map(({ key }) => {
                const pillar = result.pillars.find((p) => p.pillar === key);
                return pillar ? <PillarCard key={key} pillar={pillar} /> : null;
              })}
            </div>
          </section>

          {result.top_gaps.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">Top gaps</h3>
              <ul className="list-disc list-inside text-sm space-y-1">
                {result.top_gaps.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
            </section>
          )}

          {result.next_steps.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">Next steps</h3>
              <ul className="list-disc list-inside text-sm space-y-1">
                {result.next_steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </section>
          )}

          <div className="rounded border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950 p-4 text-xs">
            {result.disclaimer}
          </div>
        </>
      )}
    </div>
  );
}
