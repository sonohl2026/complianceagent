# Reimbursement Readiness Agent v2.0 — Implementation Spec

**Audience:** AI coding agent. Execute tasks in order. Each task has acceptance criteria.
**Companion files:** `system_prompt_v2.md` (load verbatim as system prompt), `benchmark_suite.json` (regression fixtures).
**Background:** the strategy report (separate doc) explains *why*; this spec is *what to build*.

---

## 0. Architecture Overview

```
User upload/URL
   │
   ▼
STAGE 1 — EXTRACTION (cheap fast model, e.g. Haiku-class)
   Input: uploaded doc text / fetched page (truncate to ~8k tokens)
   Output: {product_name, manufacturer, aliases[], intended_use,
            technology_type, dev_stage_guess, candidate_search_terms[]}
   │
   ▼
STAGE 2 — RETRIEVAL (no LLM; parallel HTTP, hard 15s timeout each)
   ├─ openFDA: 510k, pma, classification, recall, enforcement, event, udi
   ├─ CMS Coverage API: NCD/LCD/article search
   └─ Web search: ≤3 queries (deep-dive tier only)
   │
   ▼
STAGE 3 — SYNTHESIS (strong model, e.g. Sonnet-class)
   Input: system_prompt_v2 (cached) + Stage-1 JSON + Stage-2 evidence bundle
   Output: assessment JSON (schema §4), target <1,500 output tokens
   │
   ▼
UI renders dashboard from JSON. Exports generated client-side.
```

Two tiers:
- **quick_scan**: Stage 1 + Stage 2 (openFDA + Coverage API only, no web search) + Stage 3. Target: <30s p50, <$0.10.
- **deep_dive**: adds web search (manufacturer reimbursement page, payer policies, evidence). Target: <90s p50, <$0.25.

---

## 1. Retrieval Layer (build first — this fixes the zero-score bug)

### 1.1 openFDA (api.fda.gov, free; no key needed at low volume)

Real endpoints (VERIFIED — do not invent others):

