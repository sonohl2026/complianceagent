"""The staged compliance-analysis pipeline (build spec §13).

Each stage is a separate, narrow, schema-validated OpenRouter call rather
than one large agentic loop (build spec §30: "A simple, auditable
multi-stage pipeline is preferable to an opaque fully autonomous agent").
Every finding a stage produces is persisted with citations resolved from the
exact chunks retrieved for that stage -- never a bare, uncited claim.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisRun, Finding
from app.models.citation import Citation
from app.models.claim import ExtractedClaim
from app.models.coding import CodingCandidate, CodingRequirement
from app.models.enums import (
    CitationRole,
    ClaimCategory,
    ClaimDisposition,
    CodingEligibilityStatus,
    CollectionType,
    EvidenceStatus,
    ExpressOrImplied,
    FindingDomain,
    JobStatus,
    RiskLevel,
    Verdict,
)
from app.models.product import Product
from app.models.project import Project
from app.schemas.analysis_llm import (
    ClaimExtractionResult,
    CodingEligibilityResult,
    CombinedDomainAnalysisResult,
    DomainAnalysisResult,
    InputAuditResult,
    OverallAnalysisResult,
    ProductFactExtractionResult,
)
from app.services.analysis.checklist import reconcile_compliance_issues
from app.services.analysis.prompt_composer import compose_messages
from app.services.analysis.prompts_service import get_active_master_prompt, load_module_prompt
from app.services.analysis.scoring import apply_readiness_score_guardrail
from app.services.llm.base import LLMProvider
from app.services.llm.redaction import apply_redaction
from app.services.retrieval.hybrid_search import RetrievalFilter, RetrievedChunk, hybrid_search
from app.services.storage.settings_store import load_runtime_settings

logger = logging.getLogger(__name__)


class AnalysisCancelled(Exception):
    """Raised when POST /analyses/{id}/cancel flips the run's status while
    the pipeline is mid-flight; caught by the caller (app.workers.analysis_tasks)
    so it doesn't get reported as a failure."""


INPUT_AUDIT_MODULE_PROMPT = """# Module Prompt — Input Audit

You are operating beneath the active compliance master system prompt (see master prompt §7 \
Step 3 — Perform an Input Audit). The master prompt remains controlling.

## Task

Using only the verified project facts and retrieved evidence provided, produce an Input Audit: \
for each category of information a compliance analysis needs (product definition, intended use, \
FDA status, clinical evidence, coding/coverage/payment strategy, quality-system records, privacy \
posture), determine whether it is Available, Missing, Conflicting, Stale, or Unverified, and why \
it matters. Do not fabricate a value for a category with no supporting evidence — mark it Missing.

## Output

Return structured JSON conforming to the InputAuditResult schema."""


@dataclass
class StageContext:
    db: AsyncSession
    llm: LLMProvider
    analysis_run: AnalysisRun
    project: Project
    product: Product | None
    master_prompt: str
    model: str
    """Default/fallback model, recorded on the analysis run for reporting.
    Individual stages use extraction_model/synthesis_model/citation_model
    below when those are configured, falling back to this one otherwise."""
    extraction_model: str
    synthesis_model: str
    citation_model: str
    privacy: dict
    chunk_lookup: dict[str, RetrievedChunk]
    prior_outputs: dict


def _project_facts(project: Project, product: Product | None) -> dict:
    facts = {
        "project_name": project.name,
        "jurisdiction": project.jurisdiction,
        "target_payers": project.target_payers,
        "analysis_scope": project.analysis_scope,
    }
    if product:
        facts["product"] = {
            "name": product.name,
            "product_type": product.product_type,
            "regulatory_stage": product.regulatory_stage,
            "fda_status": product.fda_status,
            "intended_use": product.intended_use,
            "indications_for_use": product.indications_for_use,
            "target_population": product.target_population,
            "intended_user": product.intended_user,
            "site_of_service": product.site_of_service,
            "care_setting": product.care_setting,
            "clinical_output": product.clinical_output,
            "ai_role": product.ai_role,
            "hardware_version": product.hardware_version,
            "software_version": product.software_version,
        }
    else:
        facts["product"] = "[INPUT REQUIRED: no product selected for this project]"
    return facts


