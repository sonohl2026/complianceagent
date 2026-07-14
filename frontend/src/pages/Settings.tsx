import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { MasterPromptSection } from "../components/MasterPromptSection";
import type { AppSettings, AppSettingsUpdate } from "../types/settings";
import { AuthorityLibrary } from "./AuthorityLibrary";

const TABS = ["General", "Authority Library"] as const;
type Tab = (typeof TABS)[number];

export function Settings() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("General");
  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<AppSettings>("/settings"),
  });
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [modelInput, setModelInput] = useState("");

  const mutation = useMutation({
    mutationFn: (update: AppSettingsUpdate) => api.put<AppSettings>("/settings", update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setApiKeyInput("");
    },
  });

  if (isLoading || !data) {
    return <p className="text-sm text-slate-500">Loading settings…</p>;
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h2 className="text-lg font-semibold">Settings</h2>

      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-sm -mb-px border-b-2 ${
              tab === t
                ? "border-slate-900 dark:border-slate-100 font-medium"
                : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Authority Library" && <AuthorityLibrary />}

      {tab === "General" && (
        <>

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

          <MasterPromptSection />
        </>
      )}
    </div>
  );
}
