from app.services.reporting.data import (
    ReportCitation,
    ReportCodingCandidate,
    ReportCodingRequirement,
    ReportData,
    ReportFinding,
    ReportSource,
)
from app.services.reporting.html_report import build_html_report
from app.services.reporting.markdown_report import HUMAN_REVIEW_NOTICE, build_markdown_report


def _sample_data() -> ReportData:
    findings = [
        ReportFinding(
            domain="FDA_REGULATORY",
            title="No verified FDA status",
            description="The product's FDA regulatory status could not be verified from available evidence.",
            status="MISSING",
            risk="CRITICAL",
            verdict="STOP",
            verified_fact=None,
            missing_information=["FDA clearance/approval letter", "predicate device analysis"],
            applicable_requirement="21 CFR Part 807",
            recommended_action="Escalate to Regulatory for FDA-status confirmation.",
            responsible_owner="Regulatory",
            priority=1,
            confidence=90,
            human_review_required=True,
            citations=[
                ReportCitation(
                    role="AUTHORITY_SOURCE",
                    quoted_text="A device must have FDA clearance or approval before commercial distribution.",
                    section_title="21 CFR 807.81",
                    page_number=None,
                    url="https://www.fda.gov/medical-devices/premarket-notification-510k",
                    document_title="FDA 510(k) Premarket Notification Guidance",
                ),
                ReportCitation(role="COMPANY_EVIDENCE", quoted_text="Home page text", section_title="Home", page_number=1),
            ],
        ),
        ReportFinding(
            domain="MARKETING",
            title="Unsubstantiated diagnostic claim",
            description="The website claims the device 'diagnoses heart disease' without supporting evidence.",
            status="UNRESOLVED",
            risk="HIGH",
            verdict=None,
            verified_fact=None,
            missing_information=[],
            applicable_requirement=None,
            recommended_action="Remove or qualify the claim pending evidence.",
            responsible_owner="Communications",
            priority=2,
            confidence=80,
            human_review_required=True,
            citations=[],
        ),
    ]
    coding_candidates = [
        ReportCodingCandidate(
            code_system="CPT_CATEGORY_III",
            code=None,
            code_year="2024",
            service_definition="Remote acoustic monitoring service",
            eligibility_status="EXPERT_REVIEW_REQUIRED",
            coverage_status="UNDETERMINED pending FDA status",
            payment_status="UNDETERMINED",
            billing_status="NOT ASSESSABLE",
            major_gaps=["No FDA status", "No coverage policy"],
            expert_review_required=True,
            requirements=[
                ReportCodingRequirement(
                    requirement_name="FDA device status",
                    requirement_text="Must be a cleared/approved medical device.",
                    status="MISSING",
                    gap="No verified FDA record",
                )
            ],
        )
    ]
    return ReportData(
        analysis_id="11111111-1111-1111-1111-111111111111",
        company_name="SonoHL Inc.",
        product_name="Acoustic-Sensing Platform",
        jurisdiction="United States",
        analysis_model="anthropic/claude-opus-4.8",
        model_response_identifier="anthropic/claude-4.8-opus-20260528",
        source_cutoff_date="2026-07-08",
        overall_verdict="STOP",
        overall_risk="CRITICAL",
        readiness_score=8,
        readiness_score_note=None,
        confidence_score=86,
        executive_summary="Every module returned a STOP verdict due to unresolved FDA status.",
        critical_blockers=["FDA status and regulatory stage are unresolved."],
        missing_inputs=["FDA correspondence", "Clinical protocol"],
        priority_actions=["Escalate to Regulatory and FDA counsel."],
        required_reviewers=["Regulatory", "Legal", "Communications"],
        findings=findings,
        coding_candidates=coding_candidates,
        sources=[
            ReportSource(
                title="FDA 510(k) Premarket Notification Guidance",
                issuer="FDA",
                jurisdiction="United States",
                authority_level="3_OFFICIAL_EXTERNAL_AUTHORITY",
                url="https://www.fda.gov/medical-devices/premarket-notification-510k",
            ),
            ReportSource(
                title="SonoHL company website (Home)",
                issuer=None,
                jurisdiction=None,
                authority_level=None,
                url=None,
            ),
        ],
    )


