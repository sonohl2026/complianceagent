# Prompt Design

## Hierarchy

A model call is composed, in order, from:

1. Immutable security and source-handling instructions (untrusted-content boundaries,
   prohibition on following embedded instructions) — owned by application code, not editable
   through the Prompt Management UI.
2. The active version of the compliance master system prompt — a `PromptVersion` row, seeded on
   first use from `prompts/master_system_prompt.md` as version 1
   (`app/services/analysis/prompts_service.py::get_active_master_prompt`). This remains
   controlling if a module prompt conflicts with it.
3. The module-specific instruction for the current pipeline stage (`prompts/*_analysis.md`,
   `prompts/product_fact_extraction.md`, `prompts/claim_extraction.md`, `prompts/synthesis.md`,
   `prompts/citation_audit.md`).
4. Structured project facts (verified facts, prior stage outputs relevant to this stage).
5. Retrieved evidence, each chunk wrapped in explicit untrusted-content boundaries and tagged
   with its citation ID, collection type (company/authority), and authority level.
6. The output JSON schema for this stage, with `additionalProperties: false` and explicit
   `required` fields.

Untrusted source text (step 5) is never concatenated into the system-message region — only into a
clearly delimited user-message section, per `docs/security.md`.

## Versioning

Prompts are stored as versioned rows, not hardcoded (`prompt_versions` table). Every
`AnalysisRun` records `system_prompt_version_id`, the exact requested `analysis_model`, and the
actual `model_response_identifier` OpenRouter returned, for reproducibility. **Not yet
implemented**: the Prompt Management screen itself (view/edit/clone/diff/rollback/test-run/export)
— today there's exactly one active version per name, created automatically, with no UI to edit or
roll one back. That's a Milestone 7 UI item; the versioning data model it needs already exists.

## Schemas and citation audit

Every stage's output is validated against a strict Pydantic/JSON schema (via OpenRouter/OpenAI
structured-outputs strict mode) before being trusted; one automatic repair retry is attempted on
validation failure (re-prompting with the exact validation error), then the run is marked failed
rather than accepting malformed output (`app/services/llm/openrouter_provider.py`). The final
`citation_audit` stage (`prompts/citation_audit.md`) re-checks every finding from earlier stages
for citation presence and correct company-vs-authority attribution; findings that fail are
downgraded to the status the model specifies (e.g. an "evidence required" state), never silently
left as an unsupported high-confidence finding. **Known gap**: this stage does not yet
byte-for-byte verify that a citation's quoted text is verbatim present in the source chunk — it
validates citation coverage and role, not quote fidelity.
