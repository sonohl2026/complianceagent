import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { parseErrorDetail } from "../../api/client";
import type { Job } from "../../types/document";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

// Same set app/services/parsing/dispatch.py's SUPPORTED_EXTENSIONS knows how
// to turn into text -- kept in sync by hand since the accept list is tiny
// and rarely changes; there's no cheap way to fetch it from the API without
// an extra round-trip just to populate a file picker's accept attribute.
const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".html", ".htm", ".md", ".txt"];

/** MVP lockdown Step 2: the single entry point. A user can freely mix any
 * number of file uploads, web links, and/or a typed product name, then hit
 * one button. Behavior branches server-side on what's actually present --
 * this component just gathers whatever the user gave it.
 *
 * Passing productId re-runs against that existing product (a fresh
 * AnalysisRun under it) instead of creating a new one -- the "Run a new
 * scan" affordance on a product's own results page uses this. */
export function Composer({
  onStarted,
  productId,
  defaultName = "",
}: {
  onStarted: (job: Job) => void;
  productId?: string;
  defaultName?: string;
}) {
  const [name, setName] = useState(defaultName);
  const [urls, setUrls] = useState<string[]>([""]);
  const [files, setFiles] = useState<File[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addFiles = (incoming: FileList | File[]) => {
    const accepted = Array.from(incoming).filter((f) => {
      const extension = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
      return ACCEPTED_EXTENSIONS.includes(extension);
    });
    setFiles((existing) => [...existing, ...accepted]);
  };

  const removeFile = (index: number) => setFiles((existing) => existing.filter((_, i) => i !== index));
  const updateUrl = (index: number, value: string) =>
    setUrls((existing) => existing.map((u, i) => (i === index ? value : u)));
  const removeUrl = (index: number) => setUrls((existing) => existing.filter((_, i) => i !== index));

  const submit = useMutation({
    mutationFn: async () => {
      const formData = new FormData();
      formData.append("product_name", name.trim());
      for (const file of files) formData.append("files", file);
      for (const url of urls) {
        if (url.trim()) formData.append("source_urls", url.trim());
      }
      if (productId) formData.append("product_id", productId);
      const response = await fetch(`${API_BASE_URL}/quick-scans`, { method: "POST", body: formData });
      if (!response.ok) throw new Error(parseErrorDetail(await response.text(), response.statusText));
      return (await response.json()) as Job;
    },
    onSuccess: (job) => {
      setName(defaultName);
      setUrls([""]);
      setFiles([]);
      onStarted(job);
    },
  });

  const canSubmit = name.trim().length > 0 || files.length > 0 || urls.some((u) => u.trim().length > 0);

  return (
    <div className="rounded border border-slate-200 dark:border-slate-800 p-5 space-y-4">
      <div>
        <h3 className="text-sm font-semibold">{productId ? "Run a new scan" : "Analyze a device"}</h3>
        <p className="text-xs text-slate-500 mt-1">
          {productId
            ? "Attach fresh material or just re-check the name -- this adds a new scan to this product, it won't create a duplicate."
            : "Type a product name, attach documents, add links -- any mix works. If you just type a name, we'll look it up and check with you before running the full assessment."}
        </p>
      </div>

      <label className="block text-xs space-y-1">
        <span className="text-slate-500">Product name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Dexcom G7, or the device you're working on"
          className="w-full rounded border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-sm"
        />
      </label>

      <div className="space-y-1.5">
        <span className="text-xs text-slate-500">Links</span>
        {urls.map((url, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              value={url}
              onChange={(e) => updateUrl(i, e.target.value)}
              placeholder="https://…"
              className="flex-1 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-1.5 text-sm"
            />
            {urls.length > 1 && (
              <button
                onClick={() => removeUrl(i)}
                className="text-xs text-slate-400 hover:text-risk-critical shrink-0"
                title="Remove link"
              >
                ✕
              </button>
            )}
          </div>
        ))}
        <button
          onClick={() => setUrls((existing) => [...existing, ""])}
          className="text-xs text-slate-500 underline decoration-dotted"
        >
          + Add another link
        </button>
      </div>

      <div className="space-y-1.5">
        <span className="text-xs text-slate-500">Documents</span>
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
            if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
          }}
          className={`flex flex-col items-center justify-center gap-1 rounded border-2 border-dashed px-4 py-6 text-center cursor-pointer transition-colors ${
            isDragOver
              ? "border-teal-600 bg-teal-700/5"
              : "border-slate-300 dark:border-slate-700 hover:border-slate-400 dark:hover:border-slate-600"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED_EXTENSIONS.join(",")}
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.length) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Drop one or more files here, or click to browse
          </p>
          <p className="text-xs text-slate-400">{ACCEPTED_EXTENSIONS.join(", ")}</p>
        </div>
        {files.length > 0 && (
          <ul className="space-y-1">
            {files.map((f, i) => (
              <li key={i} className="flex items-center justify-between text-xs rounded bg-slate-100 dark:bg-slate-900 px-2 py-1">
                <span className="truncate">{f.name}</span>
                <button onClick={() => removeFile(i)} className="text-slate-400 hover:text-risk-critical shrink-0 ml-2">
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button
          disabled={!canSubmit || submit.isPending}
          onClick={() => submit.mutate()}
          className="text-sm rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-4 py-2 disabled:opacity-50"
        >
          {submit.isPending ? "Starting…" : "Run"}
        </button>
        {submit.isError && <span className="text-xs text-risk-critical">{(submit.error as Error).message}</span>}
      </div>
    </div>
  );
}