def test_markdown_report_includes_header_and_verdict():
    md = build_markdown_report(_sample_data())
    assert "# SonoHL Inc. — Acoustic-Sensing Platform" in md
    assert "**Overall verdict:** STOP" in md
    assert "**Risk:** CRITICAL" in md
    assert "**Readiness score:** 8" in md


def test_markdown_report_groups_findings_by_domain_in_spec_order():
    md = build_markdown_report(_sample_data(), mode="extended")
    fda_index = md.index("FDA and Regulatory Readiness")
    marketing_index = md.index("Public Claims and Marketing")
    assert fda_index < marketing_index  # matches DOMAIN_ORDER


def test_markdown_report_includes_citations():
    md = build_markdown_report(_sample_data(), mode="extended")
    assert "COMPANY_EVIDENCE" in md


def test_markdown_report_includes_coding_candidates_as_stacked_blocks():
    md = build_markdown_report(_sample_data(), mode="extended")
    assert "## Candidate Coding Pathways" in md
    assert "CPT_CATEGORY_III" in md
    assert "UNDETERMINED pending FDA status" in md  # full sentence, not truncated to fit a table column
    assert "is an approved billing instruction" in md.lower()


def test_markdown_report_always_includes_mandatory_disclaimer():
    md = build_markdown_report(_sample_data())
    assert HUMAN_REVIEW_NOTICE in md


def test_markdown_report_includes_critical_blockers_and_actions():
    md = build_markdown_report(_sample_data())
    assert "FDA status and regulatory stage are unresolved." in md
    assert "Escalate to Regulatory and FDA counsel." in md


def test_html_report_is_valid_shell_and_includes_disclaimer():
    html_doc = build_html_report(_sample_data())
    assert html_doc.startswith("<!doctype html>")
    assert "<style>" in html_doc
    assert HUMAN_REVIEW_NOTICE in html_doc


def test_html_report_escapes_content_to_prevent_injection():
    from app.services.reporting.data import ReportData as RD

    data = _sample_data()
    data.executive_summary = "<script>alert('xss')</script>"
    html_doc = build_html_report(data)
    assert "<script>alert" not in html_doc
    assert "&lt;script&gt;" in html_doc


def test_html_report_includes_coding_candidate_summary_table_and_detail_card():
    html_doc = build_html_report(_sample_data(), mode="extended")
    # Compact summary table (short columns only -- code/year/eligibility)
    # plus a detail card underneath for the long-text fields.
    assert "<table" in html_doc
    assert "<th>Code system</th>" in html_doc
    assert "<th>Coverage</th>" not in html_doc  # long-text fields must not be table columns
    assert 'class="coding-candidate"' in html_doc
    assert "CPT_CATEGORY_III" in html_doc
    assert "UNDETERMINED pending FDA status" in html_doc  # full sentence renders, not squeezed into a cell


def test_markdown_report_includes_coding_candidate_summary_table():
    md = build_markdown_report(_sample_data(), mode="extended")
    assert "| Code system | Code | Code year | Eligibility |" in md
    assert "CPT_CATEGORY_III" in md


def test_findings_by_priority_sorts_critical_before_high():
    data = _sample_data()
    ranked = data.findings_by_priority()
    assert ranked[0].risk == "CRITICAL"
    assert ranked[1].risk == "HIGH"


def test_findings_by_domain_groups_correctly():
    data = _sample_data()
    grouped = data.findings_by_domain()
    assert set(grouped.keys()) == {"FDA_REGULATORY", "MARKETING"}
    assert len(grouped["FDA_REGULATORY"]) == 1


def test_markdown_citation_with_url_renders_as_link():
    md = build_markdown_report(_sample_data(), mode="extended")
    assert "[FDA 510(k) Premarket Notification Guidance, 21 CFR 807.81](https://www.fda.gov/medical-devices/premarket-notification-510k)" in md


def test_markdown_citation_without_url_renders_as_plain_text_not_broken_link():
    md = build_markdown_report(_sample_data(), mode="extended")
    assert "[COMPANY_EVIDENCE] Home" in md
    assert "[Home](" not in md  # no url on this citation -- must not fabricate one


