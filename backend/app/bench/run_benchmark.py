"""Regression harness (v2 spec section 6): runs every fixture in
benchmark_suite.json through the real quick_scan pipeline, asserts expected
bands + the 4 global invariants, prints a results table, exits nonzero on
any failure.

Two modes:
  DRY_RUN_LLM=1  -- scripted LLM responses (fixture_inputs.py), real HTTP to
                    openFDA/CMS (both free/keyless, so no cost either way).
                    $0, seconds. Run this on every pipeline/prompt change.
  (default)      -- real LLM calls too. This is what actually signs off
                    Task 4's and Task 6's acceptance criteria (all 10
                    fixtures pass; <=$0.10 and <30s p50) -- run once to sign
                    off, not on every commit.

Fixture #10 (retrieval outage) is ALWAYS respx-mocked to 503 for both
openFDA and CMS, in both modes -- never a real outage.

KNOWN, DOCUMENTED LIMITATION (partially closed, not fully -- see below):
Stage 2 originally had NO source at all for CPT/HCPCS codes or PFS/OPPS/
DMEPOS payment rates. Since closed for PFS specifically: app/services/
fee_schedule/ ingests the real, current Physician Fee Schedule Relative
Value file (no queryable API exists for this -- CMS only publishes it as a
quarterly bulk zip) into Redis, and app/services/quick_scan/
code_candidates.py proposes candidate CPT/HCPCS codes (from an LLM's general
knowledge of the device category, plus any code-shaped text found in
already-fetched CMS coverage documents) and verifies every candidate
against that real data before trusting it -- an unverified guess is
silently dropped, never surfaced (same discipline as openFDA identity
verification). This measurably helps: e.g. fixture 5 ("rides existing
codes") and fixture 3 (LumineticsCore) now get real coding/payment pillar
evidence they structurally could not before.

Two things remain open, not attempted this pass:
- DMEPOS and a standalone HCPCS Level II registry were scoped for this same
  effort but deferred -- CMS's DMEPOS fee schedule page doesn't have PFS's
  clean, consistent per-quarter link structure, and reliably locating the
  current release needs its own investigation rather than a rushed scraper.
  This means DME-billed devices (fixture 8's insulin pump, fixture 4's CGM's
  supply codes) don't benefit from this fix yet -- PFS's own file does
  incidentally carry many HCPCS Level II codes with a "not payable under
  PFS" status, which is a real but partial signal, not equivalent to real
  DMEPOS rate data.
- Genuine LLM output non-determinism, RE-CHARACTERIZED after restoring the
  correct model tier split (see status report and its follow-up): the
  original diagnosis on the (then-silently-substituted) extraction-tier
  model found this isolated to fda_status specifically, with a code-side
  fix (scoring_enforcement.py::enforce_fda_status_from_verified_hit) closing
  that one case. Re-tested on the real strong-tier model (Sonnet) once the
  tier split was restored: 6 calls against one frozen, byte-identical
  evidence bundle (fixture 5's Vscan Air) flipped STATUS (not just score) on
  THREE pillars without a code-side backstop -- coding, payment, and
  evidence each swung between different assessed statuses (e.g. payment
  MIXED <-> VERIFIED_POSITIVE, evidence UNKNOWN <-> MIXED) purely from
  repeated calls at temperature=0 against identical input. This is Stage 3
  itself sampling differently on truly fixed input, not upstream
  evidence-shape variance as originally scoped -- broader and more serious
  than the fda_status-only case that already has a fix. Not fixed. REVISIT
  TRIGGER: any report of a maturity/pillar result changing between two runs
  of the identical device with no retrieval or code change in between.

ONE ADDITIONAL KNOWN ISSUE (found diagnosing fixture 4's real-run drop from
80 to 72 after the uploaded-document-as-evidence fix; see conversation
record for the full before/after pillar diagnosis):

- "Cost of uploading more text" hedging effect: restating a fact in the
  <uploaded_document> block that Stage 3 already had via Stage 1's
  intended_use JSON measurably increased Stage 3's conservatism on payment/
  coding/billing_workflow on the (then-silently-substituted) extraction-tier
  model -- a clean, zero-variance 9-point gap between "with upload" and
  "without." RE-TESTED on the real strong-tier model (Sonnet): does NOT
  reproduce as a distinct effect -- 6 samples per condition overlap
  completely (76.8 vs 77.2 mean maturity). Not because the underlying
  concern is resolved, but because it's swamped by the larger, general
  non-determinism above: on Sonnet, pillar status already varies run-to-run
  with NO upload-related change at all, so a subtler, upload-specific signal
  can't be cleanly isolated the way it could against the more consistent
  extraction-tier model's output. REVISIT TRIGGER: same as the
  non-determinism item above -- if that gets a code-side fix and result
  variance drops, re-run this specific before/after comparison to see if
  the hedging effect re-emerges as a distinguishable signal once the noise
  floor is lower.

(The CMS coverage LCD/Article/NCD qualifier mismatch previously listed here
-- e.g. "Implantable Continuous Glucose Monitors" matching fixture 4's
non-implantable Dexcom G7 -- is FIXED: see
app/services/evidence_retrieval/cms_coverage_client.py's qualifier-
contradiction guard.)

`_classify` below distinguishes a genuine regression from a still-
remaining, documented gap: KNOWN_GAP (thin real evidence or an explicitly
annotated fixture-level known_gap, no technical failure) vs FAIL (anything
else, including a RETRIEVAL_FAILURE-driven miss or an unannotated wrong
SCORED band).

BENCHMARK INTEGRITY FREEZE (effective 2026-07-23): no edit to any fixture's
`expected` block in benchmark_suite.json without (a) a written rationale
committed alongside the change (a `note` field on that fixture, matching
the existing convention -- see benchmark_suite.json's own `changelog`
section for the precedent) and (b) explicit owner sign-off before merge.
The suite exists to check the pipeline against a fixed target; letting it
drift to describe whatever the pipeline currently does, one individually
reasonable edit at a time, would quietly defeat that purpose without any
single change looking wrong in isolation.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
import respx

from app.bench.fixture_inputs import (
    DRY_RUN_STAGE1,
    FIXTURE_SOURCE_TEXT,
    dry_run_stage3_response,
)
from app.services.evidence_retrieval.orchestrator import run_evidence_retrieval
from app.services.quick_scan.code_candidates import resolve_fee_schedule_evidence
from app.services.quick_scan.schemas import Stage1Extraction
from app.services.quick_scan.scoring_enforcement import enforce
from app.services.quick_scan.stage1_extraction import run_stage1
from app.services.quick_scan.stage3_synthesis import run_stage3

_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class _DryRunLLM:
    """Scripted per-fixture responses keyed by schema_name -- lets one fake
    provider instance correctly answer both the Stage-1 and Stage-3 calls
    for a given fixture."""

    def __init__(self, fixture_id: int):
        self.fixture_id = fixture_id

    async def structured_completion(self, **kwargs):
        from app.services.llm.base import LLMResult

        if kwargs["schema_name"] == "quick_scan_stage1":
            content = DRY_RUN_STAGE1[self.fixture_id]
        elif kwargs["schema_name"] in ("quick_scan_code_candidates", "quick_scan_code_refinement"):
            content = {"candidate_codes": []}  # dry-run validates plumbing, not fee-schedule data quality
        else:
            content = dry_run_stage3_response(self.fixture_id)
        return LLMResult(
            content=content, raw_content="{}", requested_model=kwargs["model"],
            model_response_identifier="dry-run", prompt_tokens=0, completion_tokens=0,
            total_tokens=0, cost_usd=0.0, latency_ms=1, finish_reason="stop",
        )


def _load_fixtures() -> dict:
    path = Path(__file__).resolve().parents[2] / "benchmark_suite.json"
    return json.loads(path.read_text())


class _CostAccumulator:
    """Sums cost_usd across every LLM call made for one fixture -- Stage 1,
    Stage 3, and the (previously cost-invisible -- see status report §2/§6)
    fee-schedule candidate-proposal and refinement calls -- so the printed
    table can carry a real per-fixture $ figure. Spec §6: "Store per-run
    cost + latency next to results"; this harness previously only stored
    latency.

    Also tracks repair_fired/repair_rejected per call (added for the close-
    out's re-acceptance criteria: a repair-pass fire rate threshold and a
    zero-rejection requirement) -- the bench harness bypasses DB persistence
    entirely (see module docstring), so it's otherwise blind to these, the
    same way it was blind to cost before this same fix's pattern."""

    def __init__(self) -> None:
        self.total_usd = 0.0
        self.repair_fired = False
        self.repair_rejected = False

    async def record(self, stage_name: str, result) -> None:  # noqa: ARG002 - matches UsageCallback shape
        self.total_usd += result.cost_usd or 0.0
        if getattr(result, "schema_repair_attempted", False):
            self.repair_fired = True
        if getattr(result, "repair_rejected", False):
            self.repair_rejected = True


