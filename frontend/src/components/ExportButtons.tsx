import { useState } from "react";

import { parseErrorDetail } from "../api/client";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function downloadFile(path: string, filename: string) {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) throw new Error(parseErrorDetail(await response.text(), response.statusText));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function ExportButtons({ analysisId }: { analysisId: string }) {
  // Condensed (~6 pages, top findings only) is the default so re-running
  // analyses after small incremental changes doesn't mean re-reading a
  // 40-page document every time; extended is opt-in. Both are built from
  // the same already-computed analysis data, so switching modes costs
  // nothing extra.
  const [mode, setMode] = useState<"condensed" | "extended">("condensed");
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");
  const [busy, setBusy] = useState<"pdf" | "json" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const copyMarkdown = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/analyses/${analysisId}/export.md?mode=${mode}`);
      if (!response.ok) throw new Error(parseErrorDetail(await response.text(), response.statusText));
      const text = await response.text();
      await navigator.clipboard.writeText(text);
      setCopyState("copied");
      setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      setCopyState("error");
      setTimeout(() => setCopyState("idle"), 3000);
    }
  };

  const download = async (kind: "pdf" | "json") => {
    setBusy(kind);
    setError(null);
    try {
      const modeSuffix = kind === "pdf" ? `?mode=${mode}` : "";
      const modeLabel = kind === "pdf" ? `-${mode}` : "";
      await downloadFile(
        `/analyses/${analysisId}/export.${kind}${modeSuffix}`,
        `analysis-${analysisId}${modeLabel}.${kind}`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center rounded border border-slate-300 dark:border-slate-700 text-xs overflow-hidden">
        <button
          onClick={() => setMode("condensed")}
          className={`px-2 py-1.5 ${mode === "condensed" ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : "hover:bg-slate-100 dark:hover:bg-slate-900"}`}
          title="Verdict, executive summary, and top-priority findings only (~6 pages)"
        >
          Condensed
        </button>
        <button
          onClick={() => setMode("extended")}
          className={`px-2 py-1.5 border-l border-slate-300 dark:border-slate-700 ${mode === "extended" ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : "hover:bg-slate-100 dark:hover:bg-slate-900"}`}
          title="Every finding, grouped by domain, with full citations and the coding matrix"
        >
          Extended
        </button>
      </div>
      <button
        onClick={copyMarkdown}
        className="text-xs rounded border border-slate-300 dark:border-slate-700 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-900"
      >
        {copyState === "copied" ? "Copied ✓" : copyState === "error" ? "Copy failed" : "Copy as Markdown"}
      </button>
      <button
        onClick={() => download("pdf")}
        disabled={busy === "pdf"}
        className="text-xs rounded border border-slate-300 dark:border-slate-700 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-900 disabled:opacity-50"
      >
        {busy === "pdf" ? "Preparing PDF…" : "Download PDF"}
      </button>
      <button
        onClick={() => download("json")}
        disabled={busy === "json"}
        className="text-xs rounded border border-slate-300 dark:border-slate-700 px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-900 disabled:opacity-50"
      >
        {busy === "json" ? "Preparing…" : "Download JSON"}
      </button>
      {error && <span className="text-xs text-risk-critical">{error}</span>}
    </div>
  );
}
