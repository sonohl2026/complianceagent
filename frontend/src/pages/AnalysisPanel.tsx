import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { RiskBadge, VerdictBadge } from "../components/VerdictBadge";
import { StatusBadge } from "../components/StatusBadge";
import type { AnalysisRun } from "../types/analysis";
import type { Job } from "../types/document";
import { formatAnalysisStage } from "../utils/analysisStages";

export function AnalysisPanel({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();

  const { data: runs, refetch } = useQuery({
    queryKey: ["analyses", projectId],
    queryFn: () => api.get<AnalysisRun[]>(`/projects/${projectId}/analyses`),
    refetchInterval: (query) => {
      const hasActive = query.state.data?.some((r) => r.status === "QUEUED" || r.status === "RUNNING");
      return hasActive ? 3000 : false;
    },
  });

  const startMutation = useMutation({
    mutationFn: () => api.post<Job>(`/projects/${projectId}/analyses`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analyses", projectId] });
      refetch();
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (analysisId: string) => api.post(`/analyses/${analysisId}/cancel`),
    onSuccess: () => refetch(),
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-500 max-w-xl">
          Runs the staged compliance pipeline (input audit → fact extraction → claim extraction →
          regulatory/coding/coverage/payment/billing/marketing analysis → synthesis → citation
          audit) against this project's documents and the shared authority library.
        </p>
        <button
          className="text-sm rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 whitespace-nowrap disabled:opacity-50"
          disabled={startMutation.isPending}
          onClick={() => startMutation.mutate()}
        >
          New analysis
        </button>
      </div>
      {startMutation.isError && (
        <p className="text-xs text-risk-critical">{(startMutation.error as Error).message}</p>
      )}

      {runs && runs.length === 0 && (
        <p className="text-sm text-slate-500">
          No analyses yet. Make sure an OpenRouter API key and model are set in Settings first.
        </p>
      )}
      {runs && runs.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-800">
              <th className="py-2 pr-4">Started</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Verdict</th>
              <th className="py-2 pr-4">Risk</th>
              <th className="py-2 pr-4">Readiness</th>
              <th className="py-2 pr-4"></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className="border-b border-slate-100 dark:border-slate-900">
                <td className="py-2 pr-4 text-slate-500">
                  {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                </td>
                <td className="py-2 pr-4">
                  <StatusBadge status={r.status} />
                  {r.current_stage && r.status === "RUNNING" && (
                    <span className="ml-2 text-xs text-slate-500">{formatAnalysisStage(r.current_stage)}</span>
                  )}
                </td>
                <td className="py-2 pr-4">
                  <VerdictBadge verdict={r.overall_verdict} />
                </td>
                <td className="py-2 pr-4">
                  <RiskBadge risk={r.overall_risk} />
                </td>
                <td className="py-2 pr-4" title={r.readiness_score_note ?? undefined}>
                  {r.readiness_score ?? "—"}
                  {r.readiness_score_note && <span className="text-amber-600 dark:text-amber-400">*</span>}
                </td>
                <td className="py-2 pr-4 space-x-2">
                  <Link to={`/analyses/${r.id}`} className="text-slate-600 dark:text-slate-300 hover:underline">
                    View
                  </Link>
                  {(r.status === "QUEUED" || r.status === "RUNNING") && (
                    <button
                      className="text-risk-critical hover:underline"
                      onClick={() => cancelMutation.mutate(r.id)}
                    >
                      Cancel
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
