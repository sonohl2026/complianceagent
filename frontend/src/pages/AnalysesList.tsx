import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { RiskBadge, VerdictBadge } from "../components/VerdictBadge";
import { StatusBadge } from "../components/StatusBadge";
import type { RecentAnalysisRow } from "../types/dashboard";

export function AnalysesList() {
  const { data: analyses, isLoading } = useQuery({
    queryKey: ["all-analyses"],
    queryFn: () => api.get<RecentAnalysisRow[]>("/analyses"),
    refetchInterval: (query) => {
      const hasActive = query.state.data?.some((r) => r.status === "QUEUED" || r.status === "RUNNING");
      return hasActive ? 3000 : false;
    },
  });

  return (
    <div className="space-y-4 max-w-5xl">
      <h2 className="text-lg font-semibold">Analyses</h2>
      <p className="text-sm text-slate-500">
        Every compliance analysis run across all projects. Start a new one from within a project's
        page.
      </p>

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {analyses && analyses.length === 0 && <p className="text-sm text-slate-500">No analyses yet.</p>}
      {analyses && analyses.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-800">
              <th className="py-2 pr-4">Project</th>
              <th className="py-2 pr-4">Product</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Verdict</th>
              <th className="py-2 pr-4">Risk</th>
              <th className="py-2 pr-4">Readiness</th>
              <th className="py-2 pr-4">Started</th>
            </tr>
          </thead>
          <tbody>
            {analyses.map((r) => (
              <tr key={r.id} className="border-b border-slate-100 dark:border-slate-900">
                <td className="py-2 pr-4">
                  <Link to={`/projects/${r.project_id}`} className="hover:underline">
                    {r.project_name}
                  </Link>
                </td>
                <td className="py-2 pr-4 text-slate-500">{r.product_name ?? "—"}</td>
                <td className="py-2 pr-4">
                  <StatusBadge status={r.status} />
                </td>
                <td className="py-2 pr-4">
                  <VerdictBadge verdict={r.overall_verdict} />
                </td>
                <td className="py-2 pr-4">
                  <RiskBadge risk={r.overall_risk} />
                </td>
                <td className="py-2 pr-4">{r.readiness_score ?? "—"}</td>
                <td className="py-2 pr-4 text-slate-500">
                  <Link to={`/analyses/${r.id}`} className="hover:underline">
                    {new Date(r.created_at).toLocaleString()}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
