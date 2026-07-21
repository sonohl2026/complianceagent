import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api, parseErrorDetail } from "../../api/client";
import type { AnalysisRun, QuickScanAssessment } from "../../types/analysis";
import type { Job } from "../../types/document";
import { StatusBadge } from "../StatusBadge";
import { RiskBadge } from "../VerdictBadge";
import { formatAnalysisStage } from "../../utils/analysisStages";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

// Same set app/services/parsing/dispatch.py's SUPPORTED_EXTENSIONS knows how
// to turn into text -- kept in sync by hand since the accept list is tiny
// and rarely changes; there's no cheap way to fetch it from the API without
// an extra round-trip just to populate a file picker's accept attribute.
const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".html", ".htm", ".md", ".txt"];

function asResult(value: AnalysisRun["quick_scan_result_json"]): QuickScanAssessment | null {
  return Object.keys(value).length > 0 ? (value as QuickScanAssessment) : null;
}

export function QuickScanLaunchPanel({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"file" | "text" | "url">("file");
  const [sourceText, setSourceText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: runs, refetch } = useQuery({
    queryKey: ["quick-scans", projectId],
    queryFn: () =>
      api
        .get<AnalysisRun[]>(`/projects/${projectId}/analyses`)
        .then((all) => all.filter((r) => r.analysis_type === "quick_scan")),
    refetchInterval: (query) => {
      const hasActive = query.state.data?.some((r) => r.status === "QUEUED" || r.status === "RUNNING");
      return hasActive ? 3000 : false;
    },
  });

  const resetInputs = () => {
    setSourceText("");
    setSourceUrl("");
    setFile(null);
  };

  const startMutation = useMutation({
    mutationFn: async () => {
      if (mode === "file" && file) {
        const formData = new FormData();
        formData.append("file", file);
        const response = await fetch(`${API_BASE_URL}/projects/${projectId}/quick-scans/upload`, {
          method: "POST",
          body: formData,
        });
        if (!response.ok) throw new Error(parseErrorDetail(await response.text(), response.statusText));
        return (await response.json()) as Job;
      }
      return api.post<Job>(`/projects/${projectId}/quick-scans`, {
        source_text: mode === "text" ? sourceText : undefined,
        source_url: mode === "url" ? sourceUrl : undefined,
      });
    },
    onSuccess: () => {
      resetInputs();
      queryClient.invalidateQueries({ queryKey: ["quick-scans", projectId] });
      refetch();
    },
  });

  const acceptFile = (candidate: File) => {
    const extension = candidate.name.slice(candidate.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(extension)) return;
    setFile(candidate);
  };

  const canSubmit =
    mode === "text" ? sourceText.trim().length > 0 : mode === "url" ? sourceUrl.trim().length > 0 : file !== null;

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500 max-w-xl">
        Drop a document mentioning the product (a clinical paper, press release, or one-pager
        works fine), paste text, or give a URL -- it's only used to identify the product.
        Regulatory, coding, coverage, and payment status are then looked up live from openFDA and
        the CMS Coverage API, not read from the document.
      </p>

      <div className="flex items-center rounded border border-slate-300 dark:border-slate-700 text-xs overflow-hidden w-fit">
        <button
          onClick={() => setMode("file")}
          className={`px-3 py-1.5 ${mode === "file" ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : "hover:bg-slate-100 dark:hover:bg-slate-900"}`}
        >
          Upload file
        </button>
        <button
          onClick={() => setMode("text")}
          className={`px-3 py-1.5 border-l border-slate-300 dark:border-slate-700 ${mode === "text" ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : "hover:bg-slate-100 dark:hover:bg-slate-900"}`}
        >
          Paste text
        </button>
        <button
          onClick={() => setMode("url")}
          className={`px-3 py-1.5 border-l border-slate-300 dark:border-slate-700 ${mode === "url" ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : "hover:bg-slate-100 dark:hover:bg-slate-900"}`}
        >
          URL
        </button>
      </div>

      {mode === "file" && (
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragOver(true);
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragOver(false);
            const dropped = e.dataTransfer.files?.[0];
            if (dropped) acceptFile(dropped);
          }}
          className={`flex flex-col items-center justify-center gap-1 rounded border-2 border-dashed px-4 py-8 text-center cursor-pointer transition-colors ${
            isDragOver
              ? "border-teal-600 bg-teal-700/5"
              : "border-slate-300 dark:border-slate-700 hover:border-slate-400 dark:hover:border-slate-600"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS.join(",")}
            className="hidden"
            onChange={(e) => {
              const picked = e.target.files?.[0];
              if (picked) acceptFile(picked);
              e.target.value = "";
            }}
          />
          {file ? (
            <>
              <p className="text-sm font-medium">{file.name}</p>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setFile(null);
                }}
                className="text-xs text-slate-500 hover:underline"
              >
                Remove
              </button>
            </>
          ) : (
            <>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                Drop a file here, or click to browse
              </p>
              <p className="text-xs text-slate-400">{ACCEPTED_EXTENSIONS.join(", ")}</p>
            </>
          )}
        </div>
      )}

      {mode === "text" && (
        <textarea
          value={sourceText}
          onChange={(e) => setSourceText(e.target.value)}
          rows={5}
          placeholder="Paste a document describing the product…"
          className="w-full rounded border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-sm"
        />
      )}

      {mode === "url" && (
        <input
          value={sourceUrl}
          onChange={(e) => setSourceUrl(e.target.value)}
          placeholder="https://…"
          className="w-full rounded border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-sm"
        />
      )}

      <div className="flex items-center gap-2">
        <button
          disabled={!canSubmit || startMutation.isPending}
          onClick={() => startMutation.mutate()}
          className="text-sm rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 disabled:opacity-50"
        >
          {startMutation.isPending ? "Starting…" : "Run quick scan"}
        </button>
        {startMutation.isError && (
          <span className="text-xs text-risk-critical">{(startMutation.error as Error).message}</span>
        )}
      </div>

      {runs && runs.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-800">
              <th className="py-2 pr-4">Started</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Product</th>
              <th className="py-2 pr-4">Maturity</th>
              <th className="py-2 pr-4">Risk</th>
              <th className="py-2 pr-4"></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => {
              const result = asResult(r.quick_scan_result_json);
              return (
                <tr key={r.id} className="border-b border-slate-100 dark:border-slate-900">
                  <td className="py-2 pr-4 text-slate-500">
                    {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                  </td>
                  <td className="py-2 pr-4">
                    <StatusBadge status={r.status} />
                    {r.current_stage && r.status === "RUNNING" && (
                      <span className="ml-2 text-xs text-slate-500">{formatAnalysisStage(r.current_stage)}</span>
                    )}
                  </td>
                  <td className="py-2 pr-4">{result?.product.name ?? "—"}</td>
                  <td className="py-2 pr-4">
                    {result?.scores.maturity_state === "SCORED" ? result.scores.maturity : "—"}
                  </td>
                  <td className="py-2 pr-4">
                    <RiskBadge risk={result?.scores.risk_flag ?? null} />
                  </td>
                  <td className="py-2 pr-4">
                    <Link to={`/analyses/${r.id}`} className="text-slate-600 dark:text-slate-300 hover:underline">
                      View
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
