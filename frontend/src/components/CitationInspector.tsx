import { useState } from "react";

import type { Citation } from "../types/analysis";

/**
 * Source Inspector (Milestone 7): citations previously only showed a role
 * badge with the quoted text in a native title="" tooltip -- tiny, easy to
 * miss, not selectable. This surfaces the actual retrieved source text
 * (already stored on Citation.quoted_text at citation-creation time, up to
 * 2000 characters -- see app/services/analysis/pipeline.py::_resolve_citations)
 * in a real, readable panel.
 */
export function CitationBadge({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false);
  const hasSafeUrl = citation.url && /^https?:\/\//.test(citation.url);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="text-xs rounded bg-slate-100 dark:bg-slate-900 px-2 py-0.5 hover:bg-slate-200 dark:hover:bg-slate-800"
      >
        {citation.citation_role}
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="max-w-2xl w-full max-h-[80vh] overflow-y-auto rounded bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-5 space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wide">{citation.citation_role}</p>
                {citation.section_title && <p className="text-sm font-medium">{citation.section_title}</p>}
                {citation.page_number != null && (
                  <p className="text-xs text-slate-500">Page {citation.page_number}</p>
                )}
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-lg leading-none"
              >
                ×
              </button>
            </div>

            <div className="text-sm whitespace-pre-wrap rounded bg-slate-50 dark:bg-slate-900 p-3 border border-slate-100 dark:border-slate-800">
              {citation.quoted_text || "No source text was captured for this citation."}
            </div>

            <div className="flex items-center justify-between text-xs text-slate-500">
              <span>Verification: {citation.verification_status}</span>
              {hasSafeUrl && (
                <a
                  href={citation.url!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-slate-900 dark:text-slate-100 underline"
                >
                  Open source ↗
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