def _redact_chunk_text(chunk: RetrievedChunk, privacy: dict) -> RetrievedChunk:
    redacted_text = apply_redaction(
        chunk.text,
        redact_emails_enabled=privacy.get("redact_emails", True),
        redact_phones_enabled=privacy.get("redact_phone_numbers", True),
        redact_patient_ids_enabled=privacy.get("redact_patient_identifiers", True),
    )
    if redacted_text == chunk.text:
        return chunk
    return RetrievedChunk(**{**chunk.__dict__, "text": redacted_text})


async def _retrieve(
    ctx: StageContext, query: str, *, collection_types: list[CollectionType] | None = None, top_k: int = 12
) -> list[RetrievedChunk]:
    if ctx.privacy.get("exclude_restricted_documents", True):
        pass  # hybrid_search already excludes RESTRICTED confidentiality by default
    filters = RetrievalFilter(project_id=ctx.project.id, collection_types=collection_types)
    chunks = await hybrid_search(ctx.db, query, filters, top_k=top_k)
    chunks = [_redact_chunk_text(c, ctx.privacy) for c in chunks]
    for chunk in chunks:
        ctx.chunk_lookup[chunk.citation_label] = chunk
    return chunks


def _prior_outputs_for_stage(stage_name: str, prior_outputs: dict) -> dict:
    """Curates which of the accumulated prior-stage outputs a given stage
    actually needs, instead of forwarding the ever-growing full run history
    to every call -- a real, measured cost driver (see docs/data-model.md):
    without this, the last stage of an 11-stage run pays for the JSON of
    every stage before it, on top of the master prompt repetition. Synthesis
    is the deliberate exception: it genuinely needs the whole picture to
    produce a coherent overall verdict."""

    def pick(*keys: str) -> dict:
        return {k: prior_outputs[k] for k in keys if k in prior_outputs}

    if stage_name == "product_fact_extraction":
        return pick("input_audit")
    if stage_name == "claim_extraction":
        return pick("product_facts")
    if stage_name == "coding_analysis":
        return pick("product_facts")
    if stage_name == "domain_analysis":
        return pick("product_facts", "coding", "claims")
    if stage_name == "synthesis":
        return dict(prior_outputs)
    if stage_name == "citation_audit":
        return pick("findings_for_audit")
    return {}  # input_audit: the first stage, nothing to hand it yet


async def _call_stage(
    ctx: StageContext,
    *,
    stage_name: str,
    module_prompt: str,
    evidence_chunks: list[RetrievedChunk],
    schema_model,
    max_tokens: int = 8000,
    model: str | None = None,
):
    schema = schema_model.model_json_schema()
    system_prompt, messages = compose_messages(
        master_prompt=ctx.master_prompt,
        module_prompt=module_prompt,
        project_facts=_project_facts(ctx.project, ctx.product),
        evidence_chunks=evidence_chunks,
        prior_stage_outputs=_prior_outputs_for_stage(stage_name, ctx.prior_outputs),
        enable_prompt_caching=ctx.privacy.get("openrouter_prompt_caching", True),
    )
    result = await ctx.llm.structured_completion(
        system_prompt=system_prompt,
        messages=messages,
        schema=schema,
        schema_name=stage_name,
        model=model or ctx.model,
        temperature=0,
        max_tokens=max_tokens,
    )
    parsed = schema_model.model_validate(result.content)
    ctx.analysis_run.token_usage_json = {
        **ctx.analysis_run.token_usage_json,
        stage_name: {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
        },
    }
    if result.cost_usd is not None:
        ctx.analysis_run.cost_json = {**ctx.analysis_run.cost_json, stage_name: result.cost_usd}
    ctx.analysis_run.model_response_identifier = result.model_response_identifier
    return parsed, result


def _resolve_citations(
    labels: list[str], chunk_lookup: dict[str, RetrievedChunk], role: CitationRole
) -> list[Citation]:
    citations = []
    for label in labels:
        chunk = chunk_lookup.get(label)
        citations.append(
            Citation(
                document_id=chunk.document_id if chunk else None,
                chunk_id=chunk.chunk_id if chunk else None,
                citation_role=role,
                quoted_text=chunk.text[:2000] if chunk else None,
                page_number=chunk.page_number if chunk else None,
                section_title=chunk.heading_path if chunk else None,
                # Always resolved from the retrieved chunk's actual source
                # document (crawled URL or manually-verified authority-library
                # URL) -- the model never supplies a URL itself.
                url=chunk.document_url if chunk else None,
                supports_claim=True,
            )
        )
    return citations


