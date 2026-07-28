import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { RiskBadge } from "../components/VerdictBadge";
import { StatusBadge } from "../components/StatusBadge";
import { Composer } from "../components/quickScan/Composer";
import { RenameProductControl } from "../components/quickScan/RenameProductControl";
import type { Job } from "../types/document";
import type { ProductSummary } from "../types/product";

/** MVP lockdown Step 1: the app's home page. A Products list and, from
 * here, the one entry point to start a new analysis -- nothing else. */
export function ProductsList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);

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

  const deleteProduct = useMutation({
    mutationFn: (id: string) => api.del(`/products/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      setConfirmDeleteId(null);
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

      {deleteProduct.isError && (
        <p className="text-xs text-risk-critical">{(deleteProduct.error as Error).message}</p>
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
              <th className="py-2 pr-4"></th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.id} className="border-b border-slate-100 dark:border-slate-900">
                <td className="py-2 pr-4">
                  <div className="flex items-center gap-2">
                    {renamingId !== p.id && (
                      <Link to={`/products/${p.id}`} className="font-medium hover:underline">
                        {p.name}
                      </Link>
                    )}
                    <RenameProductControl
                      productId={p.id}
                      currentName={p.name}
                      onEditingChange={(editing) => setRenamingId(editing ? p.id : null)}
                    />
                  </div>
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
                <td className="py-2 pr-4">
                  {confirmDeleteId === p.id ? (
                    <div className="flex items-center gap-2 shrink-0 text-xs">
                      <span className="text-slate-500">Delete "{p.name}" and all its scans?</span>
                      <button
                        className="text-risk-critical underline disabled:opacity-50"
                        disabled={deleteProduct.isPending}
                        onClick={() => deleteProduct.mutate(p.id)}
                      >
                        Confirm
                      </button>
                      <button className="text-slate-500 underline" onClick={() => setConfirmDeleteId(null)}>
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-3 shrink-0 text-xs">
                      <Link to={`/products/${p.id}`} className="text-slate-500 hover:underline">
                        Re-run
                      </Link>
                      <button
                        className="text-slate-400 hover:text-risk-critical"
                        title="Delete product"
                        onClick={() => setConfirmDeleteId(p.id)}
                      >
                        Delete
                      </button>
                    </div>
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
