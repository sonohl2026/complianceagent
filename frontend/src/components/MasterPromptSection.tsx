import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api, parseErrorDetail } from "../api/client";
import type { PromptVersionDetail, PromptVersionSummary } from "../types/promptVersion";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

/**
 * Lets the master compliance system prompt be swapped in from the UI, the
 * same way an OpenRouter API key is -- upload a PDF/DOCX/MD/TXT, the backend
 * confirms it can actually extract readable text from it, and it becomes
 * the active version immediately. Every upload is kept as a permanent,
 * never-overwritten version row, so switching back to an earlier one is
 * just "Activate" on it -- nothing is lost.
 */
export function MasterPromptSection() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [changeSummary, setChangeSummary] = useState("");
  const [confirmation, setConfirmation] = useState<PromptVersionDetail | null>(null);

  const { data: versions, refetch: refetchVersions } = useQuery({
    queryKey: ["prompt-versions"],
    queryFn: () => api.get<PromptVersionSummary[]>("/prompts/master/versions"),
  });

  const active = versions?.find((v) => v.is_active) ?? null;

  const { data: activeDetail } = useQuery({
    queryKey: ["prompt-version-detail", active?.id],
    queryFn: () => api.get<PromptVersionDetail>(`/prompts/master/versions/${active!.id}`),
    enabled: !!active,
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      if (changeSummary.trim()) formData.append("change_summary", changeSummary.trim());
      const response = await fetch(`${API_BASE_URL}/prompts/master/upload`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error(parseErrorDetail(await response.text(), response.statusText));
      return (await response.json()) as PromptVersionDetail;
    },
    onSuccess: (detail) => {
      setConfirmation(detail);
      setChangeSummary("");
      queryClient.invalidateQueries({ queryKey: ["prompt-versions"] });
      queryClient.invalidateQueries({ queryKey: ["prompt-version-detail"] });
    },
  });

  const activateMutation = useMutation({
    mutationFn: (versionId: string) => api.post<PromptVersionDetail>(`/prompts/master/versions/${versionId}/activate`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompt-versions"] });
      queryClient.invalidateQueries({ queryKey: ["prompt-version-detail"] });
      refetchVersions();
    },
  });

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        Master Compliance Prompt
      </h3>
      <p className="text-xs text-slate-500">
        This is the controlling reasoning policy for every analysis — upload a replacement
        (PDF/DOCX/MD/TXT) to swap it in, the same way you'd swap in a new API key. Every upload is
        parsed and checked for readable text before it's activated, and every previous version
        stays available to switch back to.
      </p>

      {active && (
        <div className="rounded border border-slate-200 dark:border-slate-800 p-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="font-medium">Active: version {active.version_label}</span>
            <span className="text-xs text-slate-500">
              {new Date(active.created_at).toLocaleString()}
            </span>
          </div>
          {activeDetail && (
            <p className="text-xs text-slate-500 mt-1">
              {activeDetail.word_count.toLocaleString()} words ·{" "}
              {activeDetail.character_count.toLocaleString()} characters
            </p>
          )}
          {active.change_summary && (
            <p className="text-xs text-slate-500 mt-1">{active.change_summary}</p>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          placeholder="Optional note about this change"
          value={changeSummary}
          onChange={(e) => setChangeSummary(e.target.value)}
          className="flex-1 min-w-[16rem] rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
        />
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.md,.txt"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) {
              setConfirmation(null);
              uploadMutation.mutate(file);
            }
            e.target.value = "";
          }}
        />
        <button
          className="text-sm rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 disabled:opacity-50"
          disabled={uploadMutation.isPending}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploadMutation.isPending ? "Reading and activating…" : "Upload new prompt"}
        </button>
      </div>

      {uploadMutation.isError && (
        <p className="text-xs text-risk-critical">{(uploadMutation.error as Error).message}</p>
      )}
      {confirmation && (
        <p className="text-xs text-green-700 dark:text-green-400">
          Read and activated as version {confirmation.version_label} —{" "}
          {confirmation.word_count.toLocaleString()} words extracted successfully.
        </p>
      )}

      {versions && versions.length > 1 && (
        <details>
          <summary className="text-xs text-slate-500 cursor-pointer">
            {versions.length} version{versions.length === 1 ? "" : "s"} total — view history
          </summary>
          <ul className="mt-2 space-y-1.5">
            {versions.map((v) => (
              <li key={v.id} className="flex items-center justify-between text-sm">
                <span>
                  Version {v.version_label}
                  {v.is_active && <span className="ml-2 text-xs text-green-700 dark:text-green-400">(active)</span>}
                  {v.change_summary && (
                    <span className="ml-2 text-xs text-slate-500">— {v.change_summary}</span>
                  )}
                </span>
                {!v.is_active && (
                  <button
                    className="text-xs text-slate-600 dark:text-slate-300 underline shrink-0"
                    disabled={activateMutation.isPending}
                    onClick={() => activateMutation.mutate(v.id)}
                  >
                    Activate
                  </button>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      {activateMutation.isError && (
        <p className="text-xs text-risk-critical">{(activateMutation.error as Error).message}</p>
      )}
    </section>
  );
}
