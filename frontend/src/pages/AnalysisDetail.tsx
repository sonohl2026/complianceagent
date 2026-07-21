import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { api } from "../api/client";
import { CitationBadge } from "../components/CitationInspector";
import { ExportButtons } from "../components/ExportButtons";
import { PriorityFindingsPanel } from "../components/PriorityFindingsPanel";
import { QuickScanDashboard } from "../components/quickScan/QuickScanDashboard";
import { RiskBadge, VerdictBadge } from "../components/VerdictBadge";
import { StatusBadge } from "../components/StatusBadge";
import type { AnalysisRun, CodingCandidate, Finding } from "../types/analysis";
import { formatAnalysisStage } from "../utils/analysisStages";

const DISCLAIMER =
  "This application provides internal decision support. It does not constitute legal advice, " +
  "regulatory authorization, payer confirmation, coding advice, or billing approval. Final " +
  "decisions require review by qualified regulatory, legal, clinical, coding, reimbursement, " +
  "privacy, security, and quality professionals as applicable.";

function useAnalysisPoll(analysisId: string) {
  return useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => api.get<AnalysisRun>(`/analyses/${analysisId}`),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "QUEUED" || status === "RUNNING" ? 3000 : false;
    },
  });
}

export function AnalysisDetail() {
  const { analysisId } = useParams<{ analysisId: string }>();
  const [domainFilter, setDomainFilter] = useState<string>("ALL");

  const { data: run } = useAnalysisPoll(analysisId!);

  const isQuickScan = run?.analysis_type === "quick_scan";

  const { data: findings } = useQuery({
    queryKey: ["findings", analysisId],
    queryFn: () => api.get<Finding[]>(`/analyses/${analysisId}/findings`),
    enabled: run?.status === "COMPLETE" && !isQuickScan,
  });

  const { data: codingCandidates } = useQuery({
    queryKey: ["coding-candidates", analysisId],
    queryFn: () => api.get<CodingCandidate[]>(`/analyses/${analysisId}/coding-candidates`),
    enabled: run?.status === "COMPLETE" && !isQuickScan,
  });

  if (!run) return <p className="text-sm text-slate-500">Loading…</p>;

  if (isQuickScan) return <QuickScanDashboard run={run} />;

  const domains = findings ? Array.from(new Set(findings.map((f) => f.domain))) : [];
  const filteredFindings =
    findings && domainFilter !== "ALL" ? findings.filter((f) => f.domain === domainFilter) : findings;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Analysis</h2>
          <p className="text-xs text-slate-500">
            Model: {run.analysis_model ?? "—"}
            {run.model_response_identifier ? ` (responded as ${run.model_response_identifier})` : ""} · Source
            cutoff: {run.source_cutoff_date ?? "—"}
          </p>
        </div>
        {run.status === "COMPLETE" && <ExportButtons analysisId={analysisId!} />}
      </div>

      {(run.status === "QUEUED" || run.status === "RUNNING") && (
        <div className="rounded border border-slate-200 dark:border-slate-800 p-4 text-sm">
          <StatusBadge status={run.status} /> <span className="ml-2">{formatAnalysisStage(run.current_stage)}</span>
        </div>
      )}

      {run.status === "FAILED" && (
        <div className="rounded border border-risk-critical/40 bg-risk-critical/5 p-4 text-sm text-risk-critical">
          Analysis failed: {run.error_summary}
        </div>
      )}

      {run.status === "COMPLETE" && (
        <>
          <div className="grid grid-cols-4 gap-4">
            <div className="rounded border border-slate-200 dark:border-slate-800 p-4">
              <p className="text-xs text-slate-500 mb-1">Verdict</p>
              <VerdictBadge verdict={run.overall_verdict} />
            </div>
            <div className="rounded border border-slate-200 dark:border-slate-800 p-4">
              <p className="text-xs text-slate-500 mb-1">Risk</p>
              <RiskBadge risk={run.overall_risk} />
            </div>
            <div className="rounded border border-slate-200 dark:border-slate-800 p-4">
              <p className="text-xs text-slate-500 mb-1">Readiness score</p>
              <p className="text-lg font-semibold">{run.readiness_score ?? "—"}</p>
              {run.readiness_score_note && (
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">{run.readiness_score_note}</p>
              )}
            </div>
            <div className="rounded border border-slate-200 dark:border-slate-800 p-4">
              <p className="text-xs text-slate-500 mb-1">Confidence</p>
              <p className="text-lg font-semibold">{run.confidence_score ?? "—"}</p>
            </div>
          </div>

          {findings && <PriorityFindingsPanel findings={findings} />}

          {run.executive_summary && (
            <section>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">
                Executive summary
              </h3>
              <p className="text-sm whitespace-pre-wrap">{run.executive_summary}</p>
            </section>
          )}

          {run.critical_blockers.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">
                Critical blockers
              </h3>
              <ul className="list-disc list-inside text-sm space-y-1">
                {run.critical_blockers.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </section>
          )}

          {run.priority_actions.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">
                Prioritized action plan
              </h3>
              <ul className="list-disc list-inside text-sm space-y-1">
                {run.priority_actions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </section>
          )}

          {run.required_reviewers.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">
                Required human reviewers
              </h3>
              <p className="text-sm">{run.required_reviewers.join(", ")}</p>
            </section>
          )}

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Findings</h3>
              <select
                value={domainFilter}
                onChange={(e) => setDomainFilter(e.target.value)}
                className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-xs"
              >
                <option value="ALL">All domains</option>
                {domains.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            {filteredFindings?.map((f) => (
              <div key={f.id} className="rounded border border-slate-200 dark:border-slate-800 p-4 text-sm space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium">{f.title}</p>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-slate-500">{f.domain}</span>
                    <RiskBadge risk={f.risk} />
                    <StatusBadge status={f.status} />
                  </div>
                </div>
                <p className="text-slate-600 dark:text-slate-300">{f.description}</p>
                {f.recommended_action && (
                  <p className="text-xs text-slate-500">
                    <span className="font-medium">Recommended action:</span> {f.recommended_action}
                  </p>
                )}
                {f.missing_information.length > 0 && (
                  <p className="text-xs text-slate-500">
                    <span className="font-medium">Missing:</span> {f.missing_information.join("; ")}
                  </p>
                )}
                {f.citations.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {f.citations.map((c) => (
                      <CitationBadge key={c.id} citation={c} />
                    ))}
                  </div>
                )}
                {f.human_review_required && (
                  <p className="text-xs text-amber-600 dark:text-amber-400">Human review required</p>
                )}
              </div>
            ))}
          </section>

          {codingCandidates && codingCandidates.length > 0 && (
            <section className="space-y-3">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                Coding eligibility matrix
              </h3>
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-800">
                    <th className="py-2 pr-4">Code system</th>
                    <th className="py-2 pr-4">Code</th>
                    <th className="py-2 pr-4">Service definition</th>
                    <th className="py-2 pr-4">Eligibility</th>
                    <th className="py-2 pr-4">Coverage</th>
                    <th className="py-2 pr-4">Payment</th>
                    <th className="py-2 pr-4">Billing</th>
                  </tr>
                </thead>
                <tbody>
                  {codingCandidates.map((c) => (
                    <tr key={c.id} className="border-b border-slate-100 dark:border-slate-900 align-top">
                      <td className="py-2 pr-4">{c.code_system}</td>
                      <td className="py-2 pr-4">{c.code || "—"}</td>
                      <td className="py-2 pr-4 max-w-xs">{c.service_definition}</td>
                      <td className="py-2 pr-4">
                        <StatusBadge status={c.eligibility_status} />
                      </td>
                      <td className="py-2 pr-4 text-slate-500">{c.coverage_status ?? "—"}</td>
                      <td className="py-2 pr-4 text-slate-500">{c.payment_status ?? "—"}</td>
                      <td className="py-2 pr-4 text-slate-500">{c.billing_status ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-xs text-slate-500">
                No candidate here is an approved billing instruction. Expert coding review is
                required regardless of eligibility_status.
              </p>
            </section>
          )}
        </>
      )}

      <div className="rounded border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950 p-4 text-xs">
        {DISCLAIMER}
      </div>
    </div>
  );
}
