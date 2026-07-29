"""Device -> candidate billing code -> verify against real fee-schedule data
(closes the coding/payment pillar gap for devices with no dedicated NCD/LCD/
Article -- see the plan doc's point (b)/(c)). There is no dataset that maps
a device to its code, so this flips the direction: propose candidates, then
verify every one against real, current PFS data before trusting any of them
-- mirrors the same verify-before-trust pattern already proven for openFDA
identity matching (a wrong/unverified match is worse than an honest miss).

Candidates come from three sources, all subject to the SAME verification
step below -- none of them is trusted on its own:
1. Code-shaped tokens found in already-fetched CMS coverage documents
   (extract_code_mentions/_sourced_hints_from_bundle) -- highest-confidence,
   since they come from a real coverage document, not a guess.
2. propose_llm_candidates -- an LLM guessing from its own memorized
   knowledge of how similar device categories are typically billed.
3. Real-data pre-filter + LLM refinement (description_search.py +
   refine_candidates_from_descriptions) -- added after finding that (2)
   alone is unreliable for specific/newer codes: asked directly and
   unambiguously, the model confidently gave a WRONG definition for a real,
   current CPT code rather than admitting it didn't know. Since the code's
   real, current description is sitting in the PFS registry, this
   mechanically pre-filters that registry (loose, recall-oriented -- see
   description_search.py's own docstring for why a single mechanical
   threshold can't be both tight and complete against CMS's abbreviation
   style) down to a small, real, grounded shortlist, then asks the LLM to
   make the actual precision judgment against real candidates instead of
   recalling one from memory -- recognition, not recall.
"""

import re

from app.services.analysis.prompts_service import load_module_prompt
from app.services.evidence_retrieval.orchestrator import EvidenceBundle
from app.services.evidence_retrieval.types import RetrievalStatus, SourceEvidence
from app.services.fee_schedule import cache, description_search
from app.services.fee_schedule.code_format import CodeFormat, classify_code_format
from app.services.fee_schedule.types import FeeScheduleEntry
from app.services.llm.base import LLMProvider
from app.services.quick_scan.schemas import CandidateCodesResponse, Stage1Extraction
from app.services.quick_scan.stage1_extraction import UsageCallback, wrap_untrusted_data

_MAX_OUTPUT_TOKENS = 1500  # a longer candidate list (each ~6-char code) can exceed a Stage-1-sized budget

# Remote Physiologic Monitoring (RPM) is a small, fixed, CMS-defined code
# family that is deliberately parameter-agnostic -- it applies to any
# FDA-regulated device that digitally transmits physiologic data for
# ongoing clinical monitoring/management, regardless of which specific
# parameter is measured (see quick_scan_code_relevance_gate.md's own
# reasoning about this). Neither the LLM memory-guess step nor the
# mechanical description-index prefilter reliably surfaces this family:
# confirmed empirically against a real auscultation-device query, the
# prefilter ranked 99453/99445/99454 at #695+ and 99457/99458/99470 at
# #3926+ out of 5,444 codes with at least one coincidental keyword
# overlap (short abbreviated tokens like "mntr" collide with thousands of
# unrelated codes), and the memory-guess step recalled some of these codes
# but not others with no consistent pattern. So this family is included
# directly as an always-considered candidate set, subject to the exact
# same real-data verification and relevance gate as every other candidate
# -- this does not assume RPM applies to any given device; the gate still
# judges it per device, same as everything else.
_KNOWN_GENERIC_CANDIDATE_FAMILIES: tuple[str, ...] = (
    "99453", "99445", "99454", "99457", "99458", "99470", "99091",
)


def extract_code_mentions(text: str) -> list[str]:
    """Scans real, already-retrieved CMS document text for CPT/HCPCS-shaped
    tokens -- these are higher-confidence than an LLM guess since they come
    from an actual coverage document, but still go through the same
    verification step (a code-shaped token in free text isn't necessarily
    the code the document is really about)."""
    if not text:
        return []
    tokens = re.findall(r"\b\d{5}\b|\b\d{4}[A-Z]\b|\b[A-Z]\d{4}\b", text.upper())
    return [t for t in tokens if classify_code_format(t) != CodeFormat.UNKNOWN]