async def _run_pipeline_for_fixture(fixture_id: int, dry_run: bool, real_llm, model: str, synthesis_model: str):
    source_text = FIXTURE_SOURCE_TEXT[fixture_id]
    llm = _DryRunLLM(fixture_id) if dry_run else real_llm
    extraction_model = "dry-run" if dry_run else model
    cost = _CostAccumulator()
    stage1: Stage1Extraction = await run_stage1(llm, extraction_model, source_text, on_usage=cost.record)
    bundle = await run_evidence_retrieval(stage1)
    fee_schedule_evidence = await resolve_fee_schedule_evidence(llm, extraction_model, stage1, bundle, on_usage=cost.record)
    bundle.sources[fee_schedule_evidence.source] = fee_schedule_evidence
    assessment = await run_stage3(
        llm, "dry-run" if dry_run else synthesis_model, stage1, bundle, on_usage=cost.record, source_text=source_text,
    )
    return enforce(assessment, bundle), bundle, cost.total_usd, cost.repair_fired, cost.repair_rejected


async def _run_fixture_10(dry_run: bool, real_llm, model: str, synthesis_model: str):
    # Force a clean slate: fixtures 1-9 populate cms_coverage_client's
    # in-memory listing cache with real, successfully-fetched data (a
    # legitimate feature -- see that module's docstring). Left warm, it
    # would serve that still-valid cached data through this fixture's
    # simulated outage instead of genuinely hitting (and failing on) the
    # mocked endpoint, defeating the point of this specific regression test.
    from app.services.evidence_retrieval import cms_coverage_client

    cms_coverage_client._listing_cache.clear()
    cms_coverage_client._token_cache.clear()

    llm = _DryRunLLM(10) if dry_run else real_llm
    source_text = FIXTURE_SOURCE_TEXT[10]
    cost = _CostAccumulator()
    stage1 = await run_stage1(llm, "dry-run" if dry_run else model, source_text, on_usage=cost.record)

    # respx's global patch blocks ANY unregistered httpx call while active
    # (including real OpenRouter calls in non-dry-run mode) -- scope it to
    # ONLY the retrieval call, not the surrounding LLM stages.
    with respx.mock:
        respx.get(url__regex=r"https://api\.fda\.gov/device/.*").mock(side_effect=httpx.TimeoutException("simulated outage"))
        respx.get(url__regex=r"https://api\.coverage\.cms\.gov/v1/reports/.*").mock(side_effect=httpx.TimeoutException("simulated outage"))
        bundle = await run_evidence_retrieval(stage1)

    # Deliberately still resolved even during the simulated outage -- proves
    # force_not_scored overrides regardless of what other evidence exists,
    # matching how the real pipeline (pipeline.py) always runs this step
    # unconditionally.
    extraction_model = "dry-run" if dry_run else model
    fee_schedule_evidence = await resolve_fee_schedule_evidence(llm, extraction_model, stage1, bundle, on_usage=cost.record)
    bundle.sources[fee_schedule_evidence.source] = fee_schedule_evidence

    assessment = await run_stage3(
        llm, "dry-run" if dry_run else synthesis_model, stage1, bundle, on_usage=cost.record, source_text=source_text,
    )
    return enforce(assessment, bundle), bundle, cost.total_usd, cost.repair_fired, cost.repair_rejected