def _safe_enum(enum_cls, value: str, default):
    try:
        return enum_cls(value)
    except ValueError:
        logger.warning("Model returned unrecognized %s value %r; defaulting to %r", enum_cls.__name__, value, default)
        return default


async def _persist_domain_findings(ctx: StageContext, domain: FindingDomain, domain_result: DomainAnalysisResult) -> None:
    # The stage's target domain is already known from DOMAIN_STAGES -- use
    # that rather than trusting the model's free-text "domain" field, which
    # exists in the schema for the model's own bookkeeping/summary purposes
    # but is not authoritative for how the finding gets filed.
    for item in domain_result.findings:
        finding = Finding(
            analysis_run_id=ctx.analysis_run.id,
            domain=domain,
            title=item.title,
            description=item.description,
            finding_type=item.finding_type or None,
            status=_safe_enum(EvidenceStatus, item.status, EvidenceStatus.UNRESOLVED).value,
            risk=_safe_enum(RiskLevel, item.risk, RiskLevel.MEDIUM),
            verdict=_safe_enum(Verdict, item.verdict, None) if item.verdict else None,
            verified_fact=item.verified_fact or None,
            missing_information=item.missing_information,
            applicable_requirement=item.applicable_requirement or None,
            recommended_action=item.recommended_action or None,
            responsible_owner=item.responsible_owner or None,
            priority=item.priority,
            due_timing=item.due_timing or None,
            confidence=item.confidence,
            human_review_required=item.human_review_required,
        )
        ctx.db.add(finding)
        await ctx.db.flush()
        for citation in _resolve_citations(item.company_citation_labels, ctx.chunk_lookup, CitationRole.COMPANY_EVIDENCE):
            citation.finding_id = finding.id
            ctx.db.add(citation)
        for citation in _resolve_citations(
            item.authority_citation_labels, ctx.chunk_lookup, CitationRole.CONTROLLING_AUTHORITY
        ):
            citation.finding_id = finding.id
            ctx.db.add(citation)
    await ctx.db.commit()


DOMAIN_STAGES = [
    ("regulatory_analysis", FindingDomain.FDA_REGULATORY, "FDA regulatory pathway, intended use, indications, clearance/approval status, quality system, cybersecurity, human factors, postmarket obligations"),
    ("coverage_analysis", FindingDomain.COVERAGE, "Medicare and commercial payer coverage: NCD, LCD, benefit category, medical necessity, patient and provider criteria"),
    ("payment_analysis", FindingDomain.PAYMENT, "Physician Fee Schedule, OPPS/APC, IPPS/MS-DRG, NTAP, ASC, DMEPOS payment rates and methodology"),
    ("billing_analysis", FindingDomain.BILLING, "billing workflow: patient eligibility, consent, setup, data capture, monitoring, documentation, claim submission"),
    ("marketing_analysis", FindingDomain.MARKETING, "public marketing claims compared against regulatory status, intended use, evidence, and commercial status"),
]

# Cost optimization: the 5 domain stages above don't depend on each other's
# output (each independently reads product facts / coding / claims), so they
# don't need 5 separate calls, each re-paying for the master prompt. One
# combined call, using the union of each domain's targeted evidence
# retrieval, produces all 5 -- see CombinedDomainAnalysisResult and
# docs/data-model.md for the cost analysis this is based on.
COMBINED_DOMAIN_MAX_TOKENS = 28000


def _build_combined_domain_module_prompt() -> str:
    sections = [
        f"## Domain: {stage_name}\n\n{load_module_prompt(stage_name)}" for stage_name, _, _ in DOMAIN_STAGES
    ]
    return (
        "# Module Prompt — Combined Domain Analysis\n\n"
        "You are operating beneath the active compliance master system prompt, which remains "
        "controlling. Below are five separate domain-analysis module prompts. Analyze all five "
        "in this single response, producing a complete result for each in the correspondingly "
        "named output field (regulatory_analysis, coverage_analysis, payment_analysis, "
        "billing_analysis, marketing_analysis). Do not let a finding discovered while reading "
        "evidence for one domain leak into another domain's field -- e.g. a billing-workflow gap "
        "belongs only in billing_analysis, even if it was noticed while reading evidence retrieved "
        "for regulatory_analysis. Each domain's findings must still cite only evidence relevant to "
        "that domain's own claims.\n\n" + "\n\n---\n\n".join(sections)
    )


