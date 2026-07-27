# MedTech Reimbursement Readiness Agent

A locally hosted decision-support application that analyzes medtech companies, their websites and
product documentation, and applicable U.S. regulatory/reimbursement authorities — surfacing gaps,
conflicts, and stale information with full source citations. It uses OpenRouter for model inference
but keeps all documents, crawls, embeddings, and analysis history on your machine by default.

This is **not** legal, regulatory, coding, or billing advice. See `docs/security.md` and the
in-app Settings notice before using it with any sensitive data.

## Project status

This repository is being built milestone-by-milestone (see `docs/operations.md` for the full
sequence). Current state:

- **Milestone 1 — Foundation: done.** Docker Compose stack (frontend, api, worker, scheduler,
  postgres+pgvector, redis) boots; FastAPI health check; local-only settings page wired
  end-to-end (OpenRouter key never returned to the browser); React/Vite/TS/Tailwind shell with the
  full navigation IA from the spec (most sections are placeholders until their milestone lands).
- **Milestone 2 — Projects & document ingestion: done.** Company/Product/Project CRUD (API +
  UI); document upload (PDF/DOCX/PPTX/XLSX/CSV/HTML/Markdown/TXT) with content-sniffed MIME
  validation, executable rejection, and a quarantine path for failed uploads; structure-aware
  chunking with page/heading-path citation labels; ingestion runs as a Celery job the UI polls to
  completion; Authority Library upload endpoint (`POST /api/v1/authority/documents`). No
  retrieval/search yet — embeddings and hybrid search land in Milestone 3.
- **Milestone 3 — Retrieval: done.** Local CPU-by-default embeddings via Sentence Transformers
  (`sentence-transformers/all-MiniLM-L6-v2`, 384-dim, matching the `pgvector` column), computed
  automatically right after a document finishes chunking; Postgres full-text search
  (`to_tsvector`/`ts_rank`) populated alongside; hybrid retrieval combines both via reciprocal-rank
  fusion with an authority-level boost (never lets raw semantic similarity alone outrank a binding
  authority source), and always includes the shared Authority Library alongside a project's own
  documents. A raw search preview panel lives at the bottom of each project's page; a proper
  Source Inspector UI lands in Milestone 7. `scripts/reindex_project.py` re-embeds a project (or
  the whole authority library) after an embedding-model change.
- **Milestone 4 — Website crawler: done.** SSRF-guarded crawler (blocks loopback/private/
  link-local/cloud-metadata addresses and literal `file://`/`ftp://` schemes; re-validates every
  redirect hop, closing the most common real-world SSRF vector); robots.txt compliance with
  correct per-agent-group semantics; same-registrable-domain scoping with an optional
  follow-subdomains toggle; deterministic hash-based page diffing against the previous snapshot
  (no LLM involved in detecting whether a page changed, per spec); crawled HTML pages flow through
  the same parse/chunk/embed pipeline as uploads, so they're searchable identically. Runs from
  each project's page (crawl wizard, snapshot list, page list, diff summary). Known gap: the
  Playwright JS-rendering fallback is accepted as a setting but not yet wired to a real browser
  (falls back to plain HTTP fetch, logged clearly rather than silently).
- **Milestone 5 — OpenRouter integration & structured analyses: done.** Real OpenRouter client
  (`app/services/llm/openrouter_provider.py`) using strict JSON-schema structured outputs, one
  automatic repair retry on schema validation failure, exponential backoff on transient errors
  only (never retries a 4xx), and full token/cost/model-identity recording per stage. The
  compliance master prompt is now a versioned DB row (seeded from
  `prompts/master_system_prompt.md`) composed with immutable security instructions + a
  module-specific prompt + structured project facts + retrieved evidence — untrusted retrieved
  content is always wrapped in explicit boundaries and never placed in the system-message region.
  The full 11-stage pipeline (input audit → product fact extraction → claim extraction →
  regulatory/coding/coverage/payment/billing/marketing analysis → synthesis → citation audit) runs
  as a Celery job with cooperative cancellation, persisting `Finding`/`Citation`/`CodingCandidate`/
  `CodingRequirement`/`ExtractedClaim` rows with citations resolved back to the exact retrieved
  chunks. Runs from each project's page; results (verdict, risk, readiness/confidence scores,
  findings, coding eligibility matrix) render on a dedicated analysis results page. Redaction
  toggles (email/phone/patient-identifier) from Settings are applied to retrieved text before it
  reaches OpenRouter. **Known gap**: `ExtractedClaim` rows are persisted during the claim-extraction
  stage but have no dedicated Claims Register review UI yet (Milestone 7).
