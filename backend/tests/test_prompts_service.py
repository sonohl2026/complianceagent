import pytest

from app.services.analysis.prompts_service import _read_master_prompt_file, load_module_prompt


def test_load_module_prompt_strips_frontmatter_and_returns_body():
    content = load_module_prompt("regulatory_analysis")
    assert not content.startswith("---")
    assert "Module Prompt" in content
    assert "master prompt remains controlling" in content.lower()


def test_load_module_prompt_rejects_unknown_stage():
    with pytest.raises(ValueError, match="Unknown pipeline stage"):
        load_module_prompt("not_a_real_stage")


def test_all_ten_module_prompts_load_without_error():
    stages = [
        "product_fact_extraction",
        "claim_extraction",
        "regulatory_analysis",
        "coding_analysis",
        "coverage_analysis",
        "payment_analysis",
        "billing_analysis",
        "marketing_analysis",
        "synthesis",
        "citation_audit",
    ]
    for stage in stages:
        content = load_module_prompt(stage)
        assert len(content) > 50


def test_master_prompt_file_loads_and_strips_frontmatter():
    content = _read_master_prompt_file()
    assert not content.startswith("---")
    assert "MedTech Reimbursement Readiness Agent" in content
    assert content.startswith("#")
