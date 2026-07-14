import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Alert } from "../types/monitoring";

const CATEGORY_COLORS: Record<string, string> = {
  NEW_CLAIM: "text-risk-critical",
  REMOVED_DISCLAIMER: "text-risk-critical",
  FDA_STATUS_LANGUAGE: "text-risk-critical",
  PRICING: "text-amber-600 dark:text-amber-400",
  INTENDED_USE: "text-risk-critical",
  COSMETIC: "text-slate-500",
  OTHER: "text-amber-600 dark:text-amber-400",
};

export function Monitoring() {
  const queryClient = useQueryClient();
  const [showAcknowledged, setShowAcknowledged] = useState(false);

  const { data: alerts, isLoading } = useQuery({
    queryKey: ["alerts", showAcknowledged],
    queryFn: () => api.get<Alert[]>(`/alerts${showAcknowledged ? "" : "?acknowledged=false"}`),
  });

  const acknowledgeMutation = useMutation({
    mutationFn: (id: string) => api.post(`/alerts/${id}/acknowledge`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Monitoring</h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showAcknowledged}
            onChange={(e) => setShowAcknowledged(e.target.checked)}
          />
          Show acknowledged
        </label>
      </div>
      <p className="text-sm text-slate-500">
        Material-change alerts raised after scheduled recrawls (set these up from a project's
        Website panel). A deterministic hash comparison decides whether a page changed at all; a
        model pass decides only whether an already-detected change is material to compliance —
        never whether something changed in the first place.
      </p>

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {alerts && alerts.length === 0 && (
        <p className="text-sm text-slate-500">
          {showAcknowledged ? "No alerts yet." : "No unacknowledged alerts."}
        </p>
      )}
      {alerts && alerts.length > 0 && (
        <div className="space-y-3">
          {alerts.map((a) => (
            <div
              key={a.id}
              className={`rounded border p-4 text-sm space-y-1 ${
                a.acknowledged
                  ? "border-slate-200 dark:border-slate-800 opacity-60"
                  : "border-amber-300 dark:border-amber-700"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className={`text-xs font-semibold ${CATEGORY_COLORS[a.category] ?? "text-slate-500"}`}>
                  {a.category}
                </span>
                {!a.acknowledged && (
                  <button
                    className="text-xs text-slate-600 dark:text-slate-300 underline shrink-0"
                    onClick={() => acknowledgeMutation.mutate(a.id)}
                  >
                    Acknowledge
                  </button>
                )}
              </div>
              <p>{a.summary}</p>
              <div className="flex flex-wrap items-center gap-x-3 text-xs text-slate-500">
                <Link to={`/projects/${a.project_id}`} className="hover:underline">
                  {a.project_name}
                </Link>
                <span className="truncate max-w-xs" title={a.canonical_url}>
                  {a.canonical_url}
                </span>
                <span>{new Date(a.created_at).toLocaleString()}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
