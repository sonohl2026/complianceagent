import { useMutation, useQuery, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { AppSettings, AppSettingsUpdate } from "../types/settings";

export function Settings() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<AppSettings>("/settings"),
  });
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [braveKeyInput, setBraveKeyInput] = useState("");
  const [modelInput, setModelInput] = useState("");

  const mutation = useMutation({
    mutationFn: (update: AppSettingsUpdate) => api.put<AppSettings>("/settings", update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setApiKeyInput("");
      setBraveKeyInput("");
    },
  });

  if (isLoading || !data) {
    return <p className="text-sm text-slate-500">Loading settings…</p>;
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h2 className="text-lg font-semibold">Settings</h2>

      {mutation.isError && (
        <div className="rounded border border-risk-critical/40 bg-risk-critical/5 p-3 text-sm text-risk-critical">
          Save failed: {(mutation.error as Error).message}. Nothing below was changed -- try again.
        </div>
      )}

      <div className="rounded border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950 p-4 text-sm">
        {data.local_data_notice}
      </div>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          OpenRouter
        </h3>
        <div className="flex items-center gap-2 text-sm">
          <span>API key:</span>
          <code className="rounded bg-slate-100 dark:bg-slate-900 px-2 py-0.5">
            {data.openrouter_api_key_configured ? data.openrouter_api_key_masked : "not set"}
          </code>
        </div>
        <div className="flex gap-2">
          <input
            type="password"
            placeholder="sk-or-..."
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            className="flex-1 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
          />
          <button
            className="rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 text-sm disabled:opacity-50"
            disabled={!apiKeyInput || mutation.isPending}
            onClick={() => mutation.mutate({ openrouter_api_key: apiKeyInput })}
          >
            Save key
          </button>
        </div>
        <p className="text-xs text-slate-500">
          The key is stored only on this machine and is never sent to the browser after saving —
          only a masked preview is returned.
        </p>

        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Default analysis model slug, e.g. anthropic/claude-sonnet-5"
            value={modelInput}
            onChange={(e) => setModelInput(e.target.value)}
            className="flex-1 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
          />
          <button
            className="rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 text-sm disabled:opacity-50"
            disabled={!modelInput || mutation.isPending}
            onClick={() => mutation.mutate({ openrouter_model: modelInput })}
          >
            Save model
          </button>
        </div>
        <p className="text-xs text-slate-500">
          Current default model: <code>{data.openrouter_model || "not set"}</code>. Use an exact
          model slug, not a "latest" alias, for reproducible regulated analysis.
        </p>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Web search (name-only fallback)
        </h3>
        <p className="text-xs text-slate-500">
          Only used when a name-only submission's FDA/CMS lookup finds nothing: proposes a
          candidate site for you to confirm before it's fetched and analyzed. Never used when a
          document or link is already attached.
        </p>
        <div className="flex items-center gap-2 text-sm">
          <span>Brave Search API key:</span>
          <code className="rounded bg-slate-100 dark:bg-slate-900 px-2 py-0.5">
            {data.brave_search_api_key_configured ? data.brave_search_api_key_masked : "not set"}
          </code>
        </div>
        <div className="flex gap-2">
          <input
            type="password"
            placeholder="BSA..."
            value={braveKeyInput}
            onChange={(e) => setBraveKeyInput(e.target.value)}
            className="flex-1 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
          />
          <button
            className="rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 text-sm disabled:opacity-50"
            disabled={!braveKeyInput || mutation.isPending}
            onClick={() => mutation.mutate({ brave_search_api_key: braveKeyInput })}
          >
            Save key
          </button>
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Per-stage models (cost control)
        </h3>
        <p className="text-xs text-slate-500">
          An analysis runs 7 model calls. Input audit, fact/claim extraction, coding, and citation
          audit are comparatively mechanical — a cheap/fast model handles them fine. Domain
          analysis and synthesis are where the actual compliance reasoning happens, so they stay
          on the default model above unless you set a synthesis-tier override here. Leave any
          field blank to fall back to the default model.
        </p>
        <button
          className="text-sm rounded border border-slate-300 dark:border-slate-700 px-3 py-1"
          onClick={() =>
            mutation.mutate({
              openrouter_model: "anthropic/claude-haiku-4.5",
              openrouter_extraction_model: "",
              openrouter_synthesis_model: "",
              openrouter_citation_model: "",
            })
          }
        >
          Use cheap testing defaults (Claude Haiku 4.5 for everything)
        </button>
        {(
          [
            ["openrouter_extraction_model", "Extraction tier (input audit, facts, claims, coding)"],
            ["openrouter_synthesis_model", "Synthesis tier (domain analysis, synthesis)"],
            ["openrouter_citation_model", "Citation-audit tier"],
          ] as [keyof AppSettingsUpdate & keyof AppSettings, string][]
        ).map(([key, label]) => (
          <PerStageModelInput
            key={`${key}:${data[key]}`}
            settingKey={key}
            label={label}
            currentValue={String(data[key] ?? "")}
            mutation={mutation}
          />
        ))}
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Privacy controls
        </h3>
        {(
          [
            ["openrouter_zdr", "Enforce Zero Data Retention"],
            ["redact_emails", "Redact email addresses before sending to OpenRouter"],
            ["redact_phone_numbers", "Redact phone numbers before sending to OpenRouter"],
            ["redact_patient_identifiers", "Redact likely patient identifiers"],
            ["exclude_restricted_documents", "Exclude RESTRICTED documents from model context"],
            ["allow_ocr", "Allow local OCR for documents with no text layer"],
            ["allow_lan_access", "Allow LAN access (binds beyond 127.0.0.1)"],
          ] as [keyof AppSettings, string][]
        ).map(([key, label]) => (
          <label key={key} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={Boolean(data[key])}
              onChange={(e) => mutation.mutate({ [key]: e.target.checked })}
            />
            {label}
          </label>
        ))}
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Cost controls
        </h3>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={Boolean(data.openrouter_prompt_caching)}
            onChange={(e) => mutation.mutate({ openrouter_prompt_caching: e.target.checked })}
          />
          Cache the repeated master-prompt block across stages (reduces cost; disable if you
          notice issues)
        </label>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Quick Scan / Licensed Data
        </h3>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={Boolean(data.cms_license_accepted)}
            onChange={(e) => mutation.mutate({ cms_license_accepted: e.target.checked })}
          />
          <span>
            Allow quick scan to fetch full LCD/Article text from CMS&apos;s licensed Coverage API
            endpoints.
            <span className="block text-xs text-slate-500 mt-1">
              Enabling this allows the app to call CMS&apos;s License Agreement endpoint and accept
              the AMA CPT, ADA CDT, and AHA UB-04 license agreements on your behalf when a scan
              needs full coverage-document text. Turning this toggle on <strong>is</strong> your
              acceptance of those license terms. Leave it off and quick scan still works — it just
              relies on CMS&apos;s open, unlicensed coverage listings instead of full document text.
            </span>
          </span>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={Boolean(data.cpt_license)}
            onChange={(e) => mutation.mutate({ cpt_license: e.target.checked })}
          />
          Show full CPT code descriptors (requires your own AMA CPT license — off by default,
          shows code number + short paraphrase + official-lookup link only)
        </label>
      </section>
    </div>
  );
}

function PerStageModelInput({
  settingKey,
  label,
  currentValue,
  mutation,
}: {
  settingKey: keyof AppSettingsUpdate;
  label: string;
  currentValue: string;
  mutation: UseMutationResult<AppSettings, Error, AppSettingsUpdate>;
}) {
  const [value, setValue] = useState(currentValue);

  return (
    <div className="flex gap-2 items-center">
      <label className="text-xs text-slate-500 w-72 shrink-0">{label}</label>
      <input
        type="text"
        placeholder="blank = use default model"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="flex-1 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
      />
      <button
        className="rounded border border-slate-300 dark:border-slate-700 px-3 py-1 text-sm disabled:opacity-50"
        disabled={mutation.isPending || value === currentValue}
        onClick={() => mutation.mutate({ [settingKey]: value })}
      >
        Save
      </button>
    </div>
  );
}
