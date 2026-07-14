# Data Model

Implemented so far, in `backend/app/models/`: `Company`, `Product`, `Project`, `SourceDocument`,
`SourceChunk`, `Job` (Milestone 2), `CrawlSnapshot`/`CrawledPage` (Milestone 4), `PromptVersion`,
`AnalysisRun`, `Finding`, `Citation`, `ExtractedClaim`, `CodingCandidate`, `CodingRequirement`
(Milestone 5). Migrations `0001_initial_schema`, `0002_vector_index`, `0003_crawl_tables`,
`0004_analysis_tables` create all of them (hand-authored — see each migration file's docstring for
why — and cross-checked against `Base.metadata` DDL via a SQLAlchemy mock engine rather than a
live database).

Not yet implemented: `ChatThread`/`ChatMessage` (Milestone 7).

`CrawledPage.source_document_id` is one addition beyond the literal spec §7.7 field list: it links
a crawled page to the `SourceDocument` it was ingested into, since the spec doesn't otherwise say
how crawled pages become retrievable evidence (see "Crawling" below).

`Project.system_prompt_version_id` now has a real foreign key to `prompt_versions.id` (added by
`0004_analysis_tables`, since that table didn't exist until this migration).

## Design constraints carried through from the spec

- UUID primary keys, UTC timestamps everywhere (`app/models/base.py` mixins).
- `SourceDocument.collection_type` strictly separates `COMPANY` vs `AUTHORITY` (vs `THIRD_PARTY`/
  `COMPETITOR`) — company marketing content must never be retrievable as if it were an authority
  rule. Enforced today only at the data-model level; retrieval-time ranking enforcement lands in
  Milestone 3.
- `SourceChunk` is never created without a `citation_label` (document title + page/slide +
  heading path) — see `app/services/parsing/chunking.py`. `embedding` and `search_vector` columns
  exist now (so no later ALTER TABLE is needed) but are populated starting in Milestone 3.
- `Finding` (Milestone 6) will carry a `status` from the fixed enum (`VERIFIED`, `LIKELY`,
  `CONDITIONAL`, `UNRESOLVED`, `MISSING`, `CONFLICTING`, `STALE`, `NOT_APPLICABLE`) — "unknown"
  must never be silently coerced to "yes" or "no".
- `CodingCandidate` (Milestone 6) will have independent `eligibility_status`, `coverage_status`,
  `payment_status`, `billing_status` fields — coding, coverage, payment, and billing are never
  merged into one "reimbursable" boolean.

## Foreign-key cycle note

`Product.status_source_id -> SourceDocument`, `SourceDocument.project_id -> Project`, and
`Project.default_product_id -> Product` form a cycle across four tables (companies, products,
projects, source_documents). The migration creates all four tables first without those particular
inline foreign keys, then adds every FK via `op.create_foreign_key` afterward — this mirrors
exactly what SQLAlchemy's own `MetaData.create_all()` does when it detects a dependency cycle
(verified by compiling `Base.metadata.create_all()` DDL through a mock engine and diffing against
the hand-written migration).

## Retrieval (Milestone 3)

`app/services/embeddings/` defines an `EmbeddingProvider` protocol and a
`SentenceTransformerProvider` implementation (local, CPU by default, model/device/batch size from
`.env`). `app/services/embeddings/indexing.py::embed_document` runs right after chunking in the
ingestion Celery task: computes embeddings for every chunk, records the exact model
name/dimensions/timestamp in each chunk's `metadata_json` (so a model change can be detected),
and populates `search_vector` via a single bulk `to_tsvector` update.

`app/services/retrieval/hybrid_search.py` combines a pgvector cosine-distance candidate query and
a Postgres full-text (`plainto_tsquery`/`ts_rank`) candidate query via reciprocal-rank fusion
(`app/services/retrieval/fusion.py`), then applies a multiplicative authority-level boost so a
binding authority source can outrank a merely-more-similar low-authority one without a hard
override. Retrieval for a project always includes the shared `AUTHORITY` collection alongside
that project's own documents (fixed in review — an earlier version of the project filter
accidentally excluded authority documents entirely). Exposed at
`POST /api/v1/projects/{id}/search` for now; the analysis pipeline (Milestone 5) will call the
same function directly rather than through HTTP.

## Crawling (Milestone 4)

