import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { Company, CompanyCreate } from "../types/company";
import type { Project, ProjectCreate } from "../types/project";

export function NewAnalysis() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [companyId, setCompanyId] = useState("");
  const [showCompanyForm, setShowCompanyForm] = useState(false);
  const [companyForm, setCompanyForm] = useState<CompanyCreate>({ name: "", website_url: "" });
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [projectForm, setProjectForm] = useState<ProjectCreate>({
    company_id: "",
    name: "",
    jurisdiction: "United States",
  });

  const { data: companies, isLoading: companiesLoading } = useQuery({
    queryKey: ["companies"],
    queryFn: () => api.get<Company[]>("/companies"),
  });

  const { data: projects, isLoading: projectsLoading } = useQuery({
    queryKey: ["projects", companyId],
    queryFn: () => api.get<Project[]>(`/projects?company_id=${companyId}`),
    enabled: !!companyId,
  });

  const createCompany = useMutation({
    mutationFn: (payload: CompanyCreate) => api.post<Company>("/companies", payload),
    onSuccess: (company) => {
      queryClient.invalidateQueries({ queryKey: ["companies"] });
      setCompanyForm({ name: "", website_url: "" });
      setShowCompanyForm(false);
      setCompanyId(company.id);
    },
  });

  const createProject = useMutation({
    mutationFn: (payload: ProjectCreate) => api.post<Project>("/projects", payload),
    onSuccess: (project) => navigate(`/projects/${project.id}`),
  });

  return (
    <div className="space-y-8 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold">New analysis</h2>
        <p className="text-sm text-slate-500 mt-1">
          Pick the company and project you're working on, then add product details, documents,
          or a website to analyze. Everything you need — uploads, crawling, and running the
          analysis — lives together on the project's page.
        </p>
      </div>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          1. Company
        </h3>
        {companiesLoading && <p className="text-sm text-slate-500">Loading…</p>}
        {companies && companies.length > 0 && (
          <select
            value={companyId}
            onChange={(e) => {
              setCompanyId(e.target.value);
              setProjectForm((f) => ({ ...f, company_id: e.target.value }));
            }}
            className="w-full rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1.5 text-sm"
          >
            <option value="">Select a company…</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        )}

        {!showCompanyForm && (
          <button
            className="text-sm text-slate-600 dark:text-slate-300 underline decoration-dotted"
            onClick={() => setShowCompanyForm(true)}
          >
            + New company
          </button>
        )}
        {showCompanyForm && (
          <form
            className="flex flex-wrap gap-2 rounded border border-slate-200 dark:border-slate-800 p-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (companyForm.name.trim()) createCompany.mutate(companyForm);
            }}
          >
            <input
              required
              autoFocus
              placeholder="Company name"
              value={companyForm.name}
              onChange={(e) => setCompanyForm({ ...companyForm, name: e.target.value })}
              className="flex-1 min-w-48 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
            />
            <input
              placeholder="Website URL (optional)"
              value={companyForm.website_url ?? ""}
              onChange={(e) => setCompanyForm({ ...companyForm, website_url: e.target.value })}
              className="flex-1 min-w-48 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
            />
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={createCompany.isPending}
                className="rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 text-sm disabled:opacity-50"
              >
                Create
              </button>
              <button
                type="button"
                className="rounded border border-slate-300 dark:border-slate-700 px-3 py-1 text-sm"
                onClick={() => setShowCompanyForm(false)}
              >
                Cancel
              </button>
            </div>
            {createCompany.isError && (
              <p className="w-full text-xs text-risk-critical">
                {(createCompany.error as Error).message}
              </p>
            )}
          </form>
        )}
      </section>

      {companyId && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            2. Project
          </h3>
          <p className="text-xs text-slate-500">
            A project holds one product's website, documents, and analysis history. Resume an
            existing one or start a new one.
          </p>
          {projectsLoading && <p className="text-sm text-slate-500">Loading…</p>}
          {projects && projects.length > 0 && (
            <ul className="space-y-2">
              {projects.map((p) => (
                <li key={p.id}>
                  <button
                    className="w-full text-left rounded border border-slate-200 dark:border-slate-800 px-3 py-2 text-sm hover:bg-slate-50 dark:hover:bg-slate-900"
                    onClick={() => navigate(`/projects/${p.id}`)}
                  >
                    <span className="font-medium">{p.name}</span>
                    {p.jurisdiction && (
                      <span className="ml-2 text-slate-500">({p.jurisdiction})</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {!showProjectForm && (
            <button
              className="text-sm text-slate-600 dark:text-slate-300 underline decoration-dotted"
              onClick={() => setShowProjectForm(true)}
            >
              + New project
            </button>
          )}
          {showProjectForm && (
            <form
              className="flex flex-wrap gap-2 rounded border border-slate-200 dark:border-slate-800 p-4"
              onSubmit={(e) => {
                e.preventDefault();
                if (projectForm.name.trim()) {
                  createProject.mutate({ ...projectForm, company_id: companyId });
                }
              }}
            >
              <input
                required
                autoFocus
                placeholder="Project name"
                value={projectForm.name}
                onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })}
                className="flex-1 min-w-48 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
              />
              <input
                placeholder="Jurisdiction"
                value={projectForm.jurisdiction ?? ""}
                onChange={(e) => setProjectForm({ ...projectForm, jurisdiction: e.target.value })}
                className="flex-1 min-w-48 rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
              />
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={createProject.isPending}
                  className="rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1 text-sm disabled:opacity-50"
                >
                  Create and continue
                </button>
                <button
                  type="button"
                  className="rounded border border-slate-300 dark:border-slate-700 px-3 py-1 text-sm"
                  onClick={() => setShowProjectForm(false)}
                >
                  Cancel
                </button>
              </div>
              {createProject.isError && (
                <p className="w-full text-xs text-risk-critical">
                  {(createProject.error as Error).message}
                </p>
              )}
            </form>
          )}
        </section>
      )}
    </div>
  );
}