def _sourced_hints_from_bundle(bundle: EvidenceBundle) -> list[str]:
    hints: list[str] = []
    for source_name, evidence in bundle.sources.items():
        if not source_name.endswith("_detail") or evidence.status != RetrievalStatus.HIT:
            continue
        document = (evidence.data or {}).get("document", {})
        for value in document.values():
            if isinstance(value, str):
                hints.extend(extract_code_mentions(value))
    return hints


async def propose_llm_candidates(
    llm: LLMProvider, model: str, stage1: Stage1Extraction, sourced_hints: list[str],
    on_usage: UsageCallback | None = None,
) -> list[str]:
    module_prompt = load_module_prompt("quick_scan_code_candidates")
    hints_text = f"\nCode-shaped mentions already found in retrieved coverage documents: {sourced_hints}" if sourced_hints else ""
    user_message = wrap_untrusted_data(
        f"technology_type: {stage1.technology_type}\nintended_use: {stage1.intended_use}{hints_text}"
    )
    schema = CandidateCodesResponse.model_json_schema()
    result = await llm.structured_completion(
        system_prompt=module_prompt, messages=[{"role": "user", "content": user_message}],
        schema=schema, schema_name="quick_scan_code_candidates", model=model,
        temperature=0, max_tokens=_MAX_OUTPUT_TOKENS,
    )
    if on_usage is not None:
        await on_usage("fee_schedule_llm_candidates", result)
    return CandidateCodesResponse.model_validate(result.content).candidate_codes


async def refine_candidates_from_descriptions(
    llm: LLMProvider, model: str, stage1: Stage1Extraction, candidates: dict[str, str],
    on_usage: UsageCallback | None = None,
) -> list[str]:
    """Shows the model REAL (code, real-current-description) pairs pulled
    from the PFS registry and asks it to pick which, if any, match the
    device's distinguishing characteristic -- recognition against grounded
    data, not recall from memory. The raw descriptions are used here ONLY as
    input to this internal LLM call; its output schema is code numbers
    only (CandidateCodesResponse), so the descriptor text structurally
    cannot be carried forward into anything Stage 3 or the UI ever sees."""
    if not candidates:
        return []
    module_prompt = load_module_prompt("quick_scan_code_refinement")
    candidates_text = "\n".join(f"{code}: {desc}" for code, desc in candidates.items())
    user_message = wrap_untrusted_data(
        f"technology_type: {stage1.technology_type}\nintended_use: {stage1.intended_use}\n\n"
        f"Candidate codes:\n{candidates_text}"
    )
    schema = CandidateCodesResponse.model_json_schema()
    result = await llm.structured_completion(
        system_prompt=module_prompt, messages=[{"role": "user", "content": user_message}],
        schema=schema, schema_name="quick_scan_code_refinement", model=model,
        temperature=0, max_tokens=_MAX_OUTPUT_TOKENS,
    )
    if on_usage is not None:
        await on_usage("fee_schedule_code_refinement", result)
    picked = CandidateCodesResponse.model_validate(result.content).candidate_codes
    # Never trust the model to only echo codes it was actually shown.
    return [code for code in picked if code in candidates]


async def verify_candidates(candidates: list[str], table: str = "pfs") -> list[FeeScheduleEntry]:
    verified = []
    seen = set()
    for code in candidates:
        code = code.strip().upper()
        if not code or code in seen or classify_code_format(code) == CodeFormat.UNKNOWN:
            continue
        seen.add(code)
        entry = await cache.lookup(table, code)
        if entry is not None and entry.active:
            verified.append(entry)
    return verified