`app/services/crawling/` implements: SSRF protection (`ssrf.py`, see `docs/security.md`), robots.txt
compliance (`robots.py`), URL normalization/same-registrable-domain scoping (`url_utils.py`), an
SSRF-guarded fetcher with per-redirect-hop revalidation (`fetch.py`), HTML link/metadata
extraction (`extract.py`), deterministic hash-based diffing (`diff.py` — no LLM involved, per
build spec §10.4), and the BFS crawl orchestrator (`crawler.py`) tying all of it together.

Each crawled HTML page is ingested through `app.services.parsing.ingestion.ingest_crawled_html`,
which reuses the same parse → chunk → persist path as an uploaded document
(`ingest_upload`), then `embed_document` — so crawled pages are retrievable via hybrid search
identically to an uploaded file, with `SourceDocument.url` set and `SourceDocument.source_type =
"website_page"`. `CrawlSnapshot`/`CrawledPage` rows track the crawl itself (status, page count,
per-page HTTP status/robots verdict/word count/change-vs-prior).

Cancellation (`POST /api/v1/crawls/{id}/cancel`) is cooperative: it flips
`CrawlSnapshot.status` to `CANCELLED`, and the running crawl loop re-reads that column from the
database before fetching each page and stops itself — there is no forced Celery task kill.

**Known gap, documented rather than silently skipped**: `render_js` (Playwright fallback for
JS-rendered pages) is accepted by the API and crawl settings but is not actually wired to a
Playwright browser yet — the crawler logs a note and falls back to the default HTTPX-only fetch.
Wiring a real headless-browser fallback is deferred; PDF discovery during a crawl is recorded but
not yet auto-ingested as a document (only HTML pages are ingested today).

## Analysis pipeline (Milestone 5)

`app/services/llm/` holds the OpenRouter integration: `base.py` defines the `LLMProvider` protocol
(so a local OpenAI-compatible server could implement the same interface later without pipeline
changes), `openrouter_provider.py` is the real implementation (strict JSON-schema structured
outputs, one repair retry, exponential backoff on transient errors only, never retries a 4xx),
and `redaction.py` applies the Settings privacy toggles to retrieved chunk text before it leaves
the host.

`app/services/analysis/` holds the pipeline itself: `prompts_service.py` loads the versioned
master prompt (seeded from `prompts/master_system_prompt.md` into the `prompt_versions` table on
first use) and the per-stage module prompt files; `prompt_composer.py` assembles the final
system/user messages in the required order (immutable security preamble → master prompt → module
prompt → project facts → untrusted-content-wrapped evidence), guaranteeing retrieved text never
lands in the system-message region; `pipeline.py` runs the 11 stages in order (input audit,
product fact extraction, claim extraction, coding analysis, then the five domain-analysis stages —
regulatory, coverage, payment, billing, marketing — then synthesis, then citation audit),
retrieving a stage-specific evidence bundle via `hybrid_search` for each, persisting
`Finding`/`Citation` (and `CodingCandidate`/`CodingRequirement`, `ExtractedClaim`) rows as it goes.
Citations are resolved from a per-analysis `citation_label -> RetrievedChunk` lookup built while
retrieving, so every finding's citations point at the exact chunk that was actually shown to the
model for that stage — never a citation invented after the fact.

Cancellation (`POST /api/v1/analyses/{id}/cancel`) is cooperative, same pattern as the crawler:
it flips `AnalysisRun.status` to `CANCELLED`, and the pipeline re-reads that column between stages.

**Known gap**: the citation-audit stage (11) validates and can downgrade a `Finding.status` when
citations don't hold up, but does not yet re-validate that a quoted citation's text is verbatim
present in the source chunk (build spec §13 Stage 11 asks for exact-quote verification) — it
currently checks citation *presence*, not quote fidelity byte-for-byte. `ExtractedClaim` rows are
persisted but have no dedicated review UI yet (Milestone 7).

### Real-world fixes from the first live runs

Running the pipeline against a real OpenRouter account (not just mocked tests) surfaced several
bugs invisible to unit tests, each fixed and covered by a regression test:

- **Cross-event-loop database connections**: each Celery task called `asyncio.run(...)`, which
  creates a brand-new event loop every invocation; a connection pooled by the shared engine (fine
  for the single-event-loop FastAPI process) became unusable the moment a *different* task's
  *different* loop tried to reuse it (`asyncpg` raises "attached to a different loop"). Fixed by
  giving every Celery task its own `NullPool` engine, created and disposed per task
  (`app.database.create_worker_engine_and_sessionmaker`) — see all three files in `app/workers/`.
