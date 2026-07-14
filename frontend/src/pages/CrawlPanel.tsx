import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import type { CrawlCreateRequest, CrawlDiffResponse, CrawlSnapshot, CrawledPage } from "../types/crawl";
import type { Job } from "../types/document";
import type { ScheduledRecrawl, ScheduledRecrawlCreate } from "../types/monitoring";

function ScheduledRecrawlsPanel({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<ScheduledRecrawlCreate>({ start_url: "", interval_hours: 24 });

  const { data: schedules } = useQuery({
    queryKey: ["scheduled-recrawls", projectId],
    queryFn: () => api.get<ScheduledRecrawl[]>(`/projects/${projectId}/scheduled-recrawls`),
  });

  const createMutation = useMutation({
    mutationFn: (payload: ScheduledRecrawlCreate) =>
      api.post<ScheduledRecrawl>(`/projects/${projectId}/scheduled-recrawls`, payload),
    onSuccess: () => {
      setShowForm(false);
      setForm({ start_url: "", interval_hours: 24 });
      queryClient.invalidateQueries({ queryKey: ["scheduled-recrawls", projectId] });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (vars: { id: string; is_active: boolean }) =>
      api.put(`/scheduled-recrawls/${vars.id}`, { is_active: vars.is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scheduled-recrawls", projectId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.del(`/scheduled-recrawls/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scheduled-recrawls", projectId] }),
  });

  return (
    <div className="space-y-3 rounded border border-slate-200 dark:border-slate-800 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Scheduled recrawls</p>
          <p className="text-xs text-slate-500 max-w-lg">
            Automatically recrawl on a recurring interval. After a scheduled recrawl, changed pages
            are checked for material compliance-relevant changes (new claims, removed disclaimers,
            changed FDA language) and surfaced on the Monitoring page — manual one-off crawls above
            don't do this.
          </p>
        </div>
        <button
          className="text-xs rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 whitespace-nowrap"
          onClick={() => setShowForm((v) => !v)}
        >
          {showForm ? "Cancel" : "Add schedule"}
        </button>
      </div>

      {showForm && (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (form.start_url.trim()) createMutation.mutate(form);
          }}
        >
          <input
            required
            placeholder="https://example.com"
            value={form.start_url}
            onChange={(e) => setForm({ ...form, start_url: e.target.value })}
            className="flex-1 min-w-[12rem] rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
          />
          <label className="flex items-center gap-1 text-sm">
            Every
            <select
              value={form.interval_hours}
              onChange={(e) => setForm({ ...form, interval_hours: Number(e.target.value) })}
              className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
            >
              <option value={24}>day</option>
              <option value={168}>week</option>
              <option value={720}>month</option>
            </select>
          </label>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 text-sm disabled:opacity-50"
          >
            Save
          </button>
        </form>
      )}
      {createMutation.isError && (
        <p className="text-xs text-risk-critical">{(createMutation.error as Error).message}</p>
      )}

      {schedules && schedules.length === 0 && (
        <p className="text-xs text-slate-500">No scheduled recrawls for this project.</p>
      )}
      {schedules && schedules.length > 0 && (
        <ul className="space-y-1.5">
          {schedules.map((s) => (
            <li key={s.id} className="flex items-center justify-between text-sm">
              <span>
                {s.start_url}{" "}
                <span className="text-xs text-slate-500">
                  every {s.interval_hours}h · next {new Date(s.next_run_at).toLocaleString()}
                  {!s.is_active && " · paused"}
                </span>
              </span>
              <span className="flex items-center gap-2 shrink-0">
                <button
                  className="text-xs text-slate-600 dark:text-slate-300 underline"
                  onClick={() => toggleMutation.mutate({ id: s.id, is_active: !s.is_active })}
                >
                  {s.is_active ? "Pause" : "Resume"}
                </button>
                <button
                  className="text-xs text-risk-critical underline"
                  onClick={() => deleteMutation.mutate(s.id)}
                >
                  Delete
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

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
      return 2000;
    },
  });
}

export function CrawlPanel({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(null);
  const [form, setForm] = useState<CrawlCreateRequest>({
    start_url: "",
    follow_subdomains: false,
    include_pdfs: false,
  });

  const { data: snapshots, refetch: refetchSnapshots } = useQuery({
    queryKey: ["crawls", projectId],
    queryFn: () => api.get<CrawlSnapshot[]>(`/projects/${projectId}/crawls`),
    refetchInterval: activeJobId ? 2000 : false,
  });

  useActiveJobPoll(activeJobId, () => {
    setActiveJobId(null);
    refetchSnapshots();
  });

  const startCrawl = useMutation({
    mutationFn: (payload: CrawlCreateRequest) => api.post<Job>(`/projects/${projectId}/crawls`, payload),
    onSuccess: (job) => {
      setActiveJobId(job.id);
      setShowForm(false);
      queryClient.invalidateQueries({ queryKey: ["crawls", projectId] });
    },
  });

  const cancelCrawl = useMutation({
    mutationFn: (snapshotId: string) => api.post(`/crawls/${snapshotId}/cancel`),
    onSuccess: () => refetchSnapshots(),
  });

  const { data: pages } = useQuery({
    queryKey: ["crawl-pages", selectedSnapshotId],
    queryFn: () => api.get<CrawledPage[]>(`/crawls/${selectedSnapshotId}/pages`),
    enabled: !!selectedSnapshotId,
  });

  const { data: diff } = useQuery({
    queryKey: ["crawl-diff", selectedSnapshotId],
    queryFn: () => api.get<CrawlDiffResponse>(`/crawls/${selectedSnapshotId}/diff`),
    enabled: !!selectedSnapshotId,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-500 max-w-xl">
          SSRF-guarded, robots.txt-respecting crawl of the company website. Crawled pages are
          parsed and embedded into this project's evidence library the same way an uploaded
          document is (see the Search panel above).
        </p>
        <button
          className="text-sm rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 whitespace-nowrap disabled:opacity-50"
          disabled={!!activeJobId}
          onClick={() => setShowForm((v) => !v)}
        >
          {activeJobId ? "Crawling…" : showForm ? "Cancel" : "New crawl"}
        </button>
      </div>

      {showForm && (
        <form
          className="space-y-2 rounded border border-slate-200 dark:border-slate-800 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (form.start_url.trim()) startCrawl.mutate(form);
          }}
        >
          <input
            required
            placeholder="https://example.com"
            value={form.start_url}
            onChange={(e) => setForm({ ...form, start_url: e.target.value })}
            className="w-full rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
          />
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-1">
              Max pages
              <input
                type="number"
                min={1}
                placeholder="250"
                value={form.max_pages ?? ""}
                onChange={(e) =>
                  setForm({ ...form, max_pages: e.target.value ? Number(e.target.value) : undefined })
                }
                className="w-20 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-0.5"
              />
            </label>
            <label className="flex items-center gap-1">
              Max depth
              <input
                type="number"
                min={0}
                placeholder="4"
                value={form.max_depth ?? ""}
                onChange={(e) =>
                  setForm({ ...form, max_depth: e.target.value ? Number(e.target.value) : undefined })
                }
                className="w-16 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-0.5"
              />
            </label>
            <label className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={form.follow_subdomains}
                onChange={(e) => setForm({ ...form, follow_subdomains: e.target.checked })}
              />
              Follow subdomains
            </label>
            <label className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={form.include_pdfs}
                onChange={(e) => setForm({ ...form, include_pdfs: e.target.checked })}
              />
              Include PDFs
            </label>
          </div>
          <button
            type="submit"
            disabled={startCrawl.isPending}
            className="rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 text-sm disabled:opacity-50"
          >
            Start crawl
          </button>
          {startCrawl.isError && (
            <p className="text-xs text-risk-critical">{(startCrawl.error as Error).message}</p>
          )}
        </form>
      )}

      {snapshots && snapshots.length === 0 && (
        <p className="text-sm text-slate-500">No crawls yet.</p>
      )}
      {snapshots && snapshots.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-800">
              <th className="py-2 pr-4">Root URL</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Pages</th>
              <th className="py-2 pr-4">Started</th>
              <th className="py-2 pr-4"></th>
            </tr>
          </thead>
          <tbody>
            {snapshots.map((s) => (
              <tr key={s.id} className="border-b border-slate-100 dark:border-slate-900">
                <td className="py-2 pr-4 font-medium">{s.root_url}</td>
                <td className="py-2 pr-4">
                  <StatusBadge status={s.status} />
                </td>
                <td className="py-2 pr-4">{s.page_count}</td>
                <td className="py-2 pr-4 text-slate-500">
                  {s.started_at ? new Date(s.started_at).toLocaleString() : "—"}
                </td>
                <td className="py-2 pr-4 space-x-2">
                  <button
                    className="text-slate-600 dark:text-slate-300 hover:underline"
                    onClick={() => setSelectedSnapshotId(s.id === selectedSnapshotId ? null : s.id)}
                  >
                    {selectedSnapshotId === s.id ? "Hide" : "View"}
                  </button>
                  {(s.status === "QUEUED" || s.status === "RUNNING") && (
                    <button
                      className="text-risk-critical hover:underline"
                      onClick={() => cancelCrawl.mutate(s.id)}
                    >
                      Cancel
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedSnapshotId && diff && diff.previous_snapshot_id && (
        <div className="rounded border border-slate-200 dark:border-slate-800 p-3 text-sm">
          <p className="font-medium mb-1">Changes since previous snapshot</p>
          <p className="text-slate-500">
            {diff.summary.added ?? 0} added · {diff.summary.changed ?? 0} changed ·{" "}
            {diff.summary.removed ?? 0} removed · {diff.summary.unchanged ?? 0} unchanged
          </p>
        </div>
      )}

      {selectedSnapshotId && pages && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-800">
              <th className="py-2 pr-4">URL</th>
              <th className="py-2 pr-4">Title</th>
              <th className="py-2 pr-4">HTTP</th>
              <th className="py-2 pr-4">Robots</th>
              <th className="py-2 pr-4">Changed</th>
            </tr>
          </thead>
          <tbody>
            {pages.map((p) => (
              <tr key={p.id} className="border-b border-slate-100 dark:border-slate-900">
                <td className="py-2 pr-4 truncate max-w-xs" title={p.url}>
                  {p.url}
                </td>
                <td className="py-2 pr-4">{p.title ?? "—"}</td>
                <td className="py-2 pr-4 text-slate-500">{p.http_status ?? "—"}</td>
                <td className="py-2 pr-4">
                  <StatusBadge status={p.robots_status} />
                </td>
                <td className="py-2 pr-4">
                  {p.changed_from_prior === null ? "—" : p.changed_from_prior ? "Yes" : "No"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <ScheduledRecrawlsPanel projectId={projectId} />
    </div>
  );
}
