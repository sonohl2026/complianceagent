import uuid

from app.models.enums import CollectionType, EvidenceStatus, RiskLevel
from app.models.product import Product
from app.models.project import Project
from app.services.analysis.pipeline import (
    _prior_outputs_for_stage,
    _project_facts,
    _redact_chunk_text,
    _resolve_citations,
    _resolve_stage_models,
    _safe_enum,
)
from app.models.enums import CitationRole
from app.services.retrieval.hybrid_search import RetrievedChunk


def _chunk(text: str, citation_label="Doc p.1") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Doc",
        collection_type=CollectionType.COMPANY,
        authority_level=None,
        text=text,
        citation_label=citation_label,
        page_number=1,
        heading_path=None,
        score=0.5,
    )


def test_safe_enum_returns_matching_member():
    assert _safe_enum(RiskLevel, "HIGH", RiskLevel.LOW) == RiskLevel.HIGH


def test_safe_enum_falls_back_on_unrecognized_value():
    assert _safe_enum(RiskLevel, "SUPER_HIGH", RiskLevel.MEDIUM) == RiskLevel.MEDIUM


def test_safe_enum_handles_empty_string_as_unrecognized():
    assert _safe_enum(EvidenceStatus, "", EvidenceStatus.MISSING) == EvidenceStatus.MISSING


def test_project_facts_includes_product_when_present():
    project = Project(id=uuid.uuid4(), company_id=uuid.uuid4(), name="Readiness Project", jurisdiction="US")
    product = Product(id=uuid.uuid4(), company_id=project.company_id, name="SonoHL Platform", regulatory_stage="Investigational")
    facts = _project_facts(project, product)
    assert facts["project_name"] == "Readiness Project"
    assert facts["product"]["name"] == "SonoHL Platform"
    assert facts["product"]["regulatory_stage"] == "Investigational"


def test_project_facts_flags_missing_product():
    project = Project(id=uuid.uuid4(), company_id=uuid.uuid4(), name="Readiness Project")
    facts = _project_facts(project, None)
    assert "INPUT REQUIRED" in facts["product"]


def test_redact_chunk_text_replaces_email_and_preserves_other_fields():
    chunk = _chunk("Contact info@sonohl.com for more.")
    redacted = _redact_chunk_text(chunk, {"redact_emails": True, "redact_phone_numbers": True, "redact_patient_identifiers": True})
    assert "[REDACTED-EMAIL]" in redacted.text
    assert redacted.citation_label == chunk.citation_label
    assert redacted.chunk_id == chunk.chunk_id


def test_redact_chunk_text_is_a_noop_when_nothing_to_redact():
    chunk = _chunk("No sensitive data here.")
    redacted = _redact_chunk_text(chunk, {"redact_emails": True, "redact_phone_numbers": True, "redact_patient_identifiers": True})
    assert redacted is chunk  # identity preserved when text is unchanged


def test_resolve_citations_matches_known_labels():
    chunk = _chunk("Evidence text", citation_label="Doc p.2")
    lookup = {"Doc p.2": chunk}
    citations = _resolve_citations(["Doc p.2"], lookup, CitationRole.COMPANY_EVIDENCE)
    assert len(citations) == 1
    assert citations[0].document_id == chunk.document_id
    assert citations[0].chunk_id == chunk.chunk_id
    assert citations[0].citation_role == CitationRole.COMPANY_EVIDENCE


def test_resolve_citations_handles_unknown_label_gracefully():
    citations = _resolve_citations(["Nonexistent Doc p.9"], {}, CitationRole.CONTROLLING_AUTHORITY)
    assert len(citations) == 1
    assert citations[0].document_id is None
    assert citations[0].chunk_id is None


def _all_outputs():
    return {
        "input_audit": {"summary": "audit"},
        "product_facts": {"facts": []},
        "claims": {"claims": []},
        "coding": {"candidates": []},
        "regulatory_analysis": {"findings": []},
        "coverage_analysis": {"findings": []},
        "findings_for_audit": [{"id": "1"}],
    }


def test_prior_outputs_for_input_audit_gets_nothing():
    # It's the first stage -- there's nothing to hand it yet.
    assert _prior_outputs_for_stage("input_audit", _all_outputs()) == {}


def test_prior_outputs_for_product_fact_extraction_gets_only_input_audit():
    result = _prior_outputs_for_stage("product_fact_extraction", _all_outputs())
    assert set(result.keys()) == {"input_audit"}


def test_prior_outputs_for_claim_extraction_gets_only_product_facts():
    result = _prior_outputs_for_stage("claim_extraction", _all_outputs())
    assert set(result.keys()) == {"product_facts"}


def test_prior_outputs_for_coding_analysis_gets_only_product_facts():
    result = _prior_outputs_for_stage("coding_analysis", _all_outputs())
    assert set(result.keys()) == {"product_facts"}


def test_prior_outputs_for_domain_analysis_gets_product_facts_coding_and_claims():
    result = _prior_outputs_for_stage("domain_analysis", _all_outputs())
    assert set(result.keys()) == {"product_facts", "coding", "claims"}


def test_prior_outputs_for_synthesis_gets_everything():
    # The one deliberate exception: synthesis needs the whole picture to
    # produce a coherent overall verdict.
    all_outputs = _all_outputs()
    result = _prior_outputs_for_stage("synthesis", all_outputs)
    assert result == all_outputs


def test_prior_outputs_for_citation_audit_gets_only_findings_for_audit():
    result = _prior_outputs_for_stage("citation_audit", _all_outputs())
    assert set(result.keys()) == {"findings_for_audit"}


def test_prior_outputs_selector_never_crashes_on_missing_keys():
    # A stage's designated prior keys might not exist yet in edge cases --
    # pick() must skip missing keys rather than KeyError.
    assert _prior_outputs_for_stage("synthesis", {}) == {}
    assert _prior_outputs_for_stage("domain_analysis", {}) == {}


def test_resolve_stage_models_falls_back_to_default_when_tiers_unset():
    extraction, synthesis, citation = _resolve_stage_models("anthropic/claude-sonnet-5", {})
    assert extraction == synthesis == citation == "anthropic/claude-sonnet-5"


def test_resolve_stage_models_uses_tier_overrides_when_set():
    privacy = {
        "openrouter_extraction_model": "anthropic/claude-haiku-4.5",
        "openrouter_synthesis_model": "anthropic/claude-opus-4.8",
        "openrouter_citation_model": "anthropic/claude-haiku-4.5",
    }
    extraction, synthesis, citation = _resolve_stage_models("anthropic/claude-sonnet-5", privacy)
    assert extraction == "anthropic/claude-haiku-4.5"
    assert synthesis == "anthropic/claude-opus-4.8"
    assert citation == "anthropic/claude-haiku-4.5"


def test_resolve_stage_models_partial_override_falls_back_per_tier():
    # Only the extraction tier is set; synthesis/citation must still fall
    # back to the default model individually, not all-or-nothing.
    privacy = {"openrouter_extraction_model": "anthropic/claude-haiku-4.5"}
    extraction, synthesis, citation = _resolve_stage_models("anthropic/claude-sonnet-5", privacy)
    assert extraction == "anthropic/claude-haiku-4.5"
    assert synthesis == "anthropic/claude-sonnet-5"
    assert citation == "anthropic/claude-sonnet-5"
