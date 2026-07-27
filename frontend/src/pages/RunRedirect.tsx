import { useQuery } from "@tanstack/react-query";
import { Navigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { AnalysisRun } from "../types/analysis";

/** Right after starting a scan the composer only knows the new run's id
 * (from the enqueued Job), not the product it belongs to -- this resolves
 * that one hop and lands on the product's actual results page. */
export function RunRedirect() {
  const { runId } = useParams<{ runId: string }>();
  const { data: run } = useQuery({
    queryKey: ["analysis", runId],
    queryFn: () => api.get<AnalysisRun>(`/analyses/${runId}`),
  });

  if (!run) return <p className="text-sm text-slate-500">Loading…</p>;
  if (!run.product_id) return <p className="text-sm text-risk-critical">This run has no associated product.</p>;
  return <Navigate to={`/products/${run.product_id}`} replace />;
}
