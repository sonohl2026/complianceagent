import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import { Composer } from "../components/quickScan/Composer";
import { ConfirmationPanel } from "../components/quickScan/ConfirmationPanel";
import { QuickScanDashboard } from "../components/quickScan/QuickScanDashboard";
import type { AnalysisRun } from "../types/analysis";
import type { Job } from "../types/document";
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

const ACTIVE_STATUSES = new Set(["QUEUED", "RUNNING", "AWAITING_CONFIRMATION"]);

/** MVP lockdown Step 1: a product's results page -- the only other surface
 * besides the Products list. */
export function ProductResults() {
  const { productId } = useParams<{ productId: string }>();
  const queryClient = useQueryClient();
  const [showComposer, setShowComposer] = useState(false);

  const { data: product } = useQuery({
    queryKey: ["product", productId],
    queryFn: () => api.get<Product>(`/products/${productId}`),
  });
  const { data: run, isLoading } = useLatestRun(productId!);

  if (isLoading || !product) return <p className="text-sm text-slate-500">Loading…</p>;

  const isActive = run !== null && run !== undefined && ACTIVE_STATUSES.has(run.status);

  const handleStarted = (_job: Job) => {
    setShowComposer(false);
    queryClient.invalidateQueries({ queryKey: ["analysis", "latest-for-product", productId] });
    queryClient.invalidateQueries({ queryKey: ["products"] });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Link to="/" className="text-xs text-slate-500 hover:underline">
          ← All products
        </Link>
        {!isActive && !showComposer && (
          <button
            onClick={() => setShowComposer(true)}
            className="text-xs rounded border border-slate-300 dark:border-slate-700 px-2 py-1 hover:bg-slate-100 dark:hover:bg-slate-900"
          >
            Run a new scan
          </button>
        )}
      </div>

      {(showComposer || !run) && (
        <Composer
          onStarted={handleStarted}
          productId={productId}
          defaultName={product.name === "Untitled product" ? "" : product.name}
        />
      )}

      {run && run.status === "AWAITING_CONFIRMATION" && <ConfirmationPanel run={run} />}

      {run && run.status !== "AWAITING_CONFIRMATION" && <QuickScanDashboard run={run} />}
    </div>
  );
}
