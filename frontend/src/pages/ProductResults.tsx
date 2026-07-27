import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import { ConfirmationPanel } from "../components/quickScan/ConfirmationPanel";
import { QuickScanDashboard } from "../components/quickScan/QuickScanDashboard";
import type { AnalysisRun } from "../types/analysis";
import type { Product } from "../types/product";

function useLatestRun(productId: string) {
  return useQuery({
    queryKey: ["analysis", "latest-for-product", productId],
    queryFn: async () => {
      const runs = await api.get<AnalysisRun[]>(`/products/${productId}/runs`);
      return runs[0] ?? null;
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "QUEUED" || status === "RUNNING"
        ? 3000
        : status === "AWAITING_CONFIRMATION"
          ? 15000
          : false;
    },
  });
}

/** MVP lockdown Step 1: a product's results page -- the only other surface
 * besides the Products list. */
export function ProductResults() {
  const { productId } = useParams<{ productId: string }>();

  const { data: product } = useQuery({
    queryKey: ["product", productId],
    queryFn: () => api.get<Product>(`/products/${productId}`),
  });
  const { data: run, isLoading } = useLatestRun(productId!);

  if (isLoading || !product) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div className="space-y-4">
      <Link to="/" className="text-xs text-slate-500 hover:underline">
        ← All products
      </Link>

      {!run && <p className="text-sm text-slate-500">No analysis has been run for {product.name} yet.</p>}

      {run && run.status === "AWAITING_CONFIRMATION" && <ConfirmationPanel run={run} />}

      {run && run.status !== "AWAITING_CONFIRMATION" && <QuickScanDashboard run={run} />}
    </div>
  );
}
