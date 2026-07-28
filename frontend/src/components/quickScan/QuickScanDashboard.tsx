import { RiskBadge } from "../VerdictBadge";
import { StatusBadge } from "../StatusBadge";
import type { AnalysisRun, QuickScanAssessment } from "../../types/analysis";
import { formatAnalysisStage } from "../../utils/analysisStages";
import { BillingCodesSection } from "./BillingCodesSection";
import { Gauge } from "./Gauge";
import { PILLAR_GROUPS, PillarGroupCard } from "./PillarCard";
import { ProductIdentityEdit } from "./ProductIdentityEdit";
import { QuickScanExport } from "./QuickScanExport";
import { RetrievalProgressFeed } from "./RetrievalProgressFeed";

function asResult(value: AnalysisRun["quick_scan_result_json"]): QuickScanAssessment | null {
  return Object.keys(value).length > 0 ? (value as QuickScanAssessment) : null;
}

interface Stage1Summary {
  intended_use?: string;
  technology_type?: string;
}

function getStage1Summary(run: AnalysisRun): Stage1Summary {
  return (run.retrieval_bundle_json.stage1 as Stage1Summary | undefined) ?? {};
}

export function QuickScanDashboard({ run }: { run: AnalysisRun }) {
  const isRunning = run.status === "QUEUED" || run.status === "RUNNING";
  const result = asResult(run.quick_scan_result_json);
  const stage1 = getStage1Summary(run);

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
        {result && <QuickScanExport result={result} run={run} />}
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

          {/* Scores first (MVP lockdown Step 4): the first of the three
              deliverables. NOT_SCORED reads as an early-stage state to work
              from, never an error -- the gaps below ARE the deliverable for
              a pre-clearance founder, not a consolation message. */}
          <div className="rounded border border-slate-200 dark:border-slate-800 p-4">
            <div className="flex flex-wrap justify-center gap-8">
              <Gauge
                value={result.scores.maturity_state === "SCORED" ? result.scores.maturity : null}
                label="Maturity"
                sublabel={result.scores.maturity_state === "NOT_SCORED" ? "NOT SCORED" : undefined}
                explanation="Overall reimbursement readiness, 0-100 -- how far along this product is on FDA status, coding, coverage, payment, and billing, combined. Shows a '?' instead of a low number when there isn't enough evidence yet to score it at all, which is not the same as scoring badly."
              />
              <Gauge
                value={result.scores.assessment_coverage_pct}
                label="Coverage"
                sublabel="of 6 pillars"
                explanation="How many of the 6 pillars below we actually found real evidence for, not left as 'not assessed.' This is about how complete our research was -- a different thing from insurance coverage (the Coverage & reimbursement pillar further down)."
              />
              <Gauge
                value={result.scores.research_confidence}
                label="Confidence"
                explanation="How much we trust the evidence we found -- based on how complete and consistent it was, not on whether the news is good or bad for the product."
              />
            </div>
            {result.scores.maturity_state === "NOT_SCORED" && (
              <p className="mt-3 text-center text-sm text-amber-700 dark:text-amber-400">
                Early-stage -- not enough real evidence exists yet to give this a maturity number.
                That's the finding, not a gap in the tool: see what's missing below.
              </p>
            )}
            <p className="mt-3 text-center text-sm text-slate-600 dark:text-slate-300 max-w-2xl mx-auto">
              {result.scores.stage_context}
            </p>
          </div>

          {/* Confirms the agent understood the product before showing
              anything derived from that understanding -- directly requested:
              a plain-language read-back of what this device is/does. */}
          {(stage1.technology_type || stage1.intended_use) && (
            <section className="rounded border border-slate-200 dark:border-slate-800 p-4 space-y-1">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                What we understood this product to be
              </h3>
              {stage1.technology_type && (
                <p className="text-sm text-slate-700 dark:text-slate-200">{stage1.technology_type}</p>
              )}
              {stage1.intended_use && (
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  <span className="text-slate-500">Intended use: </span>
                  {stage1.intended_use}
                </p>
              )}
              <p className="text-xs text-slate-400 pt-1">
                Not what it is -- correct it above if this is wrong before trusting anything below.
              </p>
            </section>
          )}

          {/* Billing codes: the second deliverable, promoted to first-class
              rather than buried in the coding pillar's expander. */}
          <BillingCodesSection run={run} codingPillar={result.pillars.find((p) => p.pillar === "coding")} />

          {/* Gaps blocking coverage: the third deliverable, above the fold. */}
          {(result.top_gaps.length > 0 || result.next_steps.length > 0) && (
            <section className="rounded border border-slate-200 dark:border-slate-800 p-4 space-y-3">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                Gaps blocking coverage
              </h3>
              {result.top_gaps.length > 0 && (
                <ul className="list-disc list-inside text-sm space-y-1">
                  {result.top_gaps.map((g, i) => (
                    <li key={i}>{g}</li>
                  ))}
                </ul>
              )}
              {result.next_steps.length > 0 && (
                <div className="pt-1 border-t border-slate-100 dark:border-slate-900">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1">
                    What to do about it
                  </p>
                  <ul className="list-disc list-inside text-sm space-y-1">
                    {result.next_steps.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}

          {/* Pillar detail: three plain-language groups instead of six raw
              pillars -- Coding is folded into Billing Codes above (same
              data, not a second card repeating it); Coverage/Payment/
              Billing workflow merge into one "will this get paid" card. */}
          <section className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Pillar detail</h3>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-2">
              {PILLAR_GROUPS.map((group) => (
                <PillarGroupCard key={group.id} group={group} pillars={result.pillars} />
              ))}
            </div>
          </section>

          <div className="rounded border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950 p-4 text-xs">
            {result.disclaimer}
          </div>
        </>
      )}
    </div>
  );
}