def _classify(result, bundle, failures: list[str], expected: dict | None = None) -> str:
    """PASS / KNOWN_GAP / FAIL. KNOWN_GAP covers two distinct shapes, both
    driven by genuinely thin evidence (no source technically failed) rather
    than a retrieval bug or prompt regression:
    (a) inferred: a NOT_SCORED verdict caused by INSUFFICIENT_DATA_RETRIEVED
        (fixtures 6-9 -- see module docstring).
    (b) explicit opt-in: a fixture whose `expected.known_gap` is set in
        benchmark_suite.json, and the ONLY failure is a maturity_band miss
        (fixture 4 -- the DMEPOS ingestion gap, see module docstring). This
        is never inferred from the score alone -- it requires the fixture's
        own annotation, so a genuinely wrong SCORED band elsewhere still
        FAILs loudly."""
    if not failures:
        return "PASS"
    if bundle is None:
        return "FAIL"
    no_technical_failure = all(e.status.value != "RETRIEVAL_FAILURE" for e in bundle.sources.values())
    only_state_failure = all(f.startswith("maturity_state:") or f.startswith("not_scored_reason:") for f in failures)
    if (
        only_state_failure
        and no_technical_failure
        and result is not None
        and result.scores.maturity_state == "NOT_SCORED"
        and result.scores.not_scored_reason == "INSUFFICIENT_DATA_RETRIEVED"
    ):
        return "KNOWN_GAP"
    only_band_failure = all(f.startswith("maturity_band:") for f in failures)
    if only_band_failure and no_technical_failure and expected is not None and expected.get("known_gap"):
        return "KNOWN_GAP"
    return "FAIL"


