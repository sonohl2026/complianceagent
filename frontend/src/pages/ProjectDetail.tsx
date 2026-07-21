import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { ComplianceChecklist } from "../components/ComplianceChecklist";
import { QuickScanLaunchPanel } from "../components/quickScan/QuickScanLaunchPanel";
import { StatusBadge } from "../components/StatusBadge";
import { CrawlPanel } from "./CrawlPanel";
import type { CollectionType, Job, SourceDocument } from "../types/document";
import type { Product, ProductCreate, Project } from "../types/project";
import type { SearchResultChunk } from "../types/retrieval";

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

export function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.get<Project>(`/projects/${projectId}`),
  });

  const { data: products, refetch: refetchProducts } = useQuery({
    queryKey: ["products", projectId],
    queryFn: () => api.get<Product[]>(`/projects/${projectId}/products`),
    enabled: !!projectId,
  });

  const { data: documents, refetch: refetchDocuments } = useQuery({
    queryKey: ["documents", projectId],
    queryFn: () => api.get<SourceDocument[]>(`/projects/${projectId}/documents`),
    enabled: !!projectId,
  });

  useActiveJobPoll(activeJobId, () => {
    setActiveJobId(null);
    refetchDocuments();
  });

  const [productForm, setProductForm] = useState<ProductCreate>({ name: "" });
  const [showProductForm, setShowProductForm] = useState(false);
  const createProduct = useMutation({
    mutationFn: (payload: ProductCreate) =>
      api.post<Product>(`/projects/${projectId}/products`, payload),
    onSuccess: () => {
      refetchProducts();
      setProductForm({ name: "" });
      setShowProductForm(false);
    },
  });

  const [uploadCollectionType, setUploadCollectionType] = useState<CollectionType>("COMPANY");
  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("collection_type", uploadCollectionType);
      const response = await fetch(
        `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"}/projects/${projectId}/documents`,
        { method: "POST", body: formData },
      );
      if (!response.ok) throw new Error(await response.text());
      return (await response.json()) as Job;
    },
    onSuccess: (job) => {
      setActiveJobId(job.id);
      queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
    },
  });

  const deleteProject = useMutation({
    mutationFn: () => api.del(`/projects/${projectId}`),
    onSuccess: () => navigate("/new-analysis"),
  });

  if (!project) {
    return <p className="text-sm text-slate-500">Loading project…</p>;
  }

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <div className="flex items-center justify-between">
          <Link to="/new-analysis" className="text-xs text-slate-500 hover:underline">
            ← All projects
          </Link>
          {confirmDelete ? (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-500">Delete this project and all its data?</span>
              <button
                className="text-risk-critical underline disabled:opacity-50"
                disabled={deleteProject.isPending}
                onClick={() => deleteProject.mutate()}
              >
                Confirm
              </button>
              <button className="text-slate-500 underline" onClick={() => setConfirmDelete(false)}>
                Cancel
              </button>
            </div>
          ) : (
            <button
              className="text-xs text-slate-400 hover:text-risk-critical"
              onClick={() => setConfirmDelete(true)}
            >
              Delete project
            </button>
          )}
        </div>
        <h2 className="text-lg font-semibold">{project.name}</h2>
        <p className="text-sm text-slate-500">{project.jurisdiction}</p>
        {deleteProject.isError && (
          <p className="text-xs text-risk-critical mt-1">
            {(deleteProject.error as Error).message}
          </p>
        )}
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Products
          </h3>
          <button
            className="text-sm rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1"
            onClick={() => setShowProductForm((v) => !v)}
          >
            {showProductForm ? "Cancel" : "Add product"}
          </button>
        </div>
        {showProductForm && (
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (productForm.name.trim()) createProduct.mutate(productForm);
            }}
          >
            <input
              required
              placeholder="Product name"
              value={productForm.name}
              onChange={(e) => setProductForm({ ...productForm, name: e.target.value })}
              className="flex-1 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
            />
            <button
              type="submit"
              className="rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 text-sm"
            >
              Create
            </button>
          </form>
        )}
        {products && products.length === 0 && (
          <p className="text-sm text-slate-500">No products yet.</p>
        )}
        {products && products.length > 0 && (
          <ul className="text-sm space-y-3">
            {products.map((p) => (
              <li key={p.id} className="rounded border border-slate-200 dark:border-slate-800 px-3 py-2 space-y-2">
                <div>
                  <span className="font-medium">{p.name}</span>
                  {p.regulatory_stage && (
                    <span className="ml-2 text-slate-500">({p.regulatory_stage})</span>
                  )}
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">
                    Compliance checklist
                  </p>
                  <ComplianceChecklist productId={p.id} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Website</h3>
        <CrawlPanel projectId={projectId!} />
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Documents
          </h3>
          <div className="flex items-center gap-2">
            <select
              value={uploadCollectionType}
              onChange={(e) => setUploadCollectionType(e.target.value as CollectionType)}
              title="What kind of source is this document?"
              className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
            >
              <option value="COMPANY">Company evidence (official/first-party)</option>
              <option value="THIRD_PARTY">Third-party literature (e.g. academic article, news)</option>
              <option value="COMPETITOR">Competitor material</option>
            </select>
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
              {activeJobId ? "Processing…" : "Upload document"}
            </button>
          </div>
        </div>
        <p className="text-xs text-slate-500">
          Mark evidence that isn't your own company's official material as "Third-party" or
          "Competitor" — this tells the analysis to treat it as secondary/analog evidence rather
          than authoritative company evidence, so a missing fact in that source is treated as a
          gap in this analysis, not a compliance finding against the company.
        </p>
        {uploadMutation.isError && (
          <p className="text-xs text-risk-critical">{(uploadMutation.error as Error).message}</p>
        )}
        {documents && documents.length === 0 && (
          <p className="text-sm text-slate-500">
            No documents yet. Supported: PDF, DOCX, PPTX, XLSX, CSV, HTML, Markdown, TXT.
          </p>
        )}
        {documents && documents.length > 0 && (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-800">
                <th className="py-2 pr-4">Title</th>
                <th className="py-2 pr-4">Collection</th>
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
                  <td className="py-2 pr-4 text-slate-500">{d.collection_type}</td>
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
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Search (retrieval preview)
        </h3>
        <p className="text-xs text-slate-500">
          Hybrid vector + full-text search over this project's chunks plus the shared authority
          library. This is a raw preview of the retrieval layer, useful for spot-checking what
          the compliance analysis below will actually retrieve. Documents must finish embedding
          (see status above) before they're searchable.
        </p>
        <SearchPanel projectId={projectId!} />
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Quick Scan</h3>
        <QuickScanLaunchPanel projectId={projectId!} />
      </section>
    </div>
  );
}

function SearchPanel({ projectId }: { projectId: string }) {
  const [query, setQuery] = useState("");
  const searchMutation = useMutation({
    mutationFn: (q: string) =>
      api.post<SearchResultChunk[]>(`/projects/${projectId}/search`, { query: q, top_k: 5 }),
  });

  return (
    <div className="space-y-3">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (query.trim()) searchMutation.mutate(query);
        }}
      >
        <input
          placeholder="e.g. Has the device received FDA clearance?"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
        />
        <button
          type="submit"
          disabled={searchMutation.isPending}
          className="rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 text-sm disabled:opacity-50"
        >
          Search
        </button>
      </form>
      {searchMutation.isError && (
        <p className="text-xs text-risk-critical">{(searchMutation.error as Error).message}</p>
      )}
      {searchMutation.data && searchMutation.data.length === 0 && (
        <p className="text-sm text-slate-500">No matching chunks found.</p>
      )}
      {searchMutation.data && searchMutation.data.length > 0 && (
        <ul className="space-y-2">
          {searchMutation.data.map((r) => (
            <li key={r.chunk_id} className="rounded border border-slate-200 dark:border-slate-800 p-3 text-sm">
              <div className="flex justify-between text-xs text-slate-500 mb-1">
                <span>{r.citation_label}</span>
                <span>
                  {r.collection_type}
                  {r.authority_level ? ` · ${r.authority_level}` : ""} · score {r.score.toFixed(3)}
                </span>
              </div>
              <p>{r.text}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
