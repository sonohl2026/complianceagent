"""Markdown report generation (build spec §22).

Every finding keeps its citations inline so the report is traceable back to
source chunks, and the report always closes with the mandatory human-review
disclaimer (build spec §3.6) -- never omitted, regardless of verdict.
"""

from app.services.reporting.data import DOMAIN_ORDER, ReportCitation, ReportData, ReportFinding

LOCAL_DATA_NOTICE = (
    "This application is locally hosted, but model requests sent through OpenRouter are "
    "processed by external model providers. Do not submit protected health information, "
    "patient-identifiable information, confidential clinical-trial data, privileged legal "
    "advice, or other restricted information unless your organization has approved the "
    "relevant data-processing arrangements."
)

HUMAN_REVIEW_NOTICE = (
    "This application provides internal decision support. It does not constitute legal "
    "advice, regulatory authorization, payer confirmation, coding advice, or billing "
    "approval. Final decisions require review by qualified regulatory, legal, clinical, "
    "coding, reimbursement, privacy, security, and quality professionals as applicable."
)

DOMAIN_TITLES = {
    "PRODUCT_DEFINITION": "Product Definition",
    "FDA_REGULATORY": "FDA and Regulatory Readiness",
    "CLINICAL_EVIDENCE": "Clinical and Economic Evidence",
    "QUALITY_SYSTEM": "Quality, Software, AI, and Cybersecurity",
    "CYBERSECURITY": "Cybersecurity",
    "CODING": "Coding",
    "COVERAGE": "Coverage Analysis",
    "PAYMENT": "Payment-System Analysis",
    "BILLING": "Billing-Workflow Analysis",
    "PROVIDER_ECONOMICS": "Provider Economics",
    "MANUFACTURER_ECONOMICS": "Manufacturer Economics",
    "MARKETING": "Public Claims and Marketing",
    "FRAUD_ABUSE": "Fraud and Abuse Considerations",
    "PRIVACY": "Privacy Considerations",
    "RESEARCH_COMPLIANCE": "Research Compliance",
    "POSTMARKET": "Postmarket Obligations",
}


def _citation_line(c: ReportCitation) -> str:
    location_bits = [b for b in (c.document_title, c.section_title or (f"p.{c.page_number}" if c.page_number else None)) if b]
    location = ", ".join(location_bits) if location_bits else "source"
    # Only ever a real link when a verified SourceDocument.url is on file --
    # this is resolved server-side (see app/services/reporting/data.py), the
    # LLM never supplies a URL, so there is nothing here for it to fabricate.
    location_md = f"[{location}]({c.url})" if c.url else location
    quote = f' — "{c.quoted_text[:200]}..."' if c.quoted_text and len(c.quoted_text) > 200 else (
        f' — "{c.quoted_text}"' if c.quoted_text else ""
    )
    return f"- [{c.role}] {location_md}{quote}"


# Target: a condensed report should read in a few minutes, not require
# scrolling through 40 pages after every small website tweak (build spec
# extension, user-requested cost/usability fix -- see docs/data-model.md).
CONDENSED_FINDING_LIMIT = 12


def _condensed_finding_line(f: ReportFinding) -> str:
    lines = [f"- **{f.title}** — {f.risk} · {f.domain.replace('_', ' ').title()}"]
    lines.append(f"  {f.description}")
    if f.recommended_action:
        lines.append(f"  *Action:* {f.recommended_action}")
    return "\n".join(lines)