def _check_invariants(result, fixture: dict) -> list[str]:
    failures = []
    if result.scores.maturity_state == "NOT_SCORED" and result.scores.maturity is not None:
        failures.append("NOT_SCORED but maturity is not null")
    if result.disclaimer.strip() != (
        "Informational market-access analysis only; not legal, regulatory, or coding advice. "
        "Verify all codes and rates against official sources before billing."
    ):
        failures.append("disclaimer text does not match verbatim")
    return failures


def _check_expectations(result, expected: dict) -> list[str]:
    failures = []
    if "maturity_state" in expected and result.scores.maturity_state != expected["maturity_state"]:
        failures.append(f"maturity_state: expected {expected['maturity_state']}, got {result.scores.maturity_state}")
    if "maturity_band" in expected and result.scores.maturity_state == "SCORED":
        lo, hi = expected["maturity_band"]
        if result.scores.maturity is None or not (lo <= result.scores.maturity <= hi):
            failures.append(f"maturity_band: expected [{lo},{hi}], got {result.scores.maturity}")
    if "risk_flag_max" in expected:
        if _RISK_ORDER[result.scores.risk_flag] > _RISK_ORDER[expected["risk_flag_max"]]:
            failures.append(f"risk_flag_max: expected <= {expected['risk_flag_max']}, got {result.scores.risk_flag}")
    if "risk_flag_min" in expected:
        if _RISK_ORDER[result.scores.risk_flag] < _RISK_ORDER[expected["risk_flag_min"]]:
            failures.append(f"risk_flag_min: expected >= {expected['risk_flag_min']}, got {result.scores.risk_flag}")
    if "not_scored_reason" in expected and result.scores.not_scored_reason != expected["not_scored_reason"]:
        failures.append(f"not_scored_reason: expected {expected['not_scored_reason']}, got {result.scores.not_scored_reason}")
    if "research_confidence_max" in expected and result.scores.research_confidence > expected["research_confidence_max"]:
        failures.append(f"research_confidence_max: expected <= {expected['research_confidence_max']}, got {result.scores.research_confidence}")
    return failures


