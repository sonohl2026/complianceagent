"""Structured I/O schemas for the quick_scan pipeline (v2 spec §0, §4).

Follows the same strict-schema convention as app/schemas/analysis_llm.py:
extra="forbid" so model_json_schema() emits additionalProperties: false, and
integer fields deliberately avoid Field(ge=, le=) since some providers behind
OpenRouter reject minimum/maximum keywords on integer types outright.
"""

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class Stage1Extraction(BaseModel):
    """Stage 1 output (spec §0): identifies the product from thin/uploaded
    text. This is a CLUE for Stage 2 retrieval, not the evidence itself --
    see system_prompt_v2.md's "ONE RULE"."""

    model_config = _STRICT
    product_name: str
    manufacturer: str = Field(description="'' if not stated or not determinable")
    aliases: list[str] = Field(description="Other names/model numbers the product is known by")
    intended_use: str
    technology_type: str = Field(description="e.g. 'implantable cardiac device', 'AI diagnostic software', 'CGM'")
    dev_stage_guess: str = Field(
        description="concept | investigational | submission_pending | authorized_prelaunch | commercial | restricted_or_recalled | unknown"
    )
    candidate_search_terms: list[str] = Field(
        description="Procedure/condition keywords for CMS Coverage search (services, not brand names) -- e.g. "
        "'transcatheter aortic valve replacement', 'continuous glucose monitor'"
    )


class CandidateCodesResponse(BaseModel):
    """Output of the candidate-code-proposal step (fee-schedule lookup --
    see app/services/quick_scan/code_candidates.py). A hypothesis only:
    every candidate is verified against real, current PFS data before it's
    ever trusted -- see that module's verify_candidates()."""

    model_config = _STRICT
    candidate_codes: list[str] = Field(description="Plausible CPT/HCPCS codes for this device's procedure/supply category, or [] if none plausible")


class Identifier(BaseModel):
    model_config = _STRICT
    type: str = Field(description="510k | pma | denovo | product_code | udi | ncd | lcd | cpt | hcpcs")
    value: str
    match_confidence: str = Field(description="exact | probable | uncertain")


class ProductIdentity(BaseModel):
    model_config = _STRICT
    name: str
    manufacturer: str
    fda_status: str
    identifiers: list[Identifier]
    dev_stage: str = Field(
        description="concept | investigational | submission_pending | authorized_prelaunch | commercial | restricted_or_recalled"
    )


class Scores(BaseModel):
    model_config = _STRICT
    maturity: int | None = Field(description="0-100, or null when maturity_state is NOT_SCORED")
    maturity_state: str = Field(description="SCORED | NOT_SCORED")
    not_scored_reason: str | None = Field(description="e.g. 'INSUFFICIENT_DATA_RETRIEVED', or null when SCORED")
    assessment_coverage_pct: int = Field(description="0-100")
    research_confidence: int = Field(description="0-100")
    risk_flag: str = Field(description="LOW | MEDIUM | HIGH | CRITICAL")
    stage_context: str = Field(description="max 300 chars: on-track/ahead/behind + absolute readiness, one sentence each")


class Pillar(BaseModel):
    model_config = _STRICT
    pillar: str = Field(description="fda_status | coding | coverage | payment | evidence | billing_workflow")
    status: str = Field(description="VERIFIED_POSITIVE | VERIFIED_NEGATIVE | MIXED | UNKNOWN | NA | RETRIEVAL_FAILURE")
    score: int | None = Field(description="0-100, or null when status is UNKNOWN/NA/RETRIEVAL_FAILURE")
    finding: str = Field(max_length=250, description="max 200 chars, one sentence")
    # Was "max 800 chars" (hint-only, no real constraint -- spec §4 actually
    # specifies maxLength:800 as a real JSON Schema keyword; this had drifted
    # to a description-text hint the model wasn't structurally held to).
    # Measured: detail carried 40% of total Stage-3 output chars across a
    # real 9-fixture sample, the single largest lever on output size/latency/
    # cost. Tightened to a real 400-char *target* (stated in the hint, which
    # the model empirically follows -- it was already averaging well under
    # the old 800 hint on its own) with a genuine max_length=500 backstop
    # (25% headroom) so an overshoot fails Pydantic validation and triggers
    # the existing one-repair-pass path instead of silently ignoring it.
    detail: str = Field(max_length=500, description="max 400 chars, nuance goes here -- 1-2 sentences, not a paragraph")
    citation: str | None = Field(description="URL from the evidence bundle only, or null")
    gap: str | None = Field(max_length=250, description="max 200 chars, one sentence, or null")
    action: str | None = Field(description="PROCEED | FIX | INVESTIGATE | null")


class QuickScanAssessment(BaseModel):
    """Final Stage-3 output shape, matching v2 spec §4 exactly (pre-code-side-
    enforcement; see scoring_enforcement.py for the post-processing pass that
    may override values here before persistence)."""

    model_config = _STRICT
    product: ProductIdentity
    scores: Scores
    pillars: list[Pillar] = Field(description="Exactly 6, one per pillar, fixed order: fda_status, coding, coverage, payment, evidence, billing_workflow")
    top_gaps: list[str] = Field(description="Max 5 items")
    next_steps: list[str] = Field(description="Max 5 items")
    disclaimer: str
