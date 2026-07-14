import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { RiskBadge } from "../components/VerdictBadge";
import type { ExtractedClaim } from "../types/claim";

const RISK_OPTIONS = ["", "CRITICAL", "HIGH", "MEDIUM", "LOW"];
const REVIEW_STATUS_OPTIONS = ["PENDING_REVIEW", "REVIEWED", "ACTIONED"];

const DISPOSITION_COLORS: Record<string, string> = {
  RETAIN: "text-risk-low",
  QUALIFY: "text-amber-600 dark:text-amber-400",
  REWRITE: "text-amber-600 dark:text-amber-400",
  REMOVE: "text-risk-critical",
  QUARANTINE: "text-risk-critical",
};

export function ClaimsRegister() {
  const queryClient = useQueryClient();
  const [riskFilter, setRiskFilter] = useState("");
  const [reviewFilter, setReviewFilter] = useState("");

  const { data: claims, isLoading } = useQuery({
    queryKey: ["claims", riskFilter, reviewFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (riskFilter) params.set("risk", riskFilter);
      if (reviewFilter) params.set("review_status", reviewFilter);
      const query = params.toString();
      return api.get<ExtractedClaim[]>(`/claims${query ? `?${query}` : ""}`);
    },
  });

  const updateMutation = useMutation({
    mutationFn: (vars: { id: string; review_status: string }) =>
      api.put(`/claims/${vars.id}`, { review_status: vars.review_status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["claims"] }),
  });

  return (
    <div className="space-y-4 max-w-6xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Claims Register</h2>
      </div>
      <p className="text-sm text-slate-500">
        Every marketing/website claim extracted during a compliance analysis, across all projects,
        with the model's own assessment of evidence status and recommended disposition. Mark
        claims reviewed as your team works through them.
      </p>

      <div className="flex gap-2">
        <select
          value={riskFilter}
          onChange={(e) => setRiskFilter(e.target.value)}
          className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
        >
          {RISK_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {r || "All risk levels"}
            </option>
          ))}
        </select>
        <select
          value={reviewFilter}
          onChange={(e) => setReviewFilter(e.target.value)}
          className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
        >
          <option value="">All review statuses</option>
          {REVIEW_STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {claims && claims.length === 0 && (
        <p className="text-sm text-slate-500">No claims match these filters.</p>
      )}
      {claims && claims.length > 0 && (
        <div className="space-y-3">
          {claims.map((c) => (
            <div key={c.id} className="rounded border border-slate-200 dark:border-slate-800 p-4 text-sm space-y-2">
              <div className="flex items-start justify-between gap-2">
                <p className="italic flex-1">"{c.exact_text}"</p>
                <div className="flex items-center gap-2 shrink-0">
                  <RiskBadge risk={c.risk} />
                  <span
                    className={`text-xs font-medium ${DISPOSITION_COLORS[c.recommended_disposition] ?? ""}`}
                  >
                    {c.recommended_disposition}
                  </span>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
                <Link to={`/projects/${c.project_id}`} className="hover:underline">
                  {c.project_name}
                </Link>
                <span>{c.claim_category}</span>
                <span>{c.express_or_implied}</span>
                <span>Evidence: {c.evidence_status}</span>
                {c.audience && <span>Audience: {c.audience}</span>}
              </div>
              {c.proposed_replacement && (
                <p className="text-xs text-slate-500">
                  <span className="font-medium">Proposed replacement:</span> {c.proposed_replacement}
                </p>
              )}
              <div className="flex items-center gap-2 pt-1">
                <span className="text-xs text-slate-500">Review status:</span>
                <select
                  value={c.review_status}
                  onChange={(e) => updateMutation.mutate({ id: c.id, review_status: e.target.value })}
                  className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-0.5 text-xs"
                >
                  {REVIEW_STATUS_OPTIONS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