def _finding_block(f: ReportFinding) -> str:
    lines = [f"**{f.title}** — risk: {f.risk} · status: {f.status}" + (f" · verdict: {f.verdict}" if f.verdict else "")]
    lines.append("")
    lines.append(f.description)
    if f.verified_fact:
        lines.append(f"\n*Verified fact:* {f.verified_fact}")
    if f.missing_information:
        lines.append(f"\n*Missing information:* {'; '.join(f.missing_information)}")
    if f.applicable_requirement:
        lines.append(f"\n*Applicable requirement:* {f.applicable_requirement}")
    if f.recommended_action:
        lines.append(f"\n*Recommended action:* {f.recommended_action}")
    owner_bits = []
    if f.responsible_owner:
        owner_bits.append(f"owner: {f.responsible_owner}")
    if f.priority is not None:
        owner_bits.append(f"priority: {f.priority}")
    if f.confidence is not None:
        owner_bits.append(f"confidence: {f.confidence}")
    if owner_bits:
        lines.append(f"\n*{' · '.join(owner_bits)}*")
    if f.human_review_required:
        lines.append("\n**Human review required.**")
    if f.citations:
        lines.append("\nCitations:")
        for c in f.citations:
            lines.append(_citation_line(c))
    return "\n".join(lines)


def build_markdown_report(data: ReportData, *, mode: str = "condensed") -> str:
    """mode="condensed" (default): verdict, executive summary, critical
    blockers, action plan, and the top-priority findings only -- aimed at
    ~6 pages so a human will actually read it after a small incremental
    site/document change. mode="extended": today's full report, every
    finding grouped by domain with citations, plus the full coding matrix
    and sources list. Both render from the exact same already-computed
    analysis data -- no extra LLM call either way."""
    lines: list[str] = []

    lines.append(f"# {data.company_name}" + (f" — {data.product_name}" if data.product_name else ""))
    lines.append("")
    lines.append(f"> {LOCAL_DATA_NOTICE}")
    lines.append("")

    lines.append("## Compliance-Agent Determination")
    lines.append("")
    lines.append(f"- **Overall verdict:** {data.overall_verdict or '[DECISION PENDING]'}")
    lines.append(f"- **Risk:** {data.overall_risk or '—'}")
    lines.append(f"- **Readiness score:** {data.readiness_score if data.readiness_score is not None else '—'}")
    if data.readiness_score_note:
        lines.append(f"  - *{data.readiness_score_note}*")
    lines.append(f"- **Confidence:** {data.confidence_score if data.confidence_score is not None else '—'}")
    lines.append(f"- **Source cutoff:** {data.source_cutoff_date or '—'}")
    lines.append(f"- **Model:** {data.analysis_model or '—'}" + (f" (responded as {data.model_response_identifier})" if data.model_response_identifier else ""))
    lines.append(f"- **Jurisdiction:** {data.jurisdiction or '—'}")
    lines.append("")

    if data.executive_summary:
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(data.executive_summary)
        lines.append("")

    if data.missing_inputs:
        lines.append("## Missing Inputs")
        lines.append("")
        for item in data.missing_inputs:
            lines.append(f"- {item}")
        lines.append("")

    if mode == "condensed":
        shown = data.findings_by_priority()[:CONDENSED_FINDING_LIMIT]
        if shown:
            lines.append("## Top Findings")
            lines.append("")
            lines.append(
                f"Showing the {len(shown)} highest-priority finding(s) of {len(data.findings)} total, "
                "ranked by risk then the model's own priority ranking. Generate the extended report for "
                "the full breakdown by domain, full citations, and the coding matrix."
            )
            lines.append("")
            for f in shown:
                lines.append(_condensed_finding_line(f))
            lines.append("")
        if data.coding_candidates:
            lines.append(
                f"*{len(data.coding_candidates)} candidate coding pathway(s) identified -- see the "
                "extended report for the full eligibility/coverage/payment/billing detail.*"
            )
            lines.append("")
    else:
        grouped = data.findings_by_domain()
        for domain in DOMAIN_ORDER:
            domain_findings = grouped.get(domain)
            if not domain_findings:
                continue
            lines.append(f"## {DOMAIN_TITLES.get(domain, domain.replace('_', ' ').title())}")
            lines.append("")
            for f in domain_findings:
                lines.append(_finding_block(f))
                lines.append("")

        if data.coding_candidates:
            # A table is a poor fit for the full detail here: coverage/payment/
            # billing status hold full explanatory sentences by design (see
            # docs/data-model.md), not short codes, so a fixed-width table either
            # truncates them or breaks its own formatting. Stacked blocks carry
            # the full detail below; this compact table up top is just a
            # quick-reference summary of the columns short enough to survive one.
            lines.append("## Candidate Coding Pathways")
            lines.append("")
            lines.append("| Code system | Code | Code year | Eligibility |")
            lines.append("|---|---|---|---|")
            for c in data.coding_candidates:
                lines.append(f"| {c.code_system} | {c.code or '—'} | {c.code_year or '—'} | {c.eligibility_status} |")
            lines.append("")
            for c in data.coding_candidates:
                header = f"**{c.code_system}" + (f" {c.code}" if c.code else "") + f"** — eligibility: {c.eligibility_status}"
                lines.append(header)
                lines.append("")
                lines.append(c.service_definition)
                if c.code_year:
                    lines.append(f"\n*Code year:* {c.code_year}")
                lines.append(f"\n*Coverage:* {c.coverage_status or '—'}")
                lines.append(f"\n*Payment:* {c.payment_status or '—'}")
                lines.append(f"\n*Billing:* {c.billing_status or '—'}")
                if c.major_gaps:
                    lines.append(f"\n*Major gaps:* {'; '.join(c.major_gaps)}")
                if c.expert_review_required:
                    lines.append("\n**Expert coding review required.**")
                for r in c.requirements:
                    lines.append(f"\n- **{r.requirement_name}** ({r.status}): {r.requirement_text}" + (f" — gap: {r.gap}" if r.gap else ""))
                lines.append("")
            lines.append(
                "No candidate above is an approved billing instruction. Expert coding review is required "
                "regardless of `eligibility_status`."
            )
            lines.append("")

    if data.critical_blockers:
        lines.append("## Critical Blockers")
        lines.append("")
        for item in data.critical_blockers:
            lines.append(f"- {item}")
        lines.append("")

    if data.priority_actions:
        lines.append("## Prioritized Action Plan")
        lines.append("")
        for item in data.priority_actions:
            lines.append(f"- {item}")
        lines.append("")

    if data.required_reviewers:
        lines.append("## Required Human Reviewers")
        lines.append("")
        lines.append(", ".join(data.required_reviewers))
        lines.append("")

    if data.sources and mode == "condensed":
        lines.append("## Sources")
        lines.append("")
        lines.append(
            f"{len(data.sources)} source(s) backed the findings in this run. See the extended report "
            "for the full list with links."
        )
        lines.append("")
    elif data.sources:
        lines.append("## Sources")
        lines.append("")
        lines.append(
            "Every source below backed at least one citation above and is either a page this "
            "application actually crawled or an Authority Library document with a source URL "
            "recorded by a human reviewer -- never a link generated by the model."
        )
        lines.append("")
        for s in data.sources:
            label_bits = [b for b in (s.issuer, s.jurisdiction, s.authority_level) if b]
            label = f" ({', '.join(label_bits)})" if label_bits else ""
            if s.url:
                lines.append(f"- [{s.title}]({s.url}){label}")
            else:
                lines.append(f"- {s.title}{label} — *no source URL on file*")
        lines.append("")

    lines.append("## Methodology and Limitations")
    lines.append("")
    lines.append(
        "Generated by a staged compliance-analysis pipeline (input audit, product fact extraction, "
        "claim extraction, coding/regulatory/coverage/payment/billing/marketing analysis, synthesis, "
        "citation audit). Every finding is linked to company and/or authority source citations where "
        "an external rule is involved, or explicitly marked as missing evidence. Findings reflect the "
        "state of retrieved evidence and the configured model's output at the time of the run; they "
        "are not a substitute for verification against current primary sources."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"**{HUMAN_REVIEW_NOTICE}**")
    lines.append("")
    lines.append(f"*Report generated {data.generated_at} · Analysis ID {data.analysis_id}*")

    return "\n".join(lines)
