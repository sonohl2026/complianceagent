"""Code-side scoring enforcement (v2 spec §3) -- "belt-and-suspenders... do
NOT trust the model alone." Every function here is pure (no I/O, no model
calls) so each of the 5 rules is independently unit-testable without an LLM
or network involved.
"""

from app.services.evidence_retrieval.orchestrator import EvidenceBundle
from app.services.evidence_retrieval.types import RetrievalStatus
from app.services.quick_scan.schemas import Pillar, QuickScanAssessment, Scores

_ASSESSED_STATUSES = {"VERIFIED_POSITIVE", "VERIFIED_NEGATIVE", "MIXED"}
_MIN_ASSESSED_PILLARS = 3
_MATURITY_DISAGREEMENT_THRESHOLD = 5
_CONFIDENCE_CAP_ON_RETRIEVAL_FAILURE = 60
_REGULATORY_IDENTITY_SOURCES = ("openfda_510k", "openfda_pma", "openfda_classification")


def _assessed_pillars(pillars: list[Pillar]) -> list[Pillar]:
    return [p for p in pillars if p.status in _ASSESSED_STATUSES]


def enforce_fda_status_from_verified_hit(pillars: list[Pillar], evidence: EvidenceBundle) -> list[Pillar]:
    """A genuine, exact-confidence 510(k)/PMA/classification hit is
    definitive proof the device has an FDA regulatory record -- not a
    judgment call (confirmed empirically: Stage 3 is deterministic 14/14
    times given fixed evidence including such a hit; the real-world
    instability traced back to upstream evidence-shape variance between
    runs, not Stage 3 misjudging a fixed shape -- see conversation record).
    If Stage 3 still left fda_status UNKNOWN/NA despite an exact hit
    existing, promote it in code rather than leave a whole run's
    SCORED/NOT_SCORED outcome hostage to that one inconsistency, since
    fda_status being assessed gates all scoring (enforce_not_scored below).

    Deliberately narrow: never overrides a status Stage 3 already committed
    to (VERIFIED_POSITIVE/VERIFIED_NEGATIVE/MIXED pass through untouched --
    this only rescues UNKNOWN/NA), and only trusts an "exact" match, not a
    "probable" one (e.g. the openFDA manufacturer-name fallback) -- that
    weaker signal genuinely is closer to a judgment call."""
    fda_pillar = next(p for p in pillars if p.pillar == "fda_status")
    if fda_pillar.status not in ("UNKNOWN", "NA"):
        return pillars

    hit_source = next(
        (
            name for name in _REGULATORY_IDENTITY_SOURCES
            if (e := evidence.sources.get(name)) and e.status == RetrievalStatus.HIT and e.match_confidence == "exact"
        ),
        None,
    )
    if hit_source is None:
        return pillars

    promoted = fda_pillar.model_copy(update={
        "status": "VERIFIED_POSITIVE",
        "score": fda_pillar.score if fda_pillar.score is not None else 70,
        "finding": f"Confirmed FDA regulatory record found ({hit_source.replace('openfda_', '')}).",
        "gap": "Synthesis left this UNKNOWN despite a confirmed regulatory record existing -- code-side correction applied.",
    })
    return [promoted if p.pillar == "fda_status" else p for p in pillars]


def recompute_maturity(pillars: list[Pillar]) -> int | None:
    """Rule 1: mean of score over assessed-only pillars. UNKNOWN/NA/
    RETRIEVAL_FAILURE pillars are dropped from numerator AND denominator --
    not treated as 0, not treated as excluded-but-still-penalizing."""
    assessed = [p for p in _assessed_pillars(pillars) if p.score is not None]
    if not assessed:
        return None
    return round(sum(p.score for p in assessed) / len(assessed))


def enforce_not_scored(pillars: list[Pillar], maturity: int | None) -> tuple[int | None, str, str | None]:
    """Rule 2: fewer than 3 assessed pillars, or the fda_status pillar itself
    not assessed, forces NOT_SCORED with a null numeric maturity -- this is
    the rule that makes fixture #10's "everything failed" case, and any
    thin-evidence case, come back NOT_SCORED instead of a low or zero
    number. Returns (maturity, maturity_state, not_scored_reason)."""
    assessed = _assessed_pillars(pillars)
    fda_status_assessed = any(p.pillar == "fda_status" and p.status in _ASSESSED_STATUSES for p in pillars)
    if len(assessed) < _MIN_ASSESSED_PILLARS or not fda_status_assessed:
        return None, "NOT_SCORED", "INSUFFICIENT_DATA_RETRIEVED"
    return maturity, "SCORED", None


def recompute_coverage_pct(pillars: list[Pillar]) -> int:
    """Rule 3: share of the 6 pillars assessed -- "we didn't have enough
    info" lives here, never folded into maturity."""
    return round(100 * len(_assessed_pillars(pillars)) / 6)


def clamp_research_confidence(confidence: int, evidence: EvidenceBundle) -> int:
    """Rule 4: capped at 60 if EITHER government source failed entirely
    (not just individual sub-endpoints -- e.g. one openFDA endpoint timing
    out while six others succeed is not "openFDA failed")."""
    if evidence.all_openfda_failed or evidence.all_cms_failed:
        return min(confidence, _CONFIDENCE_CAP_ON_RETRIEVAL_FAILURE)
    return confidence


def enforce(assessment: QuickScanAssessment, evidence: EvidenceBundle) -> QuickScanAssessment:
    """Applies all §3 rules in order, in code, regardless of what the model
    itself reported. Rule 5 (risk-flag independence) isn't a transform here --
    it's the invariant that risk_flag is never read by any of the functions
    above, so it structurally cannot influence the recomputed maturity;
    tests assert this by constructing two assessments identical except
    risk_flag and confirming enforce() produces identical maturity."""
    pillars = enforce_fda_status_from_verified_hit(assessment.pillars, evidence)

    recomputed = recompute_maturity(pillars)
    model_reported = assessment.scores.maturity
    if (
        model_reported is not None
        and recomputed is not None
        and abs(model_reported - recomputed) > _MATURITY_DISAGREEMENT_THRESHOLD
    ):
        maturity = recomputed
    else:
        maturity = recomputed if recomputed is not None else model_reported

    maturity, maturity_state, not_scored_reason = enforce_not_scored(pillars, maturity)
    if evidence.force_not_scored:
        maturity, maturity_state, not_scored_reason = None, "NOT_SCORED", "INSUFFICIENT_DATA_RETRIEVED"

    coverage_pct = recompute_coverage_pct(pillars)
    confidence = clamp_research_confidence(assessment.scores.research_confidence, evidence)

    new_scores = Scores(
        maturity=maturity,
        maturity_state=maturity_state,
        not_scored_reason=not_scored_reason,
        assessment_coverage_pct=coverage_pct,
        research_confidence=confidence,
        risk_flag=assessment.scores.risk_flag,  # untouched by any rule above -- rule 5
        stage_context=assessment.scores.stage_context,
    )
    return assessment.model_copy(update={"scores": new_scores, "pillars": pillars})