| Endpoint | Use |
|---|---|
| `/device/510k.json` | 510(k) clearances; search `device_name`, `applicant`, `openfda.device_name` |
| `/device/pma.json` | PMA approvals + supplements |
| `/device/classification.json` | product code, device class, regulation number |
| `/device/recall.json` + `/device/enforcement.json` | recalls (feeds Risk flag) |
| `/device/event.json` | MAUDE adverse events (Risk flag; cap at counts, don't ingest bodies) |
| `/device/udi.json` | GUDID identity resolution |

**⚠️ THERE IS NO `/device/denovo.json` ENDPOINT.** De Novo handling:
1. Query `classification.json` — De Novo-created regulations appear here; match on device name / regulation number.
2. If Stage 1 suggests a De Novo device and classification lookup is ambiguous, fall back to fetching the CDRH De Novo database page: `https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/denovo.cfm` (HTML, no JSON API) — deep-dive tier only.
3. A miss on De Novo lookup = `UNKNOWN` for that sub-item, never a negative. (Regression fixture #3 tests this.)

Search strategy: try exact product name → manufacturer name → aliases from Stage 1. Multiple candidate matches → surface top match in `product.identifiers` with a `match_confidence` field and let the user override in UI.

### 1.2 CMS Coverage API (api.coverage.cms.gov)

- **No API key** (removed Feb 8, 2024). Throttle: 10,000 req/s (irrelevant at our volume).
- **License token flow (MUST BUILD):** some endpoints require a bearer token obtained by calling the License Agreement endpoint (accepts AMA/ADA/AHA license agreements). Token valid **1 hour** — implement acquire-on-demand with in-memory cache and refresh-on-401.
- Swagger docs: `https://api.coverage.cms.gov/docs/swagger/index.html` — read this at build time and generate a typed client for: NCD search, LCD search, article search, by keyword and by ID.
- Search with procedure/condition keywords from Stage 1 (e.g. "transcatheter aortic valve", "continuous glucose monitor"), not brand names — MCD indexes services, not products.

### 1.3 Web search (deep-dive only)

Hard cap: 3 queries. Priority order: (1) `"<product>" reimbursement coding guide` (manufacturers publish these), (2) `"<product>" CPT code Medicare payment`, (3) `"<product>" clinical evidence OR payer policy`. Store URLs as citations.

### 1.4 Failure semantics (critical)

Every retrieval returns one of: `HIT`, `MISS` (searched successfully, nothing found), `RETRIEVAL_FAILURE` (timeout/5xx/network). These are distinct:
- `MISS` on FDA databases for a device claimed to be marketed → legitimate evidence (possibly `VERIFIED_NEGATIVE` or `UNKNOWN`).
- `RETRIEVAL_FAILURE` → excluded from scoring entirely; lowers `research_confidence`; never lowers maturity. If both openFDA and Coverage API fail → return `maturity_state: "NOT_SCORED"` with reason `INSUFFICIENT_DATA_RETRIEVED`. **Never emit numeric 0 for this case.** (Fixture #10.)

---

## 2. Model Pipeline

- Stage 1 model: cheapest available tier. `max_tokens: 500`. JSON-only output, validate against Stage-1 schema, one retry on invalid.
- Stage 3 model: strong tier. `max_tokens: 2000`. System prompt = `system_prompt_v2.md` verbatim, sent with **prompt caching enabled** (static prefix). Evidence bundle passed as a single user message: Stage-1 JSON + per-source evidence blocks, each tagged `<evidence source="openfda_510k" status="HIT">…</evidence>` etc. Truncate each evidence block to 1,500 tokens.
- Validate Stage-3 output against schema §4 (use strict JSON schema validation). On failure: one repair pass ("fix this JSON to match schema, change no values"), then hard error surfaced to UI.
- Prompt-injection: wrap all uploaded/fetched text in `<untrusted_data>` tags before it touches any model; system prompt already instructs to ignore instructions inside them.

## 3. Scoring Enforcement (belt-and-suspenders — do NOT trust the model alone)

Post-process Stage-3 JSON in code:
1. Recompute `maturity` = mean of `score` over pillars where `status ∈ {VERIFIED_POSITIVE, VERIFIED_NEGATIVE, MIXED}`. Pillars with `UNKNOWN | NA | RETRIEVAL_FAILURE` are dropped from numerator AND denominator. If model's number differs by >5 from recomputed, use recomputed.
2. If assessed pillars < 3 OR FDA-status pillar not assessed → force `maturity_state: "NOT_SCORED"`, null the numeric field.
3. `assessment_coverage_pct` = assessed pillars / 6 × 100 (recompute in code).
4. `research_confidence` clamp: ≤60 if any of {openFDA, Coverage API} was `RETRIEVAL_FAILURE`.
5. Risk flag never modifies maturity (assert: changing risk_flag input leaves maturity unchanged in tests).

## 4. Output JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["product", "scores", "pillars", "top_gaps", "next_steps", "disclaimer"],
  "properties": {
    "product": {
      "type": "object",
      "required": ["name", "manufacturer", "fda_status"],
      "properties": {
        "name": {"type": "string"},
        "manufacturer": {"type": "string"},
        "fda_status": {"type": "string"},
        "identifiers": {"type": "array", "items": {"type": "object", "properties": {
          "type": {"enum": ["510k","pma","denovo","product_code","udi","ncd","lcd","cpt","hcpcs"]},
          "value": {"type": "string"},
          "match_confidence": {"enum": ["exact","probable","uncertain"]}
        }}},
        "dev_stage": {"enum": ["concept","investigational","submission_pending","authorized_prelaunch","commercial","restricted_or_recalled"]}
      }
    },
    "scores": {
      "type": "object",
      "required": ["maturity_state", "assessment_coverage_pct", "research_confidence", "risk_flag", "stage_context"],
      "properties": {
        "maturity": {"type": ["integer","null"], "minimum": 0, "maximum": 100},
        "maturity_state": {"enum": ["SCORED","NOT_SCORED"]},
        "not_scored_reason": {"type": ["string","null"]},
        "assessment_coverage_pct": {"type": "integer"},
        "research_confidence": {"type": "integer"},
        "risk_flag": {"enum": ["LOW","MEDIUM","HIGH","CRITICAL"]},
        "stage_context": {"type": "string", "maxLength": 300}
      }
    },
    "pillars": {
      "type": "array", "minItems": 6, "maxItems": 6,
      "items": {"type": "object",
        "required": ["pillar","status","finding"],
        "properties": {
          "pillar": {"enum": ["fda_status","coding","coverage","payment","evidence","billing_workflow"]},
          "status": {"enum": ["VERIFIED_POSITIVE","VERIFIED_NEGATIVE","MIXED","UNKNOWN","NA","RETRIEVAL_FAILURE"]},
          "score": {"type": ["integer","null"]},
          "finding": {"type": "string", "maxLength": 200},
          "detail": {"type": "string", "maxLength": 800},
          "citation": {"type": ["string","null"]},
          "gap": {"type": ["string","null"]},
          "action": {"enum": ["PROCEED","FIX","INVESTIGATE",null]}
        }}
    },
    "top_gaps": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
    "next_steps": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
    "disclaimer": {"type": "string"}
  }
}
```

## 5. UI Spec (dashboard replaces prose report)

**Header band:** product name + FDA status chip · three gauges: Maturity (or "NOT SCORED — insufficient data" state, visually distinct, NEVER rendered as 0) · Assessment Coverage % · Research Confidence · Risk flag pill · one-line `stage_context`.

**Six pillar cards** in fixed order (FDA · Coding · Coverage · Payment · Evidence · Billing). Card row = status chip (✓ Verified / ⚠ Gap / ? Unknown / — N/A / ⛔ retrieval failed) + `finding`. Expand → `detail`, `citation` link, `gap`, `action`.

**Override affordance:** each pillar card and the product identity block have an Edit control. Edits (corrected product name, pasted known code, status override) → re-run only affected retrieval + one synthesis pass. Store overrides; render overridden items with a "user-edited" badge.

**Top Gaps / Next Steps** panels below cards. **Export:** JSON / CSV / print-styled page, all client-side.

**Copyright constraint:** do NOT display full CPT long descriptors (AMA-copyrighted, license required). Display code numbers + short paraphrase + link to official lookup. Gate descriptor display behind a `cpt_license` config flag (default false) pending AMA licensing decision.

**Streaming:** render pillar cards progressively — show retrieval status per source live ("Checking FDA 510(k) database… ✓ found K183282"), then fill cards when synthesis streams.

## 6. Regression Harness

- Runner: `npm run bench` (or `make bench`) executes every fixture in `benchmark_suite.json` through quick_scan, asserts expected bands and invariants, prints a table, exits nonzero on any failure.
- Run on every system-prompt or pipeline change. Store per-run cost + latency next to results.
- Invariant assertions (all fixtures): NOT_SCORED never serialized as 0; risk flag independence; unknown-drop recomputation matches.

## 7. Instrumentation

Per run, log: tier, tokens in/out per stage, cached vs uncached input tokens, per-source retrieval status + latency, wall-clock p50/p95, computed $ cost. Expose a `/metrics` debug view.

## 8. Task Order

1. Retrieval layer (§1) with failure semantics + unit tests. **AC:** LumineticsCore, a TAVR valve, and a Dexcom CGM each resolve to correct FDA records; De Novo path returns UNKNOWN (not negative) when ambiguous; simulated timeout produces RETRIEVAL_FAILURE.
2. Stage-1 extraction + schema validation. **AC:** benchmark uploads produce correct product identity ≥9/10.
3. Stage-3 synthesis with `system_prompt_v2.md` + code-side scoring enforcement (§3). **AC:** schema-valid output; recompute path exercised.
4. Regression harness (§6). **AC:** all 10 fixtures pass bands + invariants.
5. Dashboard UI (§5) with streaming + overrides. **AC:** NOT_SCORED renders as distinct state; CPT descriptors gated.
6. Instrumentation + tiers (§7). **AC:** quick_scan ≤$0.10 and <30s p50 on the benchmark set.

## 9. Explicitly Out of Scope (do not build)

- Billing implementation instructions or claim-generation features (fraud/abuse exposure).
- Full CPT descriptor display without the license flag.
- Coverage/payment "guarantees" language anywhere in UI copy — always "verify against official sources."
- Hard-coded payment rates or pathway facts (TCET/RAPID status, conversion factors) — these must come from retrieval, not constants.

## 10. Deferred / Diverged (as of 2026-07-23)

This section records where the built system differs from the body of this spec above. The spec body itself is unchanged by this addition — it still states the original design; this section states where implementation actually landed and why, so the two don't have to be reconciled by memory. See the outside-advisor status report for the fuller narrative each entry below is a summary of.

- **`deep_dive` tier: not built at all.** No such `analysis_type` exists. §1.3's web search (3-query cap, manufacturer reimbursement page / payer policy / clinical evidence queries) and §1.1 point 2's De Novo HTML-scrape fallback (explicitly scoped as deep-dive-only) were never attempted — everything built is `quick_scan` only. **Trigger to build:** a real need for evidence beyond openFDA + CMS Coverage (e.g. a device whose De Novo status is genuinely ambiguous in classification data, or a coding/payment question the PFS-only fee-schedule layer can't answer) becomes common enough to justify the added latency/cost budget §0 sets aside for it.
- **DMEPOS / standalone HCPCS Level II registry: deferred.** §1's coding/payment evidence source (built for PFS specifically, beyond what this spec originally scoped as a source at all) doesn't cover DME-billed devices — CMS's DMEPOS fee schedule page lacks PFS's clean per-quarter link structure. Fixture 4 (Dexcom G7) is carried as an explicit, documented known-gap in `benchmark_suite.json` because of this. **Trigger to build:** own investigation into a reliable way to locate DMEPOS's current release programmatically (not a rushed scraper against an undocumented page structure).
- **Per-pillar Edit control: not built.** §5 calls for an Edit control on "each pillar card **and** the product identity block." Only the product identity block has one (`ProductIdentityEdit.tsx`) — individual pillar cards have no override affordance, despite the backend's `OverrideRequest.target` being generic enough to accept one. **Trigger to build:** a real user need to correct a specific pillar's status/finding without re-running the whole identity, e.g. pasting a known CPT code the retrieval layer missed.
- **Streaming: polling, not streaming.** §5 describes progressive card-fill as synthesis streams. What's built: `retrieval_progress_json` is a field on the same 3-second-polled `AnalysisRun` row everything else uses — there's no dedicated streaming transport, and Stage 3's output arrives atomically when the call completes, never progressively. **Trigger to build:** perceived latency becomes a real usability complaint (Stage 3 alone now measures ~50s on the corrected model tier — see the tier-split entry in the status report — so a user watching a static screen for a minute is a real, not hypothetical, experience).
- **Pillar status glyphs: text badges instead.** §5 specifies `✓ Verified / ⚠ Gap / ? Unknown / — N/A / ⛔ retrieval failed`. The built UI uses colored text badges ("Verified", "Mixed evidence", "Not assessed", "N/A", "Retrieval failed") carrying the same distinctions with looser fidelity to the literal spec wording. **Trigger to build:** none identified — likely fine as-is; noted for completeness, not as a real gap.
- **`/metrics` path.** §7 says "Expose a `/metrics` debug view." It's namespaced at `/api/v1/metrics/quick-scan`, consistent with the rest of the API's versioning convention rather than a bare top-level route. **Trigger to build:** none — cosmetic, noted for completeness.
- **Retrieval parallelism: was diverged, now matches spec (2026-07-23).** §1 says "parallel HTTP." Until this date, only the openFDA-vs-CMS split ran concurrently — each group's own calls (7 openFDA endpoints; 3 CMS resource searches) ran sequentially in a plain loop, contrary to the spec's own wording. Fixed: both groups now dispatch their members via `asyncio.gather` (openFDA behind a small defensive semaphore; CMS unthrottled, per its documented 10,000 req/s limit). Retrieval itself now measures ~8s for a real fixture. **Residual gap from the spec's own §0/§6 latency target, not a retrieval problem:** Stage 3 synthesis alone now measures ~50s (78% of total wall-clock) once the strong model tier is genuinely in effect, so the suite's real p50 stays well over the spec's 30s quick_scan target regardless of retrieval speed — see the status report follow-up for the full measurement. That tension (a real "strong tier" Stage 3 model vs. a 30s p50 target) is unresolved and is a decision for the spec owner, not something addressed by this parallelization.
- **LCD/Article detail text: gated off by default, as specced, with a real consequence worth naming.** §1.2's license-token flow is built close to spec (acquire-on-demand, 1hr cache, refresh-on-401), correctly gated behind `cms_license_accepted` (default `false`) since flipping it constitutes accepting the AMA/ADA/AHA license text. This is spec-compliant, not drift — but the practical consequence is that in the default, out-of-the-box configuration, the coverage pillar works from LCD/Article **titles only**, never the actual coverage-criteria narrative, for the large majority of matched policies. **Trigger to revisit:** none needed structurally — this is a deliberate, correct product decision — but worth the spec owner knowing it's the default lived experience, not an edge case.
