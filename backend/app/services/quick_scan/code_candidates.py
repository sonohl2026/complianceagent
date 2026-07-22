"""Device -> candidate billing code -> verify against real fee-schedule data
(closes the coding/payment pillar gap for devices with no dedicated NCD/LCD/
Article -- see the plan doc's point (b)/(c)). There is no dataset that maps
a device to its code, so this flips the direction: propose candidates, then
verify every one against real, current PFS data before trusting any of them
-- mirrors the same verify-before-trust pattern already proven for openFDA
identity matching (a wrong/unverified match is worse than an honest miss).
"""

import re

from app.services.analysis.prompts_service import load_module_prompt
from app.services.evidence_retrieval.orchestrator import EvidenceBundle
from app.services.evidence_retrieval.types import RetrievalStatus, SourceEvidence
from app.services.fee_schedule import cache
from app.services.fee_schedule.code_format import CodeFormat, classify_code_format
from app.services.fee_schedule.types import FeeScheduleEntry
from app.services.llm.base import LLMProvider
from app.services.quick_scan.schemas import CandidateCodesResponse, Stage1Extraction
from app.services.quick_scan.stage1_extraction import wrap_untrusted_data

_MAX_OUTPUT_TOKENS = 1500  # a longer candidate list (each ~6-char code) can exceed a Stage-1-sized budget


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


async def propose_llm_candidates(llm: LLMProvider, model: str, stage1: Stage1Extraction, sourced_hints: list[str]) -> list[str]:
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
    return CandidateCodesResponse.model_validate(result.content).candidate_codes


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


def _entry_to_evidence_dict(entry: FeeScheduleEntry) -> dict:
    return {
        "code": entry.code, "code_format": entry.code_format.value, "payment_system": entry.payment_system,
        "rate_usd": entry.rate_usd, "status_code": entry.status_code,
        # description is already None for AMA-licensed (CPT) formats -- see
        # code_format.py / pfs_client.py, enforced at parse time.
        "description": entry.description,
    }


async def resolve_fee_schedule_evidence(
    llm: LLMProvider, model: str, stage1: Stage1Extraction, bundle: EvidenceBundle, table: str = "pfs",
) -> SourceEvidence:
    sourced_hints = _sourced_hints_from_bundle(bundle)
    llm_candidates = await propose_llm_candidates(llm, model, stage1, sourced_hints)
    verified = await verify_candidates(sourced_hints + llm_candidates, table=table)

    if not verified:
        return SourceEvidence(source="fee_schedule_lookup", status=RetrievalStatus.MISS, latency_ms=0)
    return SourceEvidence(
        source="fee_schedule_lookup", status=RetrievalStatus.HIT, latency_ms=0,
        data={"verified_codes": [_entry_to_evidence_dict(e) for e in verified]},
    )