async def _retrieve_combined_domain_evidence(ctx: StageContext) -> list[RetrievedChunk]:
    # Each domain keeps its own targeted retrieval query (retrieval quality
    # per domain is unaffected by the call-merging above) but at a reduced
    # top_k, since all 5 domains' evidence now shares one call's context
    # instead of each getting its own; de-duplicated by citation_label so a
    # chunk relevant to more than one domain isn't sent twice.
    seen: dict[str, RetrievedChunk] = {}
    for _, _, focus_query in DOMAIN_STAGES:
        for chunk in await _retrieve(ctx, focus_query, top_k=10):
            seen[chunk.citation_label] = chunk
    return list(seen.values())


def _resolve_stage_models(model: str, privacy: dict) -> tuple[str, str, str]:
    """Cost lever: input_audit/product_fact_extraction/claim_extraction/
    coding_analysis/citation_audit are comparatively mechanical extraction
    tasks -- a cheap/fast model handles them fine. domain_analysis and
    synthesis are where the actual compliance reasoning happens, so they
    stay on the stronger default model unless a synthesis-tier override is
    set. Any tier left unset in Settings falls back to the one model
    everyone already configures, so this is a no-op until the user opts in.
    Returns (extraction_model, synthesis_model, citation_model)."""
    return (
        privacy.get("openrouter_extraction_model") or model,
        privacy.get("openrouter_synthesis_model") or model,
        privacy.get("openrouter_citation_model") or model,
    )


