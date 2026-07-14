import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { RiskBadge, VerdictBadge } from "../components/VerdictBadge";
import { StatusBadge } from "../components/StatusBadge";
import type { DashboardSummary } from "../types/dashboard";

interface HealthResponse {
  status: string;
  database: string;
}

function StatCard({ label, value, to }: { label: string; value: number; to?: string }) {
  const content = (
    <div className="rounded border border-slate-200 dark:border-slate-800 p-4">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-2xl font-semibold">{value}</p>
    </div>
  );
  return to ? <Link to={to}>{content}</Link> : content;
}

export function Dashboard() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<HealthResponse>("/health"),
    refetchInterval: 15000,
  });

  const { data: summary, isLoading } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => api.get<DashboardSummary>("/dashboard/summary"),
    refetchInterval: 15000,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Dashboard</h2>
        <div className="flex items-center gap-4">
          {health && (
            <span className="text-xs text-slate-500">
              API{" "}
              <span className={health.status === "ok" ? "text-risk-low" : "text-risk-high"}>
                {health.status}
              </span>{" "}
              · DB{" "}
              <span className={health.database === "ok" ? "text-risk-low" : "text-risk-high"}>
                {health.database}
              </span>
            </span>
          )}
          <Link
            to="/new-analysis"
            className="rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1.5 text-sm"
          >
            + New analysis
          </Link>
        </div>
      </div>

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}

      {summary && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Projects" value={summary.project_count} to="/new-analysis" />
            <StatCard label="Products" value={summary.product_count} />
            <StatCard label="Analyses run" value={summary.analysis_count} to="/analyses" />
            <StatCard label="Open compliance issues" value={summary.open_compliance_issue_count} />
          </div>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
              Recent analyses
            </h3>
            {summary.recent_analyses.length === 0 && (
              <p className="text-sm text-slate-500">
                No analyses yet —{" "}
                <Link to="/new-analysis" className="underline">
                  start a new analysis
                </Link>{" "}
                to get going.
              </p>
            )}
            {summary.recent_analyses.length > 0 && (
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
                  {summary.recent_analyses.map((r) => (
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
          </section>
        </>
      )}
    </div>
  );
}