def test_markdown_sources_section_lists_url_and_no_url_cases():
    md = build_markdown_report(_sample_data(), mode="extended")
    assert "## Sources" in md
    assert "[FDA 510(k) Premarket Notification Guidance](https://www.fda.gov/medical-devices/premarket-notification-510k)" in md
    assert "SonoHL company website (Home)" in md
    assert "no source URL on file" in md


def test_html_citation_with_url_renders_as_anchor():
    html_doc = build_html_report(_sample_data(), mode="extended")
    assert '<a href="https://www.fda.gov/medical-devices/premarket-notification-510k">' in html_doc


def test_html_sources_section_present_with_link_and_no_url_fallback():
    html_doc = build_html_report(_sample_data(), mode="extended")
    assert "<h2>Sources</h2>" in html_doc
    assert 'class="sources"' in html_doc
    assert "no source URL on file" in html_doc


def test_html_report_never_renders_non_http_scheme_as_href():
    # Defense-in-depth: even if a bad-scheme URL somehow made it into the
    # data (schema validation is meant to prevent this at the point of
    # entry), the renderer itself must not turn it into a clickable link.
    data = _sample_data()
    data.sources = [
        ReportSource(title="Malicious", issuer=None, jurisdiction=None, authority_level=None, url="javascript:alert(1)")
    ]
    html_doc = build_html_report(data, mode="extended")
    assert "javascript:" not in html_doc
    assert "no source URL on file" in html_doc


def _many_findings(count: int) -> list[ReportFinding]:
    return [
        ReportFinding(
            domain="FDA_REGULATORY",
            title=f"Finding {i}",
            description=f"Description for finding {i}.",
            status="UNRESOLVED",
            risk="HIGH",
            verdict=None,
            verified_fact=None,
            missing_information=[],
            applicable_requirement=None,
            recommended_action=f"Fix finding {i}.",
            responsible_owner=None,
            priority=i,
            confidence=70,
            human_review_required=False,
            citations=[],
        )
        for i in range(1, count + 1)
    ]


def test_markdown_default_is_condensed_mode():
    md = build_markdown_report(_sample_data())
    assert "## Top Findings" in md
    assert "## FDA and Regulatory Readiness" not in md


def test_markdown_extended_mode_shows_domain_sections_not_top_findings():
    md = build_markdown_report(_sample_data(), mode="extended")
    assert "## FDA and Regulatory Readiness" in md
    assert "## Top Findings" not in md


def test_markdown_condensed_mode_truncates_to_limit():
    data = _sample_data()
    data.findings = _many_findings(20)
    md = build_markdown_report(data, mode="condensed")
    assert "Finding 1\n" in md or "**Finding 1**" in md
    assert "highest-priority finding(s) of 20 total" in md
    assert "**Finding 20**" not in md  # beyond CONDENSED_FINDING_LIMIT=12, ranked by priority


def test_markdown_condensed_mode_summarizes_sources_without_full_list():
    md = build_markdown_report(_sample_data(), mode="condensed")
    assert "source(s) backed the findings" in md
    assert "FDA 510(k) Premarket Notification Guidance](https" not in md


def test_html_default_is_condensed_mode():
    html_doc = build_html_report(_sample_data())
    assert "Top Findings" in html_doc
    assert "FDA and Regulatory Readiness" not in html_doc


def test_html_extended_mode_shows_domain_sections_not_top_findings():
    html_doc = build_html_report(_sample_data(), mode="extended")
    assert "FDA and Regulatory Readiness" in html_doc
    assert "Top Findings" not in html_doc


def test_html_condensed_mode_truncates_to_limit():
    data = _sample_data()
    data.findings = _many_findings(20)
    html_doc = build_html_report(data, mode="condensed")
    assert "Finding 1" in html_doc
    assert "Finding 20" not in html_doc


def test_both_modes_always_include_mandatory_disclaimer():
    for mode in ("condensed", "extended"):
        md = build_markdown_report(_sample_data(), mode=mode)
        html_doc = build_html_report(_sample_data(), mode=mode)
        assert HUMAN_REVIEW_NOTICE in md
        assert HUMAN_REVIEW_NOTICE in html_doc
