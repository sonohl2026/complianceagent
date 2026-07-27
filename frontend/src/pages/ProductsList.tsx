import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { RiskBadge } from "../components/VerdictBadge";
import { StatusBadge } from "../components/StatusBadge";
import { Composer } from "../components/quickScan/Composer";
import type { Job } from "../types/document";
import type { ProductSummary } from "../types/product";

/** MVP lockdown Step 1: the app's home page. A Products list and, from
 * here, the one entry point to start a new analysis -- nothing else. */
export function ProductsList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: products, isLoading } = useQuery({
    queryKey: ["products"],
    queryFn: () => api.get<ProductSummary[]>("/products"),
    refetchInterval: (query) => {
      const hasActive = query.state.data?.some(
        (p) => p.latest_run_status === "QUEUED" || p.latest_run_status === "RUNNING",
      );
      return hasActive ? 3000 : false;
    },
  });

  const handleStarted = (job: Job) => {
    queryClient.invalidateQueries({ queryKey: ["products"] });
    if (job.related_id) navigate(`/runs/${job.related_id}`);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <h2 className="text-lg font-semibold">Products</h2>

      <Composer onStarted={handleStarted} />

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}

      {products && products.length === 0 && (
        <p className="text-sm text-slate-500">No products yet -- run your first analysis above.</p>
      )}

      {products && products.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-800">
              <th className="py-2 pr-4">Product</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Maturity</th>
              <th className="py-2 pr-4">Risk</th>
              <th className="py-2 pr-4">Last updated</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.id} className="border-b border-slate-100 dark:border-slate-900">
                <td className="py-2 pr-4">
                  <Link to={`/products/${p.id}`} className="font-medium hover:underline">
                    {p.name}
                  </Link>
                </td>
                <td className="py-2 pr-4">
                  {p.latest_run_status ? <StatusBadge status={p.latest_run_status} /> : "—"}
                </td>
                <td className="py-2 pr-4">
                  {p.maturity_state === "SCORED" ? p.maturity : p.maturity_state === "NOT_SCORED" ? "early-stage" : "—"}
                </td>
                <td className="py-2 pr-4">
                  <RiskBadge risk={p.risk_flag} />
                </td>
                <td className="py-2 pr-4 text-slate-500">
                  {p.latest_run_created_at ? new Date(p.latest_run_created_at).toLocaleString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
