"""HTML rendering of the same report data, styled for clean PDF output via
WeasyPrint (app/services/reporting/pdf_report.py). Kept as plain string
templating (no Jinja) since the structure is simple and this avoids adding
another templating dependency."""

import html

from app.services.reporting.data import DOMAIN_ORDER, ReportData, ReportFinding
from app.services.reporting.markdown_report import (
    CONDENSED_FINDING_LIMIT,
    HUMAN_REVIEW_NOTICE,
    LOCAL_DATA_NOTICE,
    DOMAIN_TITLES,
)

RISK_COLORS = {"CRITICAL": "#b91c1c", "HIGH": "#c2410c", "MEDIUM": "#a16207", "LOW": "#15803d"}
VERDICT_COLORS = {"GO": "#15803d", "CONDITIONAL_GO": "#a16207", "STOP": "#b91c1c"}

CSS = """
@page { size: Letter; margin: 2.2cm 1.8cm; }
body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #1e293b; font-size: 10.5pt; line-height: 1.45; }
h1 { font-size: 20pt; margin-bottom: 0.2em; }
h2 { font-size: 14pt; border-bottom: 1px solid #cbd5e1; padding-bottom: 0.2em; margin-top: 1.6em; }
h3 { font-size: 11.5pt; margin-bottom: 0.1em; }
.notice { background: #fffbeb; border: 1px solid #fcd34d; padding: 0.6em 0.9em; font-size: 9pt; border-radius: 4px; }
.metrics { display: flex; gap: 1em; margin: 1em 0; }
.metric { border: 1px solid #cbd5e1; border-radius: 6px; padding: 0.6em 1em; flex: 1; }
.metric .label { font-size: 8pt; text-transform: uppercase; color: #64748b; }
.metric .value { font-size: 13pt; font-weight: 600; }
.badge { display: inline-block; border-radius: 4px; padding: 0.1em 0.5em; font-size: 8.5pt; font-weight: 600; color: white; }
.finding { border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.7em 1em; margin-bottom: 0.8em; page-break-inside: avoid; }
.finding .meta { font-size: 8.5pt; color: #64748b; margin-top: 0.3em; }
table { width: 100%; border-collapse: collapse; font-size: 9pt; margin: 0.8em 0; table-layout: fixed; }
th, td { border: 1px solid #cbd5e1; padding: 0.35em 0.5em; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
th { background: #f1f5f9; }
.citations { font-size: 8.5pt; color: #475569; margin-top: 0.4em; }
.coding-summary th:nth-child(1), .coding-summary td:nth-child(1) { width: 24%; }
.coding-summary th:nth-child(2), .coding-summary td:nth-child(2) { width: 14%; }
.coding-summary th:nth-child(3), .coding-summary td:nth-child(3) { width: 12%; }
.coding-summary th:nth-child(4), .coding-summary td:nth-child(4) { width: 50%; }
/* Coding candidates render as stacked cards, not a wide table: coverage/
   payment/billing status hold full explanatory sentences by design (see
   docs/data-model.md), which a dense multi-column table cannot fit without
   overflowing the page. */
.coding-candidate { border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.7em 1em; margin-bottom: 0.8em; page-break-inside: avoid; }
.coding-candidate dl { margin: 0.4em 0 0 0; display: grid; grid-template-columns: 8em 1fr; gap: 0.25em 0.6em; }
.coding-candidate dt { font-weight: 600; font-size: 8pt; color: #64748b; text-transform: uppercase; }
.coding-candidate dd { margin: 0; }
.coding-candidate .requirement { border-top: 1px dashed #e2e8f0; margin-top: 0.5em; padding-top: 0.4em; font-size: 9pt; }
.footer-notice { font-weight: 600; background: #fffbeb; border: 1px solid #fcd34d; padding: 0.8em; border-radius: 4px; font-size: 9pt; }
.sources { font-size: 9pt; padding-left: 1.2em; }
.sources li { margin-bottom: 0.3em; }
.sources .no-url { color: #94a3b8; font-style: italic; }
a { color: #1d4ed8; }
"""


def _esc(text: str | None) -> str:
    return html.escape(text) if text else ""


def _safe_href(url: str | None) -> str | None:
    # Belt-and-suspenders: the schema-level validator already rejects
    # non-http(s) URLs at the point a human enters them
    # (app/schemas/document.py::_require_http_scheme), but this is a real
    # href-rendering path, so check again here rather than trust every
    # upstream caller forever.
    if url and (url.startswith("http://") or url.startswith("https://")):
        return url
    return None


def _badge(value: str | None, colors: dict[str, str]) -> str:
    if not value:
        return "—"
    color = colors.get(value, "#64748b")
    # Enum values like NOT_CURRENTLY_SUPPORTED have no natural break point, so
    # a narrow column forces an ugly mid-word hyphenation; swap underscores
    # for spaces so it wraps at word boundaries instead.
    label = value.replace("_", " ")
    return f'<span class="badge" style="background:{color}">{_esc(label)}</span>'