async def gate_candidates_by_relevance(
    llm: LLMProvider, model: str, stage1: Stage1Extraction,
    verified: list[FeeScheduleEntry], table: str = "pfs",
    on_usage: UsageCallback | None = None,
) -> list[FeeScheduleEntry]:
    """Being a real, active, priced code doesn't mean it's the RIGHT code for
    this device -- a candidate can reach here via a memory-guess free-
    association or a coincidental keyword collision (both observed in
    production: ECG codes proposed for an auscultation device, RPM codes
    matched via 'min'/'monitor' vowel-stripped substring overlap in
    description_search.py). Reuses the same internal raw-description index
    and recognition-not-recall pattern already proven in
    refine_candidates_from_descriptions -- NOT a second recall-from-memory
    check, which is the exact failure mode this closes."""
    if not verified:
        return verified
    description_index = await cache.get_description_index(table)
    groundable = {e.code: description_index[e.code] for e in verified if e.code in description_index}
    if not groundable:
        return verified  # no grounded data available at all for this table -- fail open rather than blind-drop

    module_prompt = load_module_prompt("quick_scan_code_relevance_gate")
    candidates_text = "\n".join(f"{code}: {desc}" for code, desc in groundable.items())
    user_message = wrap_untrusted_data(
        f"technology_type: {stage1.technology_type}\nintended_use: {stage1.intended_use}\n\n"
        f"Candidate codes (already confirmed real/active/priced -- your job is relevance only):\n{candidates_text}"
    )
    schema = CandidateCodesResponse.model_json_schema()
    result = await llm.structured_completion(
        system_prompt=module_prompt, messages=[{"role": "user", "content": user_message}],
        schema=schema, schema_name="quick_scan_code_relevance_gate", model=model,
        temperature=0, max_tokens=_MAX_OUTPUT_TOKENS,
    )
    if on_usage is not None:
        await on_usage("fee_schedule_relevance_gate", result)
    picked = set(CandidateCodesResponse.model_validate(result.content).candidate_codes) & set(groundable)
    # Codes without a groundable description skip the gate entirely (no data
    # to judge relevance against) -- kept, same fail-open reasoning as above.
    return [e for e in verified if e.code in picked or e.code not in groundable]


def _entry_to_evidence_dict(entry: FeeScheduleEntry) -> dict:
    return {
        "code": entry.code, "code_format": entry.code_format.value, "payment_system": entry.payment_system,
        "rate_usd": entry.rate_usd, "status_code": entry.status_code,
        # description is already None for AMA-licensed (CPT) formats -- see
        # code_format.py / pfs_client.py, enforced at parse time.
        "description": entry.description,
    }


async def _description_matched_candidates(
    llm: LLMProvider, model: str, stage1: Stage1Extraction, table: str,
    on_usage: UsageCallback | None = None,
) -> list[str]:
    description_index = await cache.get_description_index(table)
    if not description_index:
        return []
    query = f"{stage1.technology_type} {stage1.intended_use}"
    prefiltered_codes = description_search.find_candidates(query, description_index)
    if not prefiltered_codes:
        return []
    prefiltered = {code: description_index[code] for code in prefiltered_codes}
    return await refine_candidates_from_descriptions(llm, model, stage1, prefiltered, on_usage=on_usage)


async def resolve_fee_schedule_evidence(
    llm: LLMProvider, model: str, stage1: Stage1Extraction, bundle: EvidenceBundle, table: str = "pfs",
    on_usage: UsageCallback | None = None,
) -> SourceEvidence:
    sourced_hints = _sourced_hints_from_bundle(bundle)
    llm_candidates = await propose_llm_candidates(llm, model, stage1, sourced_hints, on_usage=on_usage)
    description_matches = await _description_matched_candidates(llm, model, stage1, table, on_usage=on_usage)
    all_candidates = (
        sourced_hints + llm_candidates + description_matches + list(_KNOWN_GENERIC_CANDIDATE_FAMILIES)
    )
    verified = await verify_candidates(all_candidates, table=table)
    verified = await gate_candidates_by_relevance(llm, model, stage1, verified, table=table, on_usage=on_usage)

    if not verified:
        return SourceEvidence(source="fee_schedule_lookup", status=RetrievalStatus.MISS, latency_ms=0)
    return SourceEvidence(
        source="fee_schedule_lookup", status=RetrievalStatus.HIT, latency_ms=0,
        data={"verified_codes": [_entry_to_evidence_dict(e) for e in verified]},
    )
