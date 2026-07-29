import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import type { AnalysisRun } from "../../types/analysis";
import { ProductIdentityEdit } from "./ProductIdentityEdit";

const SOURCE_LABELS: Record<string, string> = {
  openfda_510k: "FDA 510(k) clearance",
  openfda_pma: "FDA PMA approval",
  openfda_classification: "FDA device classification",
  openfda_recall: "FDA recall record",
  openfda_enforcement: "FDA enforcement record",
  openfda_event: "FDA adverse event record",
  openfda_udi: "FDA UDI record",
  ncd: "CMS national coverage determination",
  lcd: "CMS local coverage determination",
  article: "CMS coverage article",
  fee_schedule_lookup: "CMS fee schedule",
};

const IDENTIFIER_KEYS = ["k_number", "pma_number", "product_code", "device_name", "udi_di"];

interface RetrievalSource {
  status: "HIT" | "MISS" | "RETRIEVAL_FAILURE";
  data: { document?: Record<string, unknown> } | null;
}

interface CandidateSite {
  title: string;
  url: string;
  snippet: string;
}

interface SourceGroup {
  product_name: string;
  manufacturer: string;
  source_indices: number[];
}

interface SourceConflict {
  groups: SourceGroup[];
}

/** Shown instead of the usual identity-confirmation UI when 2+ attached
 * sources were detected to describe different products (see
 * source_divergence.py / quick_scan_tasks.py::_run_source_check). Picking
 * a group re-merges only that group's own sources and proceeds through the
 * normal pipeline -- everything else about this run behaves exactly like a
 * single-source submission from here on. */
function SourceConflictPanel({ run, conflict }: { run: AnalysisRun; conflict: SourceConflict }) {
  const queryClient = useQueryClient();

  const resolve = useMutation({
    mutationFn: (groupIndex: number) =>
      api.post(`/quick-scans/${run.id}/resolve-source-conflict`, { group_index: groupIndex }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analysis", run.id] });
      if (run.product_id) {
        queryClient.invalidateQueries({ queryKey: ["analysis", "latest-for-product", run.product_id] });
      }
    },
  });

  return (
    <div className="rounded border border-slate-200 dark:border-slate-800 p-5 space-y-4 max-w-2xl">
      <div>
        <h3 className="text-sm font-semibold">Which product do you want to analyze?</h3>
        <p className="text-xs text-slate-500 mt-1">
          The sources you attached look like they describe more than one distinct product. Pick
          the one you want this run to focus on -- the other source(s) won't be used.
        </p>
      </div>

      <div className="space-y-3">
        {conflict.groups.map((group, i) => (
          <div key={i} className="rounded border border-slate-200 dark:border-slate-800 p-3 space-y-2">
            <div>
              <p className="text-sm font-semibold">{group.product_name}</p>
              <p className="text-xs text-slate-500">{group.manufacturer || "Manufacturer unknown"}</p>
              <p className="text-xs text-slate-400 mt-1">
                From attached source{group.source_indices.length > 1 ? "s" : ""}{" "}
                {group.source_indices.map((idx) => idx + 1).join(", ")}
              </p>
            </div>
            <button
              disabled={resolve.isPending}
              onClick={() => resolve.mutate(i)}
              className="text-sm rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-4 py-2 disabled:opacity-50"
            >
              {resolve.isPending ? "Analyzing…" : `Analyze ${group.product_name}`}
            </button>
          </div>
        ))}
      </div>

      {resolve.isError && <p className="text-xs text-risk-critical">{(resolve.error as Error).message}</p>}
    </div>
  );
}

function recordLabel(sourceName: string, source: RetrievalSource): { type: string; number: string | null } {
  const type = SOURCE_LABELS[sourceName] ?? sourceName;
  const document = source.data?.document ?? {};
  for (const key of IDENTIFIER_KEYS) {
    const value = document[key];
    if (typeof value === "string" && value) return { type, number: value };
  }
  return { type, number: null };
}

/** Dispatches to whichever confirmation UI this paused run actually needs --
 * a source conflict (2+ attached sources describing different products) vs.
 * the usual name-only identity confirmation. Kept as a plain dispatcher with
 * no hooks of its own so each branch's hooks stay unconditional within
 * their own component (React's rules of hooks). */
export function ConfirmationPanel({ run }: { run: AnalysisRun }) {
  const sourceConflict = run.retrieval_bundle_json.source_conflict as SourceConflict | undefined;
  if (sourceConflict) {
    return <SourceConflictPanel run={run} conflict={sourceConflict} />;
  }
  return <IdentityConfirmationPanel run={run} />;
}