def _coding_candidate_html(c) -> str:
    parts = [
        '<div class="coding-candidate">',
        f"<h3>{_esc(c.code_system)}" + (f" {_esc(c.code)}" if c.code else "") + f" {_badge(c.eligibility_status, {})}</h3>",
        f"<p>{_esc(c.service_definition)}</p>",
        "<dl>",
    ]
    if c.code_year:
        parts.append(f"<dt>Code year</dt><dd>{_esc(c.code_year)}</dd>")
    parts.append(f"<dt>Coverage</dt><dd>{_esc(c.coverage_status) or '—'}</dd>")
    parts.append(f"<dt>Payment</dt><dd>{_esc(c.payment_status) or '—'}</dd>")
    parts.append(f"<dt>Billing</dt><dd>{_esc(c.billing_status) or '—'}</dd>")
    if c.major_gaps:
        parts.append(f"<dt>Major gaps</dt><dd>{_esc('; '.join(c.major_gaps))}</dd>")
    parts.append("</dl>")
    if c.expert_review_required:
        parts.append('<p style="font-size:8.5pt;color:#b45309"><strong>Expert coding review required.</strong></p>')
    for r in c.requirements:
        parts.append(
            f'<div class="requirement"><strong>{_esc(r.requirement_name)}</strong> — {_esc(r.status)}<br/>'
            f"{_esc(r.requirement_text)}" + (f"<br/><em>Gap: {_esc(r.gap)}</em>" if r.gap else "") + "</div>"
        )
    parts.append("</div>")
    return "\n".join(parts)


def _condensed_finding_html(f: ReportFinding) -> str:
    parts = [
        '<div class="finding">',
        f"<h3>{_esc(f.title)} {_badge(f.risk, RISK_COLORS)} "
        f'<span style="font-size:8pt;color:#64748b;font-weight:400">{_esc(f.domain.replace("_", " ").title())}</span></h3>',
        f"<p>{_esc(f.description)}</p>",
    ]
    if f.recommended_action:
        parts.append(f"<p><em>Action:</em> {_esc(f.recommended_action)}</p>")
    parts.append("</div>")
    return "\n".join(parts)


def _finding_html(f: ReportFinding) -> str:
    parts = [
        '<div class="finding">',
        f"<h3>{_esc(f.title)} {_badge(f.risk, RISK_COLORS)}</h3>",
        f"<p>{_esc(f.description)}</p>",
    ]
    if f.verified_fact:
        parts.append(f"<p><em>Verified fact:</em> {_esc(f.verified_fact)}</p>")
    if f.missing_information:
        parts.append(f"<p><em>Missing information:</em> {_esc('; '.join(f.missing_information))}</p>")
    if f.recommended_action:
        parts.append(f"<p><em>Recommended action:</em> {_esc(f.recommended_action)}</p>")
    meta_bits = [f"Status: {_esc(f.status)}"]
    if f.responsible_owner:
        meta_bits.append(f"Owner: {_esc(f.responsible_owner)}")
    if f.priority is not None:
        meta_bits.append(f"Priority: {f.priority}")
    if f.confidence is not None:
        meta_bits.append(f"Confidence: {f.confidence}")
    if f.human_review_required:
        meta_bits.append("<strong>Human review required</strong>")
    parts.append(f'<div class="meta">{" · ".join(meta_bits)}</div>')
    if f.citations:
        cite_strs = []
        for c in f.citations:
            location = ", ".join(b for b in (c.document_title, c.section_title) if b) or "source"
            href = _safe_href(c.url)
            label = f'<a href="{_esc(href)}">{_esc(location)}</a>' if href else _esc(location)
            cite_strs.append(f"[{_esc(c.role)}] {label}")
        parts.append(f'<div class="citations">Citations: {" &middot; ".join(cite_strs)}</div>')
    parts.append("</div>")
    return "\n".join(parts)


