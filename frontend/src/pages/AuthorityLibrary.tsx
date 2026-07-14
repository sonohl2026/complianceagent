import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api, parseErrorDetail } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import type { Job, SourceDocument } from "../types/document";

const AUTHORITY_LEVELS = [
  "1_CONTROLLED_COMPANY_OR_BINDING_AUTHORITY",
  "2_VERIFIED_INTERNAL_EVIDENCE",
  "3_OFFICIAL_EXTERNAL_AUTHORITY",
  "4_WORKING_DRAFT",
  "5_SECONDARY_OR_ANALOG",
];

function useActiveJobPoll(jobId: string | null, onDone: () => void) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.get<Job>(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "COMPLETE" || status === "FAILED" || status === "CANCELLED") {
        onDone();
        return false;
      }
      return 1500;
    },
  });
}

export function AuthorityLibrary() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [authorityLevel, setAuthorityLevel] = useState(AUTHORITY_LEVELS[2]);
  const [sourceUrl, setSourceUrl] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingUrl, setEditingUrl] = useState("");

  const { data: documents, refetch } = useQuery({
    queryKey: ["authority-documents"],
    queryFn: () => api.get<SourceDocument[]>("/authority/documents"),
  });

  useActiveJobPoll(activeJobId, () => {
    setActiveJobId(null);
    refetch();
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("authority_level", authorityLevel);
      if (sourceUrl.trim()) formData.append("url", sourceUrl.trim());
      const response = await fetch(
        `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"}/authority/documents`,
        { method: "POST", body: formData },
      );
      if (!response.ok) throw new Error(parseErrorDetail(await response.text(), response.statusText));
      return (await response.json()) as Job;
    },
    onSuccess: (job) => {
      setActiveJobId(job.id);
      setSourceUrl("");
      queryClient.invalidateQueries({ queryKey: ["authority-documents"] });
    },
  });

  const updateUrlMutation = useMutation({
    mutationFn: (vars: { id: string; url: string }) =>
      api.put<SourceDocument>(`/documents/${vars.id}`, { url: vars.url || null }),
    onSuccess: () => {
      setEditingId(null);
      queryClient.invalidateQueries({ queryKey: ["authority-documents"] });
    },
  });

  return (
    <div className="space-y-4 max-w-4xl">
      <p className="text-sm text-slate-500">
        Official/binding sources (FDA guidance, CMS manuals, licensed CPT/HCPCS materials, payer
        policies, statutes and regulations) shared across every project. Never scrape or
        redistribute copyrighted CPT content beyond what your license permits — upload only
        properly licensed or official materials here.
      </p>

      <div className="flex flex-wrap items-center gap-2 rounded border border-slate-200 dark:border-slate-800 p-4">
        <label className="text-sm">Authority level</label>
        <select
          value={authorityLevel}
          onChange={(e) => setAuthorityLevel(e.target.value)}
          className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
        >
          {AUTHORITY_LEVELS.map((level) => (
            <option key={level} value={level}>
              {level}
            </option>
          ))}
        </select>
        <input
          type="url"
          placeholder="Source URL (optional, e.g. https://www.cms.gov/...)"
          value={sourceUrl}
          onChange={(e) => setSourceUrl(e.target.value)}
          className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm w-72"
        />
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.pptx,.xlsx,.csv,.html,.htm,.md,.txt"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadMutation.mutate(file);
            e.target.value = "";
          }}
        />
        <button
          className="text-sm rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 disabled:opacity-50"
          disabled={uploadMutation.isPending || !!activeJobId}
          onClick={() => fileInputRef.current?.click()}
        >
          {activeJobId ? "Processing…" : "Upload authority document"}
        </button>
      </div>
      {uploadMutation.isError && (
        <p className="text-xs text-risk-critical">{(uploadMutation.error as Error).message}</p>
      )}

      {documents && documents.length === 0 && (
        <p className="text-sm text-slate-500">No authority documents yet.</p>
      )}
      {documents && documents.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-800">
              <th className="py-2 pr-4">Title</th>
              <th className="py-2 pr-4">Authority level</th>
              <th className="py-2 pr-4">Source URL</th>
              <th className="py-2 pr-4">Parse status</th>
              <th className="py-2 pr-4">Embedding</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((d) => (
              <tr key={d.id} className="border-b border-slate-100 dark:border-slate-900">
                <td className="py-2 pr-4 font-medium">
                  {d.title}
                  {d.parse_error && (
                    <p className="text-xs text-risk-critical font-normal">{d.parse_error}</p>
                  )}
                </td>
                <td className="py-2 pr-4 text-slate-500">{d.authority_level ?? "—"}</td>
                <td className="py-2 pr-4 max-w-xs">
                  {editingId === d.id ? (
                    <div className="flex items-center gap-1">
                      <input
                        type="url"
                        autoFocus
                        value={editingUrl}
                        onChange={(e) => setEditingUrl(e.target.value)}
                        placeholder="https://..."
                        className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-1.5 py-0.5 text-xs w-48"
                      />
                      <button
                        className="text-xs text-slate-900 dark:text-slate-100 underline"
                        disabled={updateUrlMutation.isPending}
                        onClick={() => updateUrlMutation.mutate({ id: d.id, url: editingUrl.trim() })}
                      >
                        Save
                      </button>
                      <button className="text-xs text-slate-500" onClick={() => setEditingId(null)}>
                        Cancel
                      </button>
                    </div>
                  ) : d.url ? (
                    <div className="flex items-center gap-2">
                      <a
                        href={d.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs underline truncate max-w-[12rem] inline-block align-middle"
                        title={d.url}
                      >
                        {d.url}
                      </a>
                      <button
                        className="text-xs text-slate-500 shrink-0"
                        onClick={() => {
                          setEditingId(d.id);
                          setEditingUrl(d.url ?? "");
                        }}
                      >
                        Edit
                      </button>
                    </div>
                  ) : (
                    <button
                      className="text-xs text-slate-500 underline decoration-dotted"
                      onClick={() => {
                        setEditingId(d.id);
                        setEditingUrl("");
                      }}
                    >
                      Add source URL
                    </button>
                  )}
                  {updateUrlMutation.isError && updateUrlMutation.variables?.id === d.id && (
                    <p className="text-xs text-risk-critical">{(updateUrlMutation.error as Error).message}</p>
                  )}
                </td>
                <td className="py-2 pr-4">
                  <StatusBadge status={d.parse_status} />
                </td>
                <td className="py-2 pr-4">
                  <StatusBadge status={d.embedding_status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
