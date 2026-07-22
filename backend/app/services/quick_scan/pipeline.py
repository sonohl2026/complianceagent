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
from app.services.evidence_retrieval.types import SourceEvidence
from app.services.llm.base import LLMProvider, LLMResult
from app.services.quick_scan.code_candidates import resolve_fee_schedule_evidence
from app.services.quick_scan.schemas import Stage1Extraction
from app.services.quick_scan.scoring_enforcement import enforce
from app.services.quick_scan.stage1_extraction import run_stage1
from app.services.quick_scan.stage3_synthesis import run_stage3
from app.services.storage.settings_store import load_runtime_settings


async def _add_fee_schedule_evidence(
    llm: LLMProvider, extraction_model: str, stage1: Stage1Extraction, bundle: EvidenceBundle,
) -> None:
    # Device -> candidate code -> verify against real PFS data (closes the
    # coding/payment pillar gap for devices with no dedicated NCD/LCD/
    # Article -- see code_candidates.py). Mutates bundle.sources in place so
    # Stage 3's evidence-bundle builder picks it up like any other source;
    # never blocks the run if the LLM/lookup step itself fails.
    try:
        evidence = await resolve_fee_schedule_evidence(llm, extraction_model, stage1, bundle)
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


def _make_usage_recorder(db: AsyncSession, analysis_run: AnalysisRun):
    # Mirrors app/services/analysis/pipeline.py's _stage_call token/cost
    # bookkeeping, applied via run_stage1/run_stage3's optional on_usage
    # callback instead of changing their return type (which test/bench
    # harness call sites rely on staying a bare parsed-model return).
    async def _record(stage_name: str, result: LLMResult) -> None:
        analysis_run.token_usage_json = {
            **analysis_run.token_usage_json,
            stage_name: {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
            },
        }
        if result.cost_usd is not None:
            analysis_run.cost_json = {**analysis_run.cost_json, stage_name: result.cost_usd}
        await db.commit()

    return _record


async def run_quick_scan(db: AsyncSession, analysis_run: AnalysisRun, llm: LLMProvider, model: str, source_text: str) -> None:
    settings = load_runtime_settings()
    extraction_model = settings.get("openrouter_extraction_model") or model
    synthesis_model = settings.get("openrouter_synthesis_model") or model

    record_usage = _make_usage_recorder(db, analysis_run)

    analysis_run.current_stage = "stage1_extraction"
    await db.commit()
    stage1 = await run_stage1(llm, extraction_model, source_text, on_usage=record_usage)

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
    await _add_fee_schedule_evidence(llm, extraction_model, stage1, bundle)

    analysis_run.current_stage = "stage3_synthesis"
    await db.commit()
    assessment = await run_stage3(llm, synthesis_model, stage1, bundle, on_usage=record_usage)

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
    synthesis_model = settings.get("openrouter_synthesis_model") or model
    extraction_model = settings.get("openrouter_extraction_model") or model

    record_usage = _make_usage_recorder(db, analysis_run)

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
    await _add_fee_schedule_evidence(llm, extraction_model, stage1, bundle)

    analysis_run.current_stage = "stage3_synthesis"
    await db.commit()
    assessment = await run_stage3(llm, synthesis_model, stage1, bundle, on_usage=record_usage)
    enforced = enforce(assessment, bundle)

    analysis_run.quick_scan_result_json = enforced.model_dump()
    analysis_run.retrieval_bundle_json = {
        "stage1": stage1.model_dump(),
        "sources": {name: _evidence_to_dict(e) for name, e in bundle.sources.items()},
    }
    analysis_run.revision += 1
    analysis_run.current_stage = "complete"
    await db.commit()
