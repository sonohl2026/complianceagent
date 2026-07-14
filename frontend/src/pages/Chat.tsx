import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { ChatMessage } from "../types/chat";
import type { Project } from "../types/project";

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-xl rounded p-3 text-sm ${
          isUser
            ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
            : "border border-slate-200 dark:border-slate-800"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {!isUser && message.citations_json.length > 0 && (
          <div className="mt-2 pt-2 border-t border-slate-200 dark:border-slate-800 space-y-1">
            <p className="text-xs text-slate-500">Sources:</p>
            {message.citations_json.map((c, i) => (
              <div key={i} className="text-xs text-slate-500">
                [{c.role}] {c.document_title ?? "Untitled"}
                {c.section_title ? `, ${c.section_title}` : ""}
                {c.url && /^https?:\/\//.test(c.url) && (
                  <>
                    {" — "}
                    <a href={c.url} target="_blank" rel="noopener noreferrer" className="underline">
                      open ↗
                    </a>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function Chat() {
  const queryClient = useQueryClient();
  const [projectId, setProjectId] = useState<string>("");
  const [question, setQuestion] = useState("");

  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get<Project[]>("/projects"),
  });

  const { data: messages } = useQuery({
    queryKey: ["chat", projectId],
    queryFn: () => api.get<ChatMessage[]>(`/projects/${projectId}/chat`),
    enabled: !!projectId,
  });

  const askMutation = useMutation({
    mutationFn: (q: string) => api.post<ChatMessage>(`/projects/${projectId}/chat`, { question: q }),
    onSuccess: () => {
      setQuestion("");
      queryClient.invalidateQueries({ queryKey: ["chat", projectId] });
    },
  });

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Chat</h2>
        <select
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
        >
          <option value="">Select a project…</option>
          {projects?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
      <p className="text-sm text-slate-500">
        Ask a question about this project's documents, website, and the shared Authority Library.
        Every answer is grounded only in retrieved evidence and cited — this is a quick lookup, not
        a substitute for running the full compliance analysis.
      </p>

      {!projectId && <p className="text-sm text-slate-500">Select a project to start.</p>}

      {projectId && (
        <>
          <div className="space-y-3 min-h-[8rem]">
            {messages && messages.length === 0 && (
              <p className="text-sm text-slate-500">No questions asked yet for this project.</p>
            )}
            {messages?.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {askMutation.isPending && (
              <div className="flex justify-start">
                <div className="max-w-xl rounded border border-slate-200 dark:border-slate-800 p-3 text-sm text-slate-500">
                  Thinking…
                </div>
              </div>
            )}
          </div>

          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (question.trim()) askMutation.mutate(question.trim());
            }}
          >
            <input
              placeholder="e.g. Has this device received FDA clearance?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={askMutation.isPending}
              className="flex-1 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={askMutation.isPending || !question.trim()}
              className="rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 text-sm disabled:opacity-50"
            >
              Ask
            </button>
          </form>
          {askMutation.isError && (
            <p className="text-xs text-risk-critical">{(askMutation.error as Error).message}</p>
          )}
        </>
      )}
    </div>
  );
}