async def main() -> int:
    dry_run = os.environ.get("DRY_RUN_LLM") == "1"
    suite = _load_fixtures()

    real_llm = None
    model = synthesis_model = ""
    if not dry_run:
        from app.services.llm.openrouter_provider import OpenRouterProvider
        from app.services.storage.settings_store import load_runtime_settings

        settings = load_runtime_settings()
        real_llm = OpenRouterProvider(
            api_key=settings.get("openrouter_api_key"),
            prompt_caching=settings.get("openrouter_prompt_caching", True),
        )
        model = settings.get("openrouter_extraction_model") or settings.get("openrouter_model")
        synthesis_model = settings.get("openrouter_synthesis_model") or settings.get("openrouter_model")

        # Fee-schedule (coding/payment pillar) evidence depends on Redis
        # having PFS data loaded -- ensure it's there before any fixture
        # runs rather than silently scoring against an empty lookup table.
        from app.services.fee_schedule import refresh as fee_schedule_refresh

        async with httpx.AsyncClient() as client:
            await fee_schedule_refresh.ensure_pfs_populated(client)

    rows = []
    any_failed = False
    for fixture in suite["fixtures"]:
        fixture_id = fixture["id"]
        started = time.monotonic()
        bundle = None
        cost_usd = None
        repair_fired = False
        repair_rejected = False
        try:
            if fixture_id == 10:
                result, bundle, cost_usd, repair_fired, repair_rejected = await _run_fixture_10(dry_run, real_llm, model, synthesis_model)
            else:
                result, bundle, cost_usd, repair_fired, repair_rejected = await _run_pipeline_for_fixture(fixture_id, dry_run, real_llm, model, synthesis_model)
            elapsed = time.monotonic() - started
            failures = _check_expectations(result, fixture["expected"]) + _check_invariants(result, fixture)
        except Exception as exc:  # noqa: BLE001 - a fixture-level crash is itself a failure to report, not to propagate
            elapsed = time.monotonic() - started
            failures = [f"CRASHED: {exc}"]
            result = None

        status = _classify(result, bundle, failures, fixture.get("expected"))
        any_failed = any_failed or status == "FAIL"
        rows.append({
            "id": fixture_id, "name": fixture["name"], "status": status,
            "elapsed_s": round(elapsed, 2), "failures": failures,
            "maturity": result.scores.maturity if result else None,
            "maturity_state": result.scores.maturity_state if result else "CRASHED",
            "cost_usd": round(cost_usd, 4) if cost_usd is not None else None,
            "repair_fired": repair_fired,
            "repair_rejected": repair_rejected,
        })

    print(f"\n{'ID':<4}{'Name':<45}{'State':<12}{'Maturity':<10}{'Time':<8}{'Cost':<9}{'Repair':<8}{'Result'}")
    print("-" * 118)
    total_cost = 0.0
    for row in rows:
        cost_str = f"${row['cost_usd']:.4f}" if row["cost_usd"] is not None else "—"
        total_cost += row["cost_usd"] or 0.0
        repair_str = ("REJECTED" if row["repair_rejected"] else "fired") if row["repair_fired"] else "—"
        print(
            f"{row['id']:<4}{row['name'][:43]:<45}{row['maturity_state']:<12}{str(row['maturity']):<10}"
            f"{row['elapsed_s']:<8}{cost_str:<9}{repair_str:<8}{row['status']}"
        )
        for failure in row["failures"]:
            print(f"      -> {failure}")

    n_passed = sum(1 for r in rows if r["status"] == "PASS")
    n_known_gap = sum(1 for r in rows if r["status"] == "KNOWN_GAP")
    n_failed = sum(1 for r in rows if r["status"] == "FAIL")
    n_repaired = sum(1 for r in rows if r["repair_fired"])
    n_rejected = sum(1 for r in rows if r["repair_rejected"])
    print(
        f"\n{n_passed}/{len(rows)} fixtures passed outright, {n_known_gap} known-gap "
        f"(documented Stage-2 coding/coverage/payment data limitation, see module docstring), "
        f"{n_failed} failed. Total cost: ${total_cost:.4f}. Repair fired: {n_repaired}/{len(rows)} "
        f"({100 * n_repaired / len(rows):.0f}%), rejected: {n_rejected}. "
        f"Mode: {'DRY_RUN_LLM' if dry_run else 'REAL (costed)'}"
    )
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
