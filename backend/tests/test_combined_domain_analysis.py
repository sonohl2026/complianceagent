from app.schemas.analysis_llm import CombinedDomainAnalysisResult, DomainAnalysisResult
from app.services.analysis.pipeline import DOMAIN_STAGES, _build_combined_domain_module_prompt


def _domain_result(domain: str) -> dict:
    return {
        "domain": domain,
        "verdict": "STOP",
        "risk": "HIGH",
        "status": "UNRESOLVED",
        "summary": f"{domain} summary",
        "findings": [],
    }


def test_combined_domain_module_prompt_includes_all_five_domains():
    prompt = _build_combined_domain_module_prompt()
    for stage_name, _, _ in DOMAIN_STAGES:
        assert stage_name in prompt


def test_combined_domain_module_prompt_instructs_not_to_cross_contaminate():
    prompt = _build_combined_domain_module_prompt()
    assert "leak into another domain" in prompt


def test_combined_domain_analysis_result_validates_all_five_fields():
    result = CombinedDomainAnalysisResult.model_validate(
        {
            "regulatory_analysis": _domain_result("FDA_REGULATORY"),
            "coverage_analysis": _domain_result("COVERAGE"),
            "payment_analysis": _domain_result("PAYMENT"),
            "billing_analysis": _domain_result("BILLING"),
            "marketing_analysis": _domain_result("MARKETING"),
        }
    )
    assert isinstance(result.regulatory_analysis, DomainAnalysisResult)
    assert result.marketing_analysis.summary == "MARKETING summary"


def test_combined_domain_analysis_result_field_names_match_domain_stages():
    # getattr(combined_result, stage_name) in pipeline.py relies on these
    # matching exactly.
    schema_fields = set(CombinedDomainAnalysisResult.model_fields.keys())
    stage_names = {stage_name for stage_name, _, _ in DOMAIN_STAGES}
    assert schema_fields == stage_names
