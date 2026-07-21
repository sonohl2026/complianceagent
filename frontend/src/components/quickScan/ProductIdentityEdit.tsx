import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import type { AnalysisRun } from "../../types/analysis";

// Only scalar Stage-1 identity fields are editable here -- run_quick_scan_override
// (backend/app/services/quick_scan/pipeline.py::_apply_product_overrides) only
// applies target="product" overrides onto these exact Stage1Extraction fields;
// aliases/candidate_search_terms are list-typed and OverrideRequest.value is a
// plain string, so they're intentionally left out of this quick-edit form
// rather than built as a control that would silently do nothing useful.
const EDITABLE_FIELDS: { key: string; label: string }[] = [
  { key: "product_name", label: "Product name" },
  { key: "manufacturer", label: "Manufacturer" },
  { key: "intended_use", label: "Intended use" },
  { key: "technology_type", label: "Technology type" },
];

export function ProductIdentityEdit({ run }: { run: AnalysisRun }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});

  const overrideMutation = useMutation({
    mutationFn: () =>
      api.post(`/quick-scans/${run.id}/override`, {
        overrides: Object.entries(values)
          .filter(([, v]) => v.trim() !== "")
          .map(([key, value]) => ({ target: "product", key, value })),
      }),
    onSuccess: () => {
      setOpen(false);
      setValues({});
      queryClient.invalidateQueries({ queryKey: ["analysis", run.id] });
    },
  });

  const editedKeys = new Set(
    Object.keys(run.overrides_json)
      .filter((k) => k.startsWith("product."))
      .map((k) => k.replace(/^product\./, "")),
  );

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-xs rounded border border-slate-300 dark:border-slate-700 px-2 py-1 hover:bg-slate-100 dark:hover:bg-slate-900"
      >
        Edit identity
      </button>
    );
  }

  return (
    <div className="rounded border border-slate-200 dark:border-slate-800 p-4 space-y-3">
      <p className="text-xs text-slate-500">
        Correct the identified product below and re-run retrieval + synthesis against the fixed
        identity. Stage 1 extraction itself is not re-run -- your correction replaces it directly.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {EDITABLE_FIELDS.map(({ key, label }) => (
          <label key={key} className="text-xs space-y-1 block">
            <span className="text-slate-500">
              {label}
              {editedKeys.has(key) && (
                <span className="ml-1 rounded bg-teal-700/10 text-teal-800 dark:text-teal-400 px-1">
                  user-edited
                </span>
              )}
            </span>
            <input
              className="w-full rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1"
              value={values[key] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
            />
          </label>
        ))}
      </div>
      {overrideMutation.isError && (
        <p className="text-xs text-risk-critical">{(overrideMutation.error as Error).message}</p>
      )}
      <div className="flex items-center gap-2">
        <button
          disabled={overrideMutation.isPending}
          onClick={() => overrideMutation.mutate()}
          className="text-xs rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1.5 disabled:opacity-50"
        >
          {overrideMutation.isPending ? "Re-running…" : "Save and re-run"}
        </button>
        <button
          onClick={() => setOpen(false)}
          className="text-xs rounded border border-slate-300 dark:border-slate-700 px-3 py-1.5"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
