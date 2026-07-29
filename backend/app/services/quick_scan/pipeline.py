"""quick_scan pipeline orchestrator (v2 spec §0): Stage 1 -> retrieval ->
Stage 3 -> code-side scoring enforcement -> persistence. Mirrors the
cooperative-progress-commit pattern of the old pipeline's set_stage()
(app/services/analysis/pipeline.py) but writes retrieval_progress_json
instead of a single current_stage string, since retrieval has several
sources resolving independently rather than one linear stage sequence.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisRun
from app.services.evidence_retrieval.orchestrator import EvidenceBundle, run_evidence_retrieval
from app.services.evidence_retrieval.types import RetrievalStatus, SourceEvidence
from app.services.llm.base import LLMProvider, LLMResult
from app.services.quick_scan.code_candidates import resolve_fee_schedule_evidence
from app.services.quick_scan.model_tier import warn_if_tier_split_inactive
from app.services.quick_scan.schemas import Stage1Extraction
from app.services.quick_scan.scoring_enforcement import enforce
from app.services.quick_scan.stage1_extraction import UsageCallback, run_stage1
from app.services.quick_scan.stage3_synthesis import run_stage3
from app.services.storage.settings_store import load_runtime_settings
from app.services.web_search.brave_client import BraveSearchError, WebSearchResult, search as brave_search

MAX_MERGED_SOURCE_CHARS = 8000 * 4  # matches stage1_extraction.py's own cap; this is a pre-truncation courtesy, not a second cap


def fair_share_merge_sources(texts: list[str], max_chars: int) -> str:
    """Multi-file/link merge for Stage 1's ~8k-token cap: naive concatenation
    truncates from the end, so a single large source can silently push every
    other source out entirely. Each source gets an equal share of the
    budget up front instead, so every attached document/link is represented
    in what Stage 1 actually sees. Shared by the API layer (quick_scans.py)
    and the worker (quick_scan_tasks.py's source-check task), which is why
    this lives here rather than in either of those."""
    if not texts:
        return ""
    per_source_budget = max(max_chars // len(texts), 1)
    return "\n\n---\n\n".join(text[:per_source_budget] for text in texts)


async def _add_fee_schedule_evidence(
    llm: LLMProvider, extraction_model: str, stage1: Stage1Extraction, bundle: EvidenceBundle,
    on_usage: UsageCallback,
) -> None:
    # Device -> candidate code -> verify against real PFS data (closes the
    # coding/payment pillar gap for devices with no dedicated NCD/LCD/
    # Article -- see code_candidates.py). Mutates bundle.sources in place so
    # Stage 3's evidence-bundle builder picks it up like any other source;
    # never blocks the run if the LLM/lookup step itself fails.
    #
    # on_usage is threaded through so its (up to 2) LLM calls are never
    # cost-invisible -- previously this was the one call path in the whole
    # pipeline whose tokens/cost never reached token_usage_json/cost_json/
    # /metrics at all (see status report, section 2/6).
    try:
        evidence = await resolve_fee_schedule_evidence(llm, extraction_model, stage1, bundle, on_usage=on_usage)
    except Exception:  # noqa: BLE001 - a candidate-code failure must never take down quick_scan
        return
    bundle.sources[evidence.source] = evidence


def _evidence_to_dict(evidence: SourceEvidence) -> dict:
    return {
        "status": evidence.status.value,
        "latency_ms": evidence.latency_ms,
        "data": evidence.data,
        "error": evidence.error,
        "match_confidence": evidence.match_confidence,
    }


def make_usage_recorder(db: AsyncSession, analysis_run: AnalysisRun):
    # Mirrors app/services/analysis/pipeline.py's _stage_call token/cost
    # bookkeeping, applied via run_stage1/run_stage3's optional on_usage
    # callback instead of changing their return type (which test/bench
    # harness call sites rely on staying a bare parsed-model return).
    async def _record(stage_name: str, result: LLMResult) -> None:
        # cached_tokens/cache_write_tokens were previously read off the raw
        # OpenRouter response (openrouter_provider.py::_to_llm_result) into
        # LLMResult.metadata and then discarded here -- spec §7 asks for
        # cached-vs-uncached tracking explicitly; this is the fix.
        analysis_run.token_usage_json = {
            **analysis_run.token_usage_json,
            stage_name: {
                # Which model actually served this stage -- previously not
                # recorded anywhere, meaning there was no way to confirm from
                # the data itself whether the tier split (model_tier.py) was
                # really in effect for a given run, only from Settings state
                # at query time. model_response_identifier is what the
                # provider actually returned/routed to; requested_model is
                # what was asked for -- prefer the former, it's more precise.
                "model": result.model_response_identifier or result.requested_model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
                "cached_tokens": result.metadata.get("cached_tokens"),
                "cache_write_tokens": result.metadata.get("cache_write_tokens"),
                # Previously not recorded anywhere -- a repair pass firing
                # was invisible in every persisted record, which is exactly
                # why a value-alteration incident could go unaudited (see
                # the close-out report's blast-radius audit). Now first-
                # class per-run/per-stage fields, surfaced in /metrics too.
                "repair_fired": result.schema_repair_attempted,
                "repair_rejected": result.repair_rejected,
            },
        }
        if result.cost_usd is not None:
            analysis_run.cost_json = {**analysis_run.cost_json, stage_name: result.cost_usd}
        await db.commit()

    return _record


def _apply_name_hint(stage1: Stage1Extraction, product_name_hint: str) -> Stage1Extraction:
    """MVP lockdown Step 2's 'name + documents' case: the typed name seeds
    identity, documents feed evidence -- so the typed name wins over whatever
    Stage 1 guessed from the material, but Stage 1's own guess is kept as an
    alias rather than discarded."""
    hint = product_name_hint.strip()
    if not hint or hint.lower() == stage1.product_name.strip().lower():
        return stage1
    aliases = stage1.aliases
    if stage1.product_name and stage1.product_name not in aliases:
        aliases = [stage1.product_name, *aliases]
    search_terms = [hint, *[t for t in stage1.candidate_search_terms if t != hint]]
    return stage1.model_copy(update={"product_name": hint, "aliases": aliases, "candidate_search_terms": search_terms})


async def run_quick_scan(
    db: AsyncSession, analysis_run: AnalysisRun, llm: LLMProvider, model: str, source_text: str,
    product_name_hint: str | None = None,
) -> None:
    settings = load_runtime_settings()
    warn_if_tier_split_inactive(settings, context="quick_scan run")
    extraction_model = settings.get("openrouter_extraction_model") or model
    synthesis_model = settings.get("openrouter_synthesis_model") or model

    record_usage = make_usage_recorder(db, analysis_run)

    analysis_run.current_stage = "stage1_extraction"
    await db.commit()
    stage1 = await run_stage1(llm, extraction_model, source_text, on_usage=record_usage)
    if product_name_hint:
        stage1 = _apply_name_hint(stage1, product_name_hint)

    analysis_run.current_stage = "retrieval"
    analysis_run.retrieval_progress_json = {}
    await db.commit()

    async def on_progress(source_name: str, evidence: SourceEvidence) -> None:
        analysis_run.retrieval_progress_json = {
            **analysis_run.retrieval_progress_json,
            source_name: _evidence_to_dict(evidence),
        }
        await db.commit()

    bundle = await run_evidence_retrieval(stage1, on_progress=on_progress)
    await _add_fee_schedule_evidence(llm, extraction_model, stage1, bundle, record_usage)

    analysis_run.current_stage = "stage3_synthesis"
    await db.commit()
    assessment = await run_stage3(llm, synthesis_model, stage1, bundle, on_usage=record_usage, source_text=source_text)

    enforced = enforce(assessment, bundle)

    analysis_run.quick_scan_result_json = enforced.model_dump()
    analysis_run.retrieval_bundle_json = {
        "stage1": stage1.model_dump(),
        "sources": {name: _evidence_to_dict(e) for name, e in bundle.sources.items()},
    }
    analysis_run.current_stage = "complete"
    await db.commit()


def _apply_product_overrides(stage1: Stage1Extraction, overrides: dict) -> Stage1Extraction:
    updates = {}
    for key, override in overrides.items():
        if not key.startswith("product."):
            continue
        field = key.removeprefix("product.")
        if field in Stage1Extraction.model_fields:
            updates[field] = override["value"]
    return stage1.model_copy(update=updates) if updates else stage1


async def run_quick_scan_override(db: AsyncSession, analysis_run: AnalysisRun, llm: LLMProvider, model: str) -> None:
    """Re-runs only retrieval + synthesis (spec §5: "re-run only affected
    retrieval + one synthesis pass") -- Stage 1 itself isn't re-run since the
    user's override IS the corrected identity; it's applied directly to the
    previously-extracted Stage1Extraction instead."""
    settings = load_runtime_settings()
    warn_if_tier_split_inactive(settings, context="quick_scan override run")
    synthesis_model = settings.get("openrouter_synthesis_model") or model
    extraction_model = settings.get("openrouter_extraction_model") or model

    record_usage = make_usage_recorder(db, analysis_run)

    prior_stage1_data = analysis_run.retrieval_bundle_json.get("stage1", {})
    stage1 = Stage1Extraction.model_validate(prior_stage1_data)
    stage1 = _apply_product_overrides(stage1, analysis_run.overrides_json)

    analysis_run.current_stage = "retrieval"
    analysis_run.retrieval_progress_json = {}
    await db.commit()

    async def on_progress(source_name: str, evidence: SourceEvidence) -> None:
        analysis_run.retrieval_progress_json = {
            **analysis_run.retrieval_progress_json,
            source_name: _evidence_to_dict(evidence),
        }
        await db.commit()

    bundle = await run_evidence_retrieval(stage1, on_progress=on_progress)
    await _add_fee_schedule_evidence(llm, extraction_model, stage1, bundle, record_usage)

    analysis_run.current_stage = "stage3_synthesis"
    await db.commit()
    source_text = analysis_run.input_snapshot_json.get("source_text", "")
    assessment = await run_stage3(llm, synthesis_model, stage1, bundle, on_usage=record_usage, source_text=source_text)
    enforced = enforce(assessment, bundle)

    analysis_run.quick_scan_result_json = enforced.model_dump()
    analysis_run.retrieval_bundle_json = {
        "stage1": stage1.model_dump(),
        "sources": {name: _evidence_to_dict(e) for name, e in bundle.sources.items()},
    }
    analysis_run.revision += 1
    analysis_run.current_stage = "complete"
    await db.commit()


def _seed_stage1_from_name(product_name: str) -> Stage1Extraction:
    """Name-only submission (MVP lockdown Step 3): the typed name IS the
    product identity -- there's no material for Stage 1 to read, so this
    skips that LLM call entirely rather than feeding it an empty/near-empty
    prompt, and seeds just enough of a Stage1Extraction shape for retrieval
    to search on."""
    return Stage1Extraction(
        product_name=product_name,
        manufacturer="",
        aliases=[],
        intended_use="",
        technology_type="",
        dev_stage_guess="unknown",
        candidate_search_terms=[product_name],
    )


async def _find_candidate_site(product_name: str) -> WebSearchResult | None:
    """Web-search fallback for a name-only submission that openFDA/CMS
    retrieval couldn't resolve at all. Only ever reached on a genuine zero-
    hit -- never a general evidence-gathering search, and capped at one
    query returning one candidate (the top result), matching the narrow
    "propose a site, let the user confirm it" ask this closes, not a
    broader research capability."""
    settings = load_runtime_settings()
    api_key = settings.get("brave_search_api_key")
    if not api_key:
        return None
    try:
        results = await brave_search(product_name, api_key, count=1)
    except BraveSearchError:
        return None  # a search-provider failure must never take down the run
    return results[0] if results else None


async def run_quick_scan_identity_resolution(
    db: AsyncSession, analysis_run: AnalysisRun, llm: LLMProvider, model: str, product_name: str,
) -> bool:
    """Name-only submission's first half: seed identity from the typed name,
    run retrieval only, then stop for user confirmation instead of
    continuing straight to Stage 3 -- the resolved identity may be wrong
    (wrong device, ambiguous name) and Stage 3 is the expensive, hard-to-undo
    step. Returns whether retrieval found anything at all under the name.

    On a zero-hit, also tries one web search for a candidate site (see
    _find_candidate_site) so the confirmation screen can offer "is this the
    right site?" instead of a dead end -- persisted into
    retrieval_bundle_json alongside stage1/sources so the confirm-site
    endpoint and the frontend can both read it back."""
    settings = load_runtime_settings()
    extraction_model = settings.get("openrouter_extraction_model") or model

    record_usage = make_usage_recorder(db, analysis_run)
    stage1 = _seed_stage1_from_name(product_name)

    analysis_run.current_stage = "retrieval"
    analysis_run.retrieval_progress_json = {}
    await db.commit()

    async def on_progress(source_name: str, evidence: SourceEvidence) -> None:
        analysis_run.retrieval_progress_json = {
            **analysis_run.retrieval_progress_json,
            source_name: _evidence_to_dict(evidence),
        }
        await db.commit()

    bundle = await run_evidence_retrieval(stage1, on_progress=on_progress)
    await _add_fee_schedule_evidence(llm, extraction_model, stage1, bundle, record_usage)

    identity_found = any(e.status == RetrievalStatus.HIT for e in bundle.sources.values())

    retrieval_bundle_json = {
        "stage1": stage1.model_dump(),
        "sources": {name: _evidence_to_dict(e) for name, e in bundle.sources.items()},
    }
    if not identity_found:
        candidate = await _find_candidate_site(product_name)
        if candidate is not None:
            retrieval_bundle_json["candidate_site"] = {
                "title": candidate.title, "url": candidate.url, "snippet": candidate.snippet,
            }

    analysis_run.retrieval_bundle_json = retrieval_bundle_json
    analysis_run.current_stage = "awaiting_confirmation"
    await db.commit()
    return identity_found