- **Provider-specific structured-output incompatibilities**: some models behind OpenRouter reject
  `temperature` outright ("deprecated for this model") and reject JSON Schema `minimum`/`maximum`
  keywords on integer fields. Fixed by stripping `temperature` and retrying once on that specific
  error (`app/services/llm/openrouter_provider.py`), and by describing intended integer ranges in
  each field's description rather than as a schema constraint (`app/schemas/analysis_llm.py`).
- **Unbounded max_tokens**: leaving `max_tokens` unset let it default to a model's absolute max
  (65536 for one Opus-tier model), which made OpenRouter pre-authorize credits for that worst case
  and reject affordable requests. Fixed by always sending an explicit, bounded `max_tokens`
  (8000 default, 12000 for the more verbose stages).
- **Undersized database columns**: `CodingCandidate.coverage_status`/`payment_status`/
  `billing_status` were `VARCHAR(64)`, but the pipeline correctly writes full explanatory
  sentences into them (per the master prompt's philosophy of explaining *why* something is
  unresolved) — widened to `TEXT` in `0005_widen_coding_status_columns`.
- **Orphaned QUEUED rows**: if enqueueing a Celery task raised for any reason (including the
  import-time failure above), the Job/AnalysisRun/CrawlSnapshot row it had already committed as
  QUEUED stayed that way forever with no worker ever picking it up. Fixed with
  `app.services.jobs.enqueue.enqueue_job`, which marks the row FAILED with a clear error instead.
- **Clean OpenRouter error messages**: a 402 (insufficient credits) or 401 (invalid key) response
  from OpenRouter surfaced as a hard-to-read raw JSON dump. Fixed in
  `app/services/llm/openrouter_provider.py::_call_with_retry` with a clear, actionable message
  for each.