async def run_analysis(db: AsyncSession, analysis_run: AnalysisRun, llm: LLMProvider, model: str) -> None:
    project = await db.get(Project, analysis_run.project_id)
    product = await db.get(Product, analysis_run.product_id) if analysis_run.product_id else None
    master_prompt_version = await get_active_master_prompt(db)
    analysis_run.system_prompt_version_id = master_prompt_version.id
    analysis_run.analysis_model = model
    analysis_run.started_at = datetime.now(timezone.utc)
    analysis_run.source_cutoff_date = date.today()
    await db.commit()

    privacy = load_runtime_settings()
    extraction_model, synthesis_model, citation_model = _resolve_stage_models(model, privacy)
    ctx = StageContext(
        db=db,
        llm=llm,
        analysis_run=analysis_run,
        project=project,
        product=product,
        master_prompt=master_prompt_version.content,
        model=model,
        extraction_model=extraction_model,
        synthesis_model=synthesis_model,
        citation_model=citation_model,
        privacy=privacy,
        chunk_lookup={},
        prior_outputs={},
    )

    async def set_stage(name: str) -> None:
        # Cooperative cancellation, same pattern as the crawler
        # (app/services/crawling/crawler.py): re-read just the status column
        # since POST /analyses/{id}/cancel updates it from a different
        # session/request that this in-memory object won't otherwise see.
        current_status = await db.scalar(select(AnalysisRun.status).where(AnalysisRun.id == analysis_run.id))
        if current_status == JobStatus.CANCELLED:
            raise AnalysisCancelled()
        ctx.analysis_run.current_stage = name
        await db.commit()

    # Stage 1 — Input audit
    await set_stage("input_audit")
    chunks = await _retrieve(ctx, "product overview intended use regulatory status evidence", top_k=15)
    input_audit, _ = await _call_stage(
        ctx, stage_name="input_audit", module_prompt=INPUT_AUDIT_MODULE_PROMPT,
        evidence_chunks=chunks, schema_model=InputAuditResult, model=ctx.extraction_model,
    )
    ctx.prior_outputs["input_audit"] = input_audit.model_dump()
    await db.commit()

    # Stage 2 — Product fact extraction. Includes THIRD_PARTY/COMPETITOR
    # evidence, not just COMPANY: for a public-product evaluation (e.g. a
    # competitor or an established third-party device), the only evidence
    # available may be secondary literature rather than the company's own
    # materials -- per the master prompt's neutrality rule, that's a
    # legitimate Level 5 source to extract provisional facts from, not a
    # reason to retrieve nothing and fall back to all-MISSING.
    await set_stage("product_fact_extraction")
    chunks = await _retrieve(
        ctx, "product components intended function hardware software specifications FDA status",
        collection_types=[CollectionType.COMPANY, CollectionType.THIRD_PARTY, CollectionType.COMPETITOR],
        top_k=15,
    )
    facts, _ = await _call_stage(
        ctx, stage_name="product_fact_extraction", module_prompt=load_module_prompt("product_fact_extraction"),
        evidence_chunks=chunks, schema_model=ProductFactExtractionResult, model=ctx.extraction_model,
    )
    ctx.prior_outputs["product_facts"] = facts.model_dump()
    await db.commit()

    # Stages 3-4 — Claim extraction and coding analysis. Both depend only on
    # product_facts (already produced above), not on each other, so their
    # LLM calls run concurrently to cut wall-clock time -- retrieval and DB
    # writes stay strictly sequential on the shared session/connection
    # (AsyncSession is not safe for concurrent use), only the two
    # structured_completion network calls actually overlap.
    await set_stage("claim_extraction_and_coding")
    claim_chunks = await _retrieve(
        ctx, "website marketing claims performance safety effectiveness pricing availability",
        collection_types=[CollectionType.COMPANY], top_k=20,
    )
    coding_chunks = await _retrieve(ctx, "CPT HCPCS ICD coding billing code eligibility RPM RTM Category III device", top_k=15)

    (claims, _), (coding_result, _) = await asyncio.gather(
        _call_stage(
            ctx, stage_name="claim_extraction", module_prompt=load_module_prompt("claim_extraction"),
            evidence_chunks=claim_chunks, schema_model=ClaimExtractionResult, max_tokens=12000,
            model=ctx.extraction_model,
        ),
        _call_stage(
            ctx, stage_name="coding_analysis", module_prompt=load_module_prompt("coding_analysis"),
            evidence_chunks=coding_chunks, schema_model=CodingEligibilityResult, max_tokens=12000,
            model=ctx.extraction_model,
        ),
    )

    ctx.prior_outputs["claims"] = claims.model_dump()
    for claim in claims.claims:
        source_chunk = ctx.chunk_lookup.get(claim.citation_labels[0]) if claim.citation_labels else None
        db.add(
            ExtractedClaim(
                project_id=project.id,
                source_document_id=source_chunk.document_id if source_chunk else None,
                source_chunk_id=source_chunk.chunk_id if source_chunk else None,
                exact_text=claim.exact_text,
                claim_category=_safe_enum(ClaimCategory, claim.claim_category, ClaimCategory.PRODUCT_CONFIGURATION),
                express_or_implied=_safe_enum(ExpressOrImplied, claim.express_or_implied, ExpressOrImplied.EXPRESS),
                audience=claim.audience or None,
                evidence_status=_safe_enum(EvidenceStatus, claim.evidence_status, EvidenceStatus.UNRESOLVED),
                intended_use_alignment=claim.intended_use_alignment or None,
                regulatory_status_alignment=claim.regulatory_status_alignment or None,
                risk=_safe_enum(RiskLevel, claim.risk, RiskLevel.MEDIUM),
                recommended_disposition=_safe_enum(ClaimDisposition, claim.recommended_disposition, ClaimDisposition.QUALIFY),
                proposed_replacement=claim.proposed_replacement or None,
            )
        )
    await db.commit()

    # Stages 5-9 — domain analyses (regulatory, coverage, payment, billing, marketing).
    # coding_analysis's own result (from the concurrent call above) is persisted here.
    ctx.prior_outputs["coding"] = coding_result.model_dump()
    for candidate_item in coding_result.candidates:
        candidate = CodingCandidate(
            analysis_run_id=analysis_run.id,
            code_system=candidate_item.code_system,
            code=candidate_item.code or None,
            code_year=candidate_item.code_year or None,
            descriptor_reference=candidate_item.descriptor_reference or None,
            service_definition=candidate_item.service_definition,
            eligibility_status=_safe_enum(
                CodingEligibilityStatus, candidate_item.eligibility_status, CodingEligibilityStatus.EXPERT_REVIEW_REQUIRED
            ),
            coverage_status=candidate_item.coverage_status or None,
            payment_status=candidate_item.payment_status or None,
            billing_status=candidate_item.billing_status or None,
            major_gaps=candidate_item.major_gaps,
            expert_review_required=candidate_item.expert_review_required,
        )
        db.add(candidate)
        await db.flush()
        for req in candidate_item.requirements:
            company_chunk = next((ctx.chunk_lookup.get(l) for l in req.company_citation_labels if ctx.chunk_lookup.get(l)), None)
            authority_chunk = next((ctx.chunk_lookup.get(l) for l in req.authority_citation_labels if ctx.chunk_lookup.get(l)), None)
            db.add(
                CodingRequirement(
                    coding_candidate_id=candidate.id,
                    requirement_name=req.requirement_name,
                    requirement_text=req.requirement_text,
                    verified_company_fact=req.verified_company_fact or None,
                    status=_safe_enum(EvidenceStatus, req.status, EvidenceStatus.UNRESOLVED).value,
                    company_source_id=company_chunk.document_id if company_chunk else None,
                    authority_source_id=authority_chunk.document_id if authority_chunk else None,
                    gap=req.gap or None,
                    owner=req.owner or None,
                )
            )
    await db.commit()

    await set_stage("domain_analysis")
    combined_chunks = await _retrieve_combined_domain_evidence(ctx)
    combined_result, _ = await _call_stage(
        ctx, stage_name="domain_analysis", module_prompt=_build_combined_domain_module_prompt(),
        evidence_chunks=combined_chunks, schema_model=CombinedDomainAnalysisResult,
        max_tokens=COMBINED_DOMAIN_MAX_TOKENS,
    )
    for stage_name, domain, _ in DOMAIN_STAGES:
        domain_result: DomainAnalysisResult = getattr(combined_result, stage_name)
        ctx.prior_outputs[stage_name] = domain_result.model_dump()
        await _persist_domain_findings(ctx, domain, domain_result)

    # Stage 10 — synthesis
    await set_stage("synthesis")
    synthesis, _ = await _call_stage(
        ctx, stage_name="synthesis", module_prompt=load_module_prompt("synthesis"),
        evidence_chunks=[], schema_model=OverallAnalysisResult, model=ctx.synthesis_model,
    )
    analysis_run.overall_verdict = _safe_enum(Verdict, synthesis.overall_verdict, Verdict.STOP)
    analysis_run.overall_risk = _safe_enum(RiskLevel, synthesis.overall_risk, RiskLevel.HIGH)

    existing_findings = (
        await db.execute(select(Finding.risk, Finding.status).where(Finding.analysis_run_id == analysis_run.id))
    ).all()
    final_score, score_note = apply_readiness_score_guardrail(
        model_score=synthesis.readiness_score,
        overall_verdict=analysis_run.overall_verdict,
        overall_risk=analysis_run.overall_risk,
        finding_risks=[risk for risk, _ in existing_findings],
        finding_statuses=[status for _, status in existing_findings],
    )
    analysis_run.readiness_score = final_score
    analysis_run.readiness_score_note = score_note
    analysis_run.confidence_score = synthesis.confidence_score
    analysis_run.executive_summary = synthesis.executive_summary
    analysis_run.critical_blockers = synthesis.critical_blockers
    analysis_run.missing_inputs = synthesis.missing_inputs
    analysis_run.priority_actions = synthesis.priority_actions
    analysis_run.required_reviewers = synthesis.required_reviewers
    await db.commit()

    # Stage 11 — citation audit (validates, does not add new substantive findings)
    await set_stage("citation_audit")
    await _run_citation_audit(ctx)

    # Reconcile this run's findings against the product's durable compliance
    # checklist (user-requested: see what's newly resolved vs. still open
    # after a small incremental change, without a whole new report). Only
    # meaningful when a product is actually selected for this analysis.
    if product is not None:
        await reconcile_compliance_issues(db, product.id, analysis_run.id)

    ctx.analysis_run.current_stage = "complete"
    await db.commit()


async def _run_citation_audit(ctx: StageContext) -> None:
    from app.schemas.analysis_llm import CitationAuditResult

    result = await ctx.db.execute(select(Finding).where(Finding.analysis_run_id == ctx.analysis_run.id))
    findings = list(result.scalars().all())
    if not findings:
        return

    findings_summary = [
        {
            "id": str(f.id),
            "title": f.title,
            "domain": f.domain.value,
            "status": f.status,
            "has_citations": bool((await ctx.db.execute(select(Citation).where(Citation.finding_id == f.id))).first()),
        }
        for f in findings
    ]
    ctx.prior_outputs["findings_for_audit"] = findings_summary

    audit_prompt = load_module_prompt("citation_audit")
    audit_result, _ = await _call_stage(
        ctx, stage_name="citation_audit", module_prompt=audit_prompt,
        evidence_chunks=[], schema_model=CitationAuditResult, model=ctx.citation_model,
    )

    findings_by_title = {f.title: f for f in findings}
    for entry in audit_result.entries:
        if entry.passed:
            continue
        finding = findings_by_title.get(entry.finding_title)
        if finding is None:
            continue
        finding.status = entry.downgrade_to_status or "UNRESOLVED"
        finding.human_review_required = True
    await ctx.db.commit()