- Milestones 6–9 (further synthesis/scoring polish, UI polish, monitoring, security/tests
  hardening) are **not yet built**. Their nav entries exist but say so.

Do not treat anything beyond Companies/Projects/Website/Documents/Authority
Library/Search/Analyses/Settings as functional yet.

## Prerequisites

- Docker and Docker Compose v2
- An OpenRouter API key (get one at https://openrouter.ai) — optional until Milestone 5, but you
  can add it now via Settings

## Quickstart

This is a fully local, self-contained app — no cloud account or hosting needed, just Docker. Every
setting has a working default, so a `.env` file is optional, not required.

```bash
git clone https://github.com/wizbubba1/complianceagent.git
cd complianceagent
docker compose up --build
```

That's it. The `api` container runs any pending database migrations automatically on every boot
(safe to leave in place even once you're up to date — it's a no-op if there's nothing new), so
there's no separate migration step for a fresh install. `make migrate` still exists if you ever
want to run migrations manually without restarting the container (e.g. after pulling new code
while `api` is still running from before the pull).

Then open http://localhost:3000. The API is at http://localhost:8000/api/v1 (docs at
http://localhost:8000/docs). Both are bound to `127.0.0.1` only — set `ALLOW_LAN_ACCESS=true` and
`APP_HOST=0.0.0.0` in `.env` if you deliberately want LAN access (not recommended).

Closing the terminal doesn't stop anything (Docker Desktop keeps the containers running in the
background) — use `make down` (or `docker compose down`) to actually stop it, or `make reset` to
also wipe all local data and start clean.

### Add your OpenRouter (and optional Brave Search) key

Settings → paste the key(s) → Save. Keys live in this deployment's own local Postgres database
(a `runtime_settings` table, not a file), so they persist across restarts but never leave your
machine, are never sent back to the browser (only a masked preview is shown), and are not
committed to git. Each separate `docker compose` deployment — e.g. a teammate's own laptop — has
its own independent database, so keys (and all scan data) are never shared between machines unless
you deliberately set that up.

### Stopping / resetting

```bash
make down     # stop containers, keep data
make reset    # stop containers and delete the Postgres volume (destructive)
```

## Repository layout

See `docs/architecture.md` for the full picture. At a glance:

```
backend/    FastAPI app, Celery workers, Alembic migrations
frontend/   React + Vite + TypeScript + Tailwind dashboard
prompts/    Versioned master compliance prompt + module prompts (loaded at runtime, not hardcoded)
data/       Local storage root (documents, crawls, exports) — gitignored except structure
scripts/    Operational scripts (seed, backup, restore, reindex)
docs/       Architecture, data model, security, prompt design, reimbursement-analysis notes
```

## The compliance master prompt

`prompts/master_system_prompt.md` holds the current SonoHL Compliance Intelligence Agent master
prompt (v1) supplied for this build. It is the controlling reasoning policy for every compliance
analysis module (fact extraction, claim extraction, regulatory/coding/coverage/payment/billing/
marketing analysis, synthesis, citation audit — see the other files in `prompts/`). Starting in
Milestone 5, the active prompt version is loaded from the database (versioned, editable, auditable
from a Prompt Management screen) rather than hardcoded into application code; this file is the
seed for that first version.

## Troubleshooting

- **First `make build` is slow (several minutes) / downloads hundreds of MB** — expected. The
  local embedding model dependency (PyTorch, CPU-only build) is a sizeable download the first
  time; Docker caches this layer afterward so subsequent builds are fast unless
  `backend/pyproject.toml` changes.
- **`docker: No such file or directory` when running `make ...`** — Docker Desktop isn't
  installed or isn't running. Install it from docker.com, open it, and wait for the whale icon in
  the menu bar to stop animating before retrying.
- **Ports already in use** — change `API_PORT` / `FRONTEND_PORT` in `.env`, or the mapped host
  ports for Postgres (`5433`) / Redis (`6380`) in `docker-compose.yml`.
- **Frontend can't reach the API** — confirm `VITE_API_BASE_URL` (defaults to
  `http://localhost:8000/api/v1`) and that the `api` container is healthy (`docker compose ps`).

## License

MIT — see `LICENSE`.
