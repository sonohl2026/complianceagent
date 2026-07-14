# Architecture

## Services (docker-compose.yml)

```
                 ┌─────────────┐        ┌─────────────┐
   browser  ───▶ │  frontend   │  ───▶  │     api     │  ───▶ OpenRouter (HTTPS, egress only)
 127.0.0.1:3000  │ React+Vite  │  HTTP  │  FastAPI    │
                 └─────────────┘        └──────┬──────┘
                                                │
                              ┌─────────────────┼─────────────────┐
                              ▼                 ▼                 ▼
                        ┌───────────┐    ┌───────────┐     ┌───────────┐
                        │ postgres  │    │   redis   │     │  worker/  │
                        │ +pgvector │◀──▶│  (broker) │◀──▶ │ scheduler │
                        └───────────┘    └───────────┘     │  (Celery) │
                                                            └───────────┘
```

- **frontend** — React/TypeScript/Vite/Tailwind SPA. Talks only to `api`, never directly to
  Postgres, Redis, or OpenRouter. Holds no secrets.
- **api** — FastAPI. Owns all business logic behind `app/services/*` (llm, crawling, parsing,
  retrieval, analysis, citations, reporting, scheduling, storage — populated milestone by
  milestone). Route handlers in `app/api/v1/*` stay thin.
- **worker** — Celery worker. Runs crawls, document parsing/embedding, and multi-stage analyses
  out of the HTTP request path (build spec §5: "Do not run long website crawls or complete
  analyses inside ordinary HTTP request handlers").
- **scheduler** — Celery Beat. Runs `monitoring.dispatch_due_recrawls` every 30 minutes, dispatching
  due `ScheduledRecrawl` rows onto the same crawl task a manual crawl uses; the worker then runs
  material-change alert classification after a scheduled (not manual) recrawl completes — see
  "Milestone 8" in `docs/data-model.md`.
- **postgres** — PostgreSQL 16 + pgvector extension. Single source of truth for relational data,
  vector embeddings, and full-text search (`tsvector`).
- **redis** — Celery broker/result backend.

## Trust boundaries

1. **Browser ↔ api** — local-only CORS (`http://localhost:3000` / `127.0.0.1:3000`), no cookies,
   strict security headers, no secrets ever serialized into API responses (see `docs/security.md`).
2. **api/worker ↔ OpenRouter** — the only network egress in the system that leaves the host.
   Gated by the `LLMProvider` abstraction (`app/services/llm/`, landing Milestone 5) so requests
   carry only the minimum retrieved context, never whole documents or whole libraries.
3. **worker ↔ public internet (crawler)** — outbound only, SSRF-guarded (private/loopback/
   link-local/metadata-endpoint ranges blocked, redirects re-validated), robots.txt-aware,
   same-registrable-domain by default. Lands in Milestone 4.
4. **Everything else stays on the host** — uploaded documents, crawl snapshots, parsed text,
   embeddings, prompts, model-response records, and reports live under `data/storage/` and in the
   `postgres` volume, both local Docker volumes/bind mounts, never uploaded elsewhere.

## Data flow (once Milestones 2–6 land)

1. User creates a Company → Product → Project.
2. User crawls the company website and/or uploads documents → ingestion pipeline (parse → chunk →
   embed → index) runs in `worker`, progress streamed to the UI via a Job record.
3. User runs an analysis → a staged pipeline (input audit → fact extraction → claim extraction →
   regulatory → coding → coverage → payment → billing → marketing → synthesis → citation audit)
   executes in `worker`, each stage a separate structured OpenRouter call validated against a
   JSON schema, each finding carrying citations back to specific `SourceChunk` rows.
4. Results are stored as `AnalysisRun` / `Finding` / `Citation` / `CodingCandidate` rows and
   rendered in the dashboard; exportable as Markdown/JSON.

## Why a staged pipeline instead of one large agentic loop

Per the build spec (§13, §30): "A simple, auditable multi-stage pipeline is preferable to an
opaque fully autonomous agent." Each stage has a narrow prompt, a fixed input bundle, and a
strict output schema, which makes citation auditing and reproducibility (exact model, prompt
version, retrieval settings, token usage recorded per `AnalysisRun`) tractable. This trades some
flexibility for auditability, which is the right trade for a regulated-domain tool.