/** MVP lockdown Step 3: shown when a name-only submission has paused at
 * AWAITING_CONFIRMATION after retrieval, before the (expensive, hard-to-undo)
 * Stage 3 synthesis call. Reuses ProductIdentityEdit verbatim -- same
 * mechanism as a post-completion correction, just surfaced mid-run. */
function IdentityConfirmationPanel({ run }: { run: AnalysisRun }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);

  const stage1 = (run.retrieval_bundle_json.stage1 ?? {}) as {
    product_name?: string;
    manufacturer?: string;
  };
  const sources = (run.retrieval_bundle_json.sources ?? {}) as Record<string, RetrievalSource>;
  const hits = Object.entries(sources).filter(([, s]) => s.status === "HIT");
  const identityFound = hits.length > 0;
  const candidateSite = run.retrieval_bundle_json.candidate_site as CandidateSite | undefined;

  const invalidateRun = () => {
    queryClient.invalidateQueries({ queryKey: ["analysis", run.id] });
    if (run.product_id) {
      queryClient.invalidateQueries({ queryKey: ["analysis", "latest-for-product", run.product_id] });
    }
  };

  const confirm = useMutation({
    mutationFn: () => api.post(`/quick-scans/${run.id}/override`, { overrides: [] }),
    onSuccess: invalidateRun,
  });

  const confirmSite = useMutation({
    mutationFn: () => api.post(`/quick-scans/${run.id}/confirm-site`, { url: candidateSite?.url }),
    onSuccess: invalidateRun,
  });

  return (
    <div className="rounded border border-slate-200 dark:border-slate-800 p-5 space-y-4 max-w-2xl">
      <div>
        <h3 className="text-sm font-semibold">Is this the right product?</h3>
        <p className="text-xs text-slate-500 mt-1">
          We looked up "{stage1.product_name}" before running the full assessment -- confirm it's
          right, or correct it below.
        </p>
      </div>

      {identityFound && (
        <div className="space-y-2">
          <p className="text-lg font-semibold">{stage1.product_name}</p>
          <p className="text-sm text-slate-500">{stage1.manufacturer || "Manufacturer unknown"}</p>
          <div className="flex flex-wrap gap-2 pt-1">
            {hits.map(([sourceName, source]) => {
              const { type, number } = recordLabel(sourceName, source);
              return (
                <span
                  key={sourceName}
                  className="text-xs rounded border border-teal-700/30 bg-teal-700/5 text-teal-800 dark:text-teal-400 px-2 py-0.5"
                >
                  {type}
                  {number ? `: ${number}` : ""}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {!identityFound && candidateSite && (
        <div className="space-y-2">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            No FDA or CMS record turned up under "{stage1.product_name}", but this looks like it
            might be the product's own site:
          </p>
          <div className="rounded border border-slate-200 dark:border-slate-800 p-3">
            <a
              href={candidateSite.url}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-medium text-teal-700 dark:text-teal-400 hover:underline"
            >
              {candidateSite.title || candidateSite.url}
            </a>
            <p className="text-xs text-slate-500 mt-1 break-all">{candidateSite.url}</p>
            {candidateSite.snippet && (
              <p className="text-xs text-slate-500 mt-1">{candidateSite.snippet}</p>
            )}
          </div>
        </div>
      )}

      {!identityFound && !candidateSite && (
        <div className="rounded border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950 p-3 text-sm">
          No FDA or CMS coverage record turned up under "{stage1.product_name}", and no candidate
          site turned up either. Correct the name below, or start over with a document/link
          instead.
        </div>
      )}

      {confirm.isError && <p className="text-xs text-risk-critical">{(confirm.error as Error).message}</p>}
      {confirmSite.isError && <p className="text-xs text-risk-critical">{(confirmSite.error as Error).message}</p>}

      <div className="flex items-center gap-2">
        {identityFound && !editing && (
          <button
            disabled={confirm.isPending}
            onClick={() => confirm.mutate()}
            className="text-sm rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-4 py-2 disabled:opacity-50"
          >
            {confirm.isPending ? "Continuing…" : "Yes, that's it"}
          </button>
        )}
        {!identityFound && candidateSite && !editing && (
          <button
            disabled={confirmSite.isPending}
            onClick={() => confirmSite.mutate()}
            className="text-sm rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-4 py-2 disabled:opacity-50"
          >
            {confirmSite.isPending ? "Analyzing…" : "Yes, that's it"}
          </button>
        )}
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            className="text-sm rounded border border-slate-300 dark:border-slate-700 px-4 py-2"
          >
            {identityFound
              ? "Not quite -- correct it"
              : candidateSite
                ? "Not quite -- correct the name"
                : "Correct the name"}
          </button>
        )}
      </div>

      {editing && <ProductIdentityEdit run={run} forceOpen onDone={() => setEditing(false)} />}
    </div>
  );
}