- **Waiting several minutes to learn credits were insufficient**: an analysis that was doomed to
  fail on a 402 still ran 3-4 of 11 stages (each a real, billed LLM call) before hitting the stage
  that finally exceeded the balance. Fixed with a pre-flight check
  (`app/services/llm/cost_estimate.py::preflight_credit_check`, called from `POST
  /projects/{id}/analyses` before any `Job`/`AnalysisRun` row is even created) that compares the
  account's current balance against a worst-case cost floor: every stage sends an explicit
  `max_tokens` cap, so `sum(stage max_tokens) * completion_price_per_token` is a hard lower bound
  on total cost (prompt tokens are always additional). If the balance can't cover even that floor,
  the analysis is certain to fail partway through, so it's rejected instantly instead. This is a
  floor, not an exact prediction -- a run that passes this check can still fail on a 402 later if
  actual prompt-token usage (which varies with how much evidence gets retrieved) pushes the real
  cost past the balance. The check fails open (skips itself, doesn't block the analysis) if
  OpenRouter's `/credits` or `/models` endpoints return anything unexpected, since their exact
  response shape is exactly the kind of external API surface that can drift over time.

## Master prompt upload from the UI (user-requested)

`PromptVersion` (build spec §21) already existed as a versioned DB row, seeded once from
`prompts/master_system_prompt.md` on first use (`app/services/analysis/prompts_service.py
::get_active_master_prompt`) -- so this feature is "add a way to write new rows from the UI",
not a new storage model. `POST /api/v1/prompts/master/upload` (multipart file, PDF/DOCX/MD/TXT)
reuses the existing document-parsing pipeline (`app/services/parsing/validation.py::validate_upload`
+ `app/services/parsing/dispatch.py::parse_document` -- the same functions real document uploads
already go through) to extract text, then `app/api/v1/prompts.py::extract_prompt_text` confirms at
least 200 characters of readable content came out (rejecting e.g. a scanned/image-only PDF with no
text layer) before `prompts_service.create_master_prompt_version` deactivates every other version
and activates the new one. Every upload is permanently retained, never overwritten -- switching
back to an earlier version is `POST /prompts/master/versions/{id}/activate`, no data loss.
`get_active_master_prompt` already re-reads whichever row is flagged active on every run, so a
newly-activated version takes effect on the very next analysis with no other pipeline changes.

The uploaded content becomes the controlling system prompt verbatim, same trust level as the
seed file -- deliberately not sandboxed like retrieved evidence (`BEGIN/END UNTRUSTED SOURCE
CONTENT`), since replacing this content on purpose is exactly what the feature is for.

## Cost reduction (user-requested: real runs were costing $4-6 each)

Root cause, confirmed by measuring the actual seeded master prompt (not just estimating): it's
~8,400 words (~11,500 tokens), and `app/services/analysis/prompt_composer.py::compose_messages`
was resending it in full on every one of 11 stage calls with zero caching, while `prior_stage_outputs`
also grew every stage (stage 11 paid for the full accumulated JSON of stages 1-10). Three
independent fixes, all compatible with staying on the same model:

- **Trimmed prior-stage context**: `app/services/analysis/pipeline.py::_prior_outputs_for_stage`
  curates a specific subset of prior outputs per stage instead of forwarding the ever-growing
  full history to every call. Synthesis is the deliberate exception -- it still gets everything,
  since it needs the whole picture.
- **Merged the 5 independent domain stages** (regulatory/coverage/payment/billing/marketing) into
  one call (`CombinedDomainAnalysisResult` in `app/schemas/analysis_llm.py`,
  `_build_combined_domain_module_prompt`/`_retrieve_combined_domain_evidence` in pipeline.py) --
  they never depended on each other's output, so 5 calls each re-paying for the master prompt
  became 1. The pipeline is 7 stages now, not 11 (`domain_analysis` replaces the 5).
  `COMBINED_DOMAIN_MAX_TOKENS = 28000` is a judgment call, not a measured optimum -- if the
  combined call's output looks truncated (`finish_reason == "length"`), raise it.
- **Prompt caching** (`compose_messages(..., enable_prompt_caching=...)`, toggle at
  `openrouter_prompt_caching` in Settings, default on): splits the system prompt into a
  cache_control-tagged block (immutable preamble + master prompt, byte-identical across every
  call in one run) and an uncached block (the per-stage module prompt, which varies). This is the
  least certain of the three fixes -- it depends on OpenRouter currently passing Anthropic's
  `cache_control` breakpoints through unmodified, which is exactly the kind of provider API detail
  that can drift. Verify actual savings against a real run's `AnalysisRun.cost_json` rather than
  trusting this blindly; the Settings toggle exists specifically so it can be turned off in one
  click if it turns out not to help (or to cause problems).

None of this touches `prompts/master_system_prompt.md` itself or reduces analytical rigor --
every stage still sees the full controlling master prompt and whatever evidence it needs.

## Report length (user-requested: 40-page reports nobody will read)

`build_markdown_report`/`build_html_report`/`build_pdf_report` all take `mode: "condensed" |
"extended"`, defaulting to condensed. Condensed shows verdict/risk/score, executive summary,
critical blockers, action plan, and the `CONDENSED_FINDING_LIMIT = 12` highest-priority findings
(by risk then the model's own priority ranking) instead of every finding grouped by domain with
full citations and the coding matrix. Both modes render from the exact same already-computed
analysis data -- generating the extended version later costs nothing extra, it's a presentation
choice at export time, not a re-run. `GET /analyses/{id}/export.{md,pdf}?mode=condensed|extended`;
the frontend `ExportButtons` component has a toggle.

## Persistent compliance checklist (user-requested: track fixes across incremental site tweaks)

`ComplianceIssue` (migration `0007_compliance_issues`) is durable per-product, unlike `Finding`
(scoped to one `AnalysisRun`). After each run, `app/services/analysis/checklist.py
::reconcile_compliance_issues` compares the run's findings against the product's currently-OPEN
issues: a match (same domain + normalized title) keeps the issue open and refreshes its
description/risk; an unmatched new finding opens a new issue; a previously-open issue with no
matching finding in the new run gets marked RESOLVED. This is deterministic and free (no extra
LLM call, consistent with the whole point of this being a cost-reduction effort) but is a real
approximation -- if the model rewords a finding's title between runs, this reads it as a new
issue rather than the same one continuing. A follow-up could match on embedding similarity
instead of exact normalized-title equality. Surfaced at `GET
/products/{product_id}/compliance-checklist` and the `ComplianceChecklist` component on the
project page.

## Reporting and export (Milestone 6, pulled forward)

`app/services/reporting/` builds reports from a plain-dataclass snapshot of an `AnalysisRun`
(`data.py::gather_report_data`, decoupled from the ORM so `markdown_report.py`/`html_report.py`
are unit-testable with fixtures, no DB needed): a Markdown report matching build spec §22's
section order, an HTML rendering styled for print, and a PDF (via WeasyPrint, HTML→PDF) built
from that same HTML. All three always include the mandatory human-review disclaimer (build spec
§3.6) regardless of verdict. Exposed at `GET /api/v1/analyses/{id}/export.{md,json,pdf}`.
WeasyPrint needs Pango/Cairo/GDK-Pixbuf system libraries (added to `backend/Dockerfile`'s
`apt-get install` list) — validated by actually installing those libraries locally (via Homebrew)
and generating a real PDF, not just trusting the Dockerfile configuration.

The analysis results page also has a **findings-by-priority panel** — a client-side re-sort of
the same findings the API already returns (by risk severity, then the model's own priority
field), not a second billed LLM call to re-summarize what's already structured data.

### Hyperlinked source citations

Reports (Markdown/HTML/PDF) render each citation and a final "Sources" section as real
clickable links -- but the URL is *always* resolved server-side from a verified
`SourceDocument.url` (the actual crawled page URL, or a human-entered URL against an
Authority Library document), never supplied by the LLM. The model only ever picks a
`citation_label`, which resolves to a concrete retrieved chunk; `RetrievedChunk.document_url`
carries the source's URL through retrieval, and `_resolve_citations()` in
`app/services/analysis/pipeline.py` copies it onto `Citation.url`. Letting the model emit its
own URL string would be a serious hallucination risk (a plausible but fake or dead government
URL is easy for a model to produce and hard for a user to notice) -- this design makes that
class of error structurally impossible rather than relying on the model to behave.

Any URL a human enters (authority-document upload, or the `PUT /documents/{id}` metadata-update
endpoint used to backfill URLs onto existing Authority Library documents) is validated to start
with `http://`/`https://` at the schema boundary (`app/schemas/document.py::_require_http_scheme`),
with a second defense-in-depth check at render time (`html_report.py::_safe_href`) -- a report
that turns user data into `<a href>` tags is a stored-XSS surface if that validation is ever
bypassed.

## Ingestion pipeline (Milestone 2)

`app/services/parsing/ingestion.py::ingest_upload` is the single entry point: validate (size,
content-sniffed MIME, executable rejection) → hash (dedupe check) → store original bytes via the
`StorageBackend` abstraction → parse (`app/services/parsing/dispatch.py`, one module per format
under `parsers/`) → structure-aware chunk (`chunking.py`, heading-hierarchy aware, ~500-1000
approx-token target) → persist `SourceDocument` + `SourceChunk` rows. It runs inside a Celery task
(`app/workers/ingestion_tasks.py`), tracked by a `Job` row the frontend polls, not inline in the
upload request handler.

## Milestone 6 — deterministic readiness-score guardrail

`app/services/analysis/scoring.py::apply_readiness_score_guardrail` runs after synthesis, before
`AnalysisRun.readiness_score` is set: it checks the model's self-reported score against hard
internal-consistency rules (STOP verdict caps it at 25, CRITICAL overall risk caps it at 30, any
CRITICAL-risk finding caps it at 40, any MISSING/UNRESOLVED HIGH-or-worse finding caps it at 60)
and can only ever *lower* the model's number, never raise it. When a cap applies,
`AnalysisRun.readiness_score_note` records why, quoting the model's original number, so the
guardrail's existence is visible rather than silently overriding the model.

## Milestone 7 — UI polish

- **Dashboard** (`GET /api/v1/dashboard/summary`): real cross-company counts and the 10 most
  recent analyses, replacing the health-check-only stub.
- **Dark mode**: `frontend/src/hooks/useDarkMode.ts` toggles a `dark` class on `<html>`. Tailwind
  was already configured `darkMode: "class"` with `dark:` variants throughout every page -- there
  was simply never anything that added the class, so dark mode was unreachable dead CSS until now.
- **Claims Register** (`GET/PUT /api/v1/claims`): `ExtractedClaim` rows were already persisted by
  the claim_extraction pipeline stage but had no review UI; this is read/filter/mark-reviewed
  against existing data, not new extraction logic.
- **Source Inspector** (`frontend/src/components/CitationInspector.tsx`): citations previously
  showed only a role badge with the source text in a native `title=""` tooltip. Now a click opens
  a real panel with the full `Citation.quoted_text` (already captured server-side, up to 2000
  characters) and a link to the source when a verified URL is on file.
- **Cross-project list pages** (`GET /api/v1/documents`, `/crawls`, `/analyses`, all top-level):
  replaced the Documents/Website/Analyses placeholder pages with real aggregated views, each
  joined against `Project.name` (`SourceDocumentWithProject`/`CrawlSnapshotWithProject`/
  `RecentAnalysisRow` schemas).
- **Chat** (`app/services/chat/`, `ChatMessage` model): one retrieval + one small structured-output
  LLM call per question (`CHAT_MAX_TOKENS = 4000`), grounded only in the project's evidence plus
  the shared Authority Library, every claim required to carry a `citation_label`
  (`prompts/chat_qa.md`). Deliberately not the full pipeline -- same cost profile as one pipeline
  stage, not eleven. Not preflight-credit-checked like starting a full analysis, since
  `preflight_credit_check` estimates against the *full pipeline's* worst case, which would give a
  misleading answer for one cheap call.

## Milestone 8 — monitoring & scheduling

- **`ScheduledRecrawl`**: recurring recrawl configuration. Celery Beat (`app/workers/celery_app.py`
  `beat_schedule`, was an empty placeholder since Milestone 1) runs `monitoring.dispatch_due_recrawls`
  every 30 minutes; `app/services/monitoring/scheduling.py::dispatch_due_schedules` finds schedules
  whose `next_run_at` has passed and enqueues the *same* `crawling.run_crawl` task a manual crawl
  uses, just with `is_scheduled=True`, then advances `next_run_at` immediately (before attempting
  to enqueue) so a slow crawl or a transient broker failure can't cause a double-dispatch on the
  next tick.
- **Material-change alerts** (`Alert` model, `app/services/monitoring/material_change.py`): build
  spec §10.4's rule -- "do not use the LLM to decide whether a page changed; use deterministic
  hashing first, use the LLM only to summarize material changes" -- was implemented for the hash
  half in Milestone 4 (`app/services/crawling/diff.py`) but the LLM half was an explicit stub. Now:
  after a *scheduled* recrawl only (manual one-off crawls are unaffected, so this is additive to
  existing cost/behavior, not a change to it), pages the deterministic diff already flagged as
  changed get old/new text excerpts (via each `CrawledPage.source_document_id`'s `SourceChunk`s)
  fed through one combined classification call (`prompts/material_change_assessment.md`), and only
  changes classified material (not cosmetic) become `Alert` rows. Reuses `compose_messages`'
  evidence-wrapping (via synthetic `RetrievedChunk`s) rather than hand-rolling a second
  prompt-injection boundary for this untrusted crawled content.

## Milestone 9 — security, tests, docs

`tests/test_adversarial_security.py` consolidates and extends the security-relevant test coverage
that already existed spread across `test_ssrf.py`/`test_fetch.py` (SSRF, redirect chains) and
`test_validation.py` (upload validation) with a wider variety of realistic attack payloads:
8 real-world-shaped prompt-injection strings (fake system-message impersonation, boundary-marker
spoofing, base64/code-fence obfuscation) verified to never leak into the system-prompt region in
either the flat-string or prompt-caching-enabled code path, plus a boundary-spoofing test
confirming `wrap_untrusted_evidence` does no re-parsing of its own output (a fake embedded
"END UNTRUSTED SOURCE CONTENT" marker is preserved as literal text, not treated as structural);
7 malicious URL schemes (case variants, whitespace tricks, `data:`/`vbscript:`/`file:`) verified
rejected by both the schema-level validator and the HTML-report render-time check; and double-
extension upload tricks (`report.pdf.exe`, `malware.exe.pdf`) added to `test_validation.py`
confirming the extension allow-list check is a true-suffix match, never overriding the magic-byte
content check.

### Acceptance snapshot (this session)

Grounded in the actual repository state as of this work, not the original spec document (which
isn't in this session's context) -- see `docs/architecture.md` for anything predating this session.

- 236 backend tests passing (`pytest tests/ -q`), frontend type-checks (`tsc -b`) and production-
  builds (`vite build`) clean.
- All 9 build-spec milestones have real, working implementations: Foundation, Ingestion, Retrieval,
  Crawling, OpenRouter analysis, Synthesis/scoring, UI polish, Monitoring, Security/tests/docs.
- Known, deliberate scope limits (not oversights -- documented at the point they were made):
  the citation-audit stage checks citation *presence*, not byte-for-byte quote fidelity against
  source text (see "Analysis pipeline (Milestone 5)" above); the compliance-checklist matching
  across runs (`app/services/analysis/checklist.py`) is normalized-title equality, not semantic
  similarity, so a significantly reworded finding reads as a new issue rather than a continuation;
  Chat has no multi-turn agentic memory beyond the last few messages folded into context.
- Backup/restore of the Postgres volume was not built or tested this session -- Postgres data lives
  in the `postgres_data` named volume declared in `docker-compose.yml`; a `pg_dump`/`pg_restore`
  runbook is the natural next step if this is going into any kind of production use, not present
  today.