def build_html_report(data: ReportData, *, mode: str = "condensed") -> str:
    body = []
    title = f"{_esc(data.company_name)}" + (f" — {_esc(data.product_name)}" if data.product_name else "")
    body.append(f"<h1>{title}</h1>")
    body.append(f'<div class="notice">{_esc(LOCAL_DATA_NOTICE)}</div>')

    body.append('<div class="metrics">')
    body.append(f'<div class="metric"><div class="label">Verdict</div><div class="value">{_badge(data.overall_verdict, VERDICT_COLORS)}</div></div>')
    body.append(f'<div class="metric"><div class="label">Risk</div><div class="value">{_badge(data.overall_risk, RISK_COLORS)}</div></div>')
    body.append(f'<div class="metric"><div class="label">Readiness</div><div class="value">{data.readiness_score if data.readiness_score is not None else "—"}</div></div>')
    body.append(f'<div class="metric"><div class="label">Confidence</div><div class="value">{data.confidence_score if data.confidence_score is not None else "—"}</div></div>')
    body.append("</div>")
    if data.readiness_score_note:
        body.append(f"<p style='font-size:8.5pt;color:#64748b;font-style:italic'>{_esc(data.readiness_score_note)}</p>")

    body.append(
        f"<p style='font-size:8.5pt;color:#64748b'>Model: {_esc(data.analysis_model) or '—'}"
        + (f" (responded as {_esc(data.model_response_identifier)})" if data.model_response_identifier else "")
        + f" &middot; Source cutoff: {_esc(data.source_cutoff_date) or '—'}"
        + f" &middot; Jurisdiction: {_esc(data.jurisdiction) or '—'}</p>"
    )

    if data.executive_summary:
        body.append("<h2>Executive Summary</h2>")
        body.append(f"<p>{_esc(data.executive_summary)}</p>")

    if data.missing_inputs:
        body.append("<h2>Missing Inputs</h2><ul>")
        body.extend(f"<li>{_esc(item)}</li>" for item in data.missing_inputs)
        body.append("</ul>")

    if mode == "condensed":
        shown = data.findings_by_priority()[:CONDENSED_FINDING_LIMIT]
        if shown:
            body.append("<h2>Top Findings</h2>")
            body.append(
                f"<p style='font-size:8.5pt;color:#64748b'>Showing the {len(shown)} highest-priority "
                f"finding(s) of {len(data.findings)} total, ranked by risk then the model's own priority "
                "ranking. Generate the extended report for the full breakdown by domain, full citations, "
                "and the coding matrix.</p>"
            )
            body.extend(_condensed_finding_html(f) for f in shown)
        if data.coding_candidates:
            body.append(
                f"<p style='font-size:8.5pt;color:#64748b'>{len(data.coding_candidates)} candidate coding "
                "pathway(s) identified — see the extended report for the full eligibility/coverage/"
                "payment/billing detail.</p>"
            )
    else:
        grouped = data.findings_by_domain()
        for domain in DOMAIN_ORDER:
            domain_findings = grouped.get(domain)
            if not domain_findings:
                continue
            body.append(f"<h2>{_esc(DOMAIN_TITLES.get(domain, domain.replace('_', ' ').title()))}</h2>")
            body.extend(_finding_html(f) for f in domain_findings)

        if data.coding_candidates:
            body.append("<h2>Candidate Coding Pathways</h2>")
            # Quick-reference summary first: only columns short enough to never
            # overflow a table cell. Full detail (coverage/payment/billing
            # sentences, requirements) follows as cards below.
            body.append(
                '<table class="coding-summary"><tr><th>Code system</th><th>Code</th><th>Code year</th><th>Eligibility</th></tr>'
            )
            for c in data.coding_candidates:
                body.append(
                    f"<tr><td>{_esc(c.code_system)}</td><td>{_esc(c.code) or '—'}</td>"
                    f"<td>{_esc(c.code_year) or '—'}</td><td>{_badge(c.eligibility_status, {})}</td></tr>"
                )
            body.append("</table>")
            body.extend(_coding_candidate_html(c) for c in data.coding_candidates)
            body.append(
                "<p style='font-size:8.5pt;color:#64748b'>No candidate above is an approved billing "
                "instruction. Expert coding review is required regardless of eligibility status.</p>"
            )

    if data.critical_blockers:
        body.append("<h2>Critical Blockers</h2><ul>")
        body.extend(f"<li>{_esc(item)}</li>" for item in data.critical_blockers)
        body.append("</ul>")

    if data.priority_actions:
        body.append("<h2>Prioritized Action Plan</h2><ul>")
        body.extend(f"<li>{_esc(item)}</li>" for item in data.priority_actions)
        body.append("</ul>")

    if data.required_reviewers:
        body.append("<h2>Required Human Reviewers</h2>")
        body.append(f"<p>{_esc(', '.join(data.required_reviewers))}</p>")

    if data.sources and mode == "condensed":
        body.append("<h2>Sources</h2>")
        body.append(
            f"<p style='font-size:8.5pt;color:#64748b'>{len(data.sources)} source(s) backed the findings "
            "in this run. See the extended report for the full list with links.</p>"
        )
    elif data.sources:
        body.append("<h2>Sources</h2>")
        body.append(
            "<p style='font-size:8.5pt;color:#64748b'>Every source below backed at least one "
            "citation above and is either a page this application actually crawled or an Authority "
            "Library document with a source URL recorded by a human reviewer — never a link "
            "generated by the model.</p>"
        )
        body.append('<ul class="sources">')
        for s in data.sources:
            label_bits = [b for b in (s.issuer, s.jurisdiction, s.authority_level) if b]
            label = f" ({_esc(', '.join(label_bits))})" if label_bits else ""
            href = _safe_href(s.url)
            if href:
                body.append(f'<li><a href="{_esc(href)}">{_esc(s.title)}</a>{label}</li>')
            else:
                body.append(f'<li>{_esc(s.title)}{label} <span class="no-url">— no source URL on file</span></li>')
        body.append("</ul>")

    body.append(f'<div class="footer-notice">{_esc(HUMAN_REVIEW_NOTICE)}</div>')
    body.append(
        f"<p style='font-size:8pt;color:#94a3b8'>Report generated {_esc(data.generated_at)} "
        f"&middot; Analysis ID {_esc(data.analysis_id)}</p>"
    )

    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(body)}</body></html>"
