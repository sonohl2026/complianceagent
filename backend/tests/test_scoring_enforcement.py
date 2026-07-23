from app.services.evidence_retrieval.orchestrator import EvidenceBundle
from app.services.evidence_retrieval.types import RetrievalStatus, SourceEvidence
from app.services.quick_scan.scoring_enforcement import (
    clamp_research_confidence,
    enforce,
    enforce_coding_from_verified_fee_schedule_hit,
    enforce_fda_status_from_verified_hit,
    enforce_not_scored,
    recompute_coverage_pct,
    recompute_maturity,
)
from app.services.quick_scan.schemas import Pillar, ProductIdentity, QuickScanAssessment, Scores

_PILLAR_NAMES = ["fda_status", "coding", "coverage", "payment", "evidence", "billing_workflow"]


def _pillar(name: str, status: str, score: int | None) -> Pillar:
    return Pillar(pillar=name, status=status, score=score, finding="f", detail="d", citation=None, gap=None, action=None)


def _no_failure_bundle() -> EvidenceBundle:
    return EvidenceBundle(sources={}, all_openfda_failed=False, all_cms_failed=False)


def _assessment(pillars: list[Pillar], *, maturity: int | None, risk_flag: str = "LOW") -> QuickScanAssessment:
    return QuickScanAssessment(
        product=ProductIdentity(name="X", manufacturer="Y", fda_status="cleared", identifiers=[], dev_stage="commercial"),
        scores=Scores(
            maturity=maturity, maturity_state="SCORED", not_scored_reason=None,
            assessment_coverage_pct=100, research_confidence=80, risk_flag=risk_flag, stage_context="on-track",
        ),
        pillars=pillars,
        top_gaps=[], next_steps=[], disclaimer="Informational market-access analysis only.",
    )


def _all_assessed_pillars(scores: list[int]) -> list[Pillar]:
    return [_pillar(name, "VERIFIED_POSITIVE", score) for name, score in zip(_PILLAR_NAMES, scores)]


def _bundle_with_source(source: str, status: RetrievalStatus, match_confidence: str | None) -> EvidenceBundle:
    return EvidenceBundle(
        sources={source: SourceEvidence(source=source, status=status, latency_ms=100, match_confidence=match_confidence)},
        all_openfda_failed=False, all_cms_failed=False,
    )


# --- fda_status-from-verified-hit rule (added after real-run testing found
# fixture 5 flipping SCORED/NOT_SCORED run-to-run; see plan doc) ---

def test_unknown_fda_status_promoted_by_exact_510k_hit():
    pillars = [_pillar("fda_status", "UNKNOWN", None)] + [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES[1:]]
    bundle = _bundle_with_source("openfda_510k", RetrievalStatus.HIT, "exact")
    result = enforce_fda_status_from_verified_hit(pillars, bundle)
    fda = next(p for p in result if p.pillar == "fda_status")
    assert fda.status == "VERIFIED_POSITIVE"
    assert fda.score == 70
    assert "510k" in fda.finding


def test_unknown_fda_status_promoted_by_exact_pma_or_classification_hit():
    for source in ("openfda_pma", "openfda_classification"):
        pillars = [_pillar("fda_status", "NA", None)] + [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES[1:]]
        bundle = _bundle_with_source(source, RetrievalStatus.HIT, "exact")
        result = enforce_fda_status_from_verified_hit(pillars, bundle)
        assert next(p for p in result if p.pillar == "fda_status").status == "VERIFIED_POSITIVE"


def test_unknown_fda_status_not_promoted_by_probable_hit():
    pillars = [_pillar("fda_status", "UNKNOWN", None)] + [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES[1:]]
    bundle = _bundle_with_source("openfda_510k", RetrievalStatus.HIT, "probable")
    result = enforce_fda_status_from_verified_hit(pillars, bundle)
    assert next(p for p in result if p.pillar == "fda_status").status == "UNKNOWN"


def test_unknown_fda_status_not_promoted_with_no_hit_at_all():
    pillars = [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES]
    result = enforce_fda_status_from_verified_hit(pillars, _no_failure_bundle())
    assert next(p for p in result if p.pillar == "fda_status").status == "UNKNOWN"


def test_already_assessed_fda_status_never_second_guessed():
    for status in ("VERIFIED_POSITIVE", "VERIFIED_NEGATIVE", "MIXED"):
        pillars = [_pillar("fda_status", status, 40)] + [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES[1:]]
        bundle = _bundle_with_source("openfda_510k", RetrievalStatus.HIT, "exact")
        result = enforce_fda_status_from_verified_hit(pillars, bundle)
        fda = next(p for p in result if p.pillar == "fda_status")
        assert fda.status == status
        assert fda.score == 40  # untouched, not re-scored to 70


def test_enforce_end_to_end_promotes_fda_status_and_rescues_scoring():
    # The real failure mode this closes: fda_status UNKNOWN despite a
    # confirmed hit meant enforce_not_scored forced the whole run to
    # NOT_SCORED even with 3 other pillars genuinely assessed.
    pillars = [
        _pillar("fda_status", "UNKNOWN", None),
        _pillar("coding", "VERIFIED_POSITIVE", 75),
        _pillar("coverage", "UNKNOWN", None),
        _pillar("payment", "VERIFIED_POSITIVE", 70),
        _pillar("evidence", "UNKNOWN", None),
        _pillar("billing_workflow", "MIXED", 60),
    ]
    assessment = _assessment(pillars, maturity=None)
    bundle = _bundle_with_source("openfda_510k", RetrievalStatus.HIT, "exact")
    result = enforce(assessment, bundle)
    assert result.scores.maturity_state == "SCORED"
    assert result.scores.maturity is not None
    promoted_fda = next(p for p in result.pillars if p.pillar == "fda_status")
    assert promoted_fda.status == "VERIFIED_POSITIVE"


# --- coding-from-verified-fee-schedule-hit rule (added after the flip-
# matrix measurement showed coding flipping status on fixture 5 across
# repeated calls against identical frozen evidence; same shape as the
# fda_status rule above) ---

def _bundle_with_fee_schedule_hit(codes: list[str]) -> EvidenceBundle:
    return EvidenceBundle(
        sources={"fee_schedule_lookup": SourceEvidence(
            source="fee_schedule_lookup", status=RetrievalStatus.HIT, latency_ms=0,
            data={"verified_codes": [{"code": c} for c in codes]},
        )},
        all_openfda_failed=False, all_cms_failed=False,
    )


def test_unknown_coding_promoted_by_verified_fee_schedule_hit():
    pillars = [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES]
    bundle = _bundle_with_fee_schedule_hit(["92229"])
    result = enforce_coding_from_verified_fee_schedule_hit(pillars, bundle)
    coding = next(p for p in result if p.pillar == "coding")
    assert coding.status == "VERIFIED_POSITIVE"
    assert coding.score == 65
    assert "92229" in coding.finding


def test_na_coding_promoted_by_verified_fee_schedule_hit():
    pillars = [_pillar("coding", "NA", None)] + [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES if n != "coding"]
    bundle = _bundle_with_fee_schedule_hit(["76705"])
    result = enforce_coding_from_verified_fee_schedule_hit(pillars, bundle)
    assert next(p for p in result if p.pillar == "coding").status == "VERIFIED_POSITIVE"


def test_unknown_coding_not_promoted_on_fee_schedule_miss():
    pillars = [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES]
    bundle = EvidenceBundle(
        sources={"fee_schedule_lookup": SourceEvidence(source="fee_schedule_lookup", status=RetrievalStatus.MISS, latency_ms=0)},
        all_openfda_failed=False, all_cms_failed=False,
    )
    result = enforce_coding_from_verified_fee_schedule_hit(pillars, bundle)
    assert next(p for p in result if p.pillar == "coding").status == "UNKNOWN"


def test_unknown_coding_not_promoted_with_no_fee_schedule_source_at_all():
    pillars = [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES]
    result = enforce_coding_from_verified_fee_schedule_hit(pillars, _no_failure_bundle())
    assert next(p for p in result if p.pillar == "coding").status == "UNKNOWN"


def test_unknown_coding_not_promoted_when_hit_has_no_verified_codes():
    # Defensive: a HIT with an empty verified_codes list shouldn't happen
    # given resolve_fee_schedule_evidence's own MISS-on-empty behavior, but
    # this rule doesn't assume that invariant holds forever.
    pillars = [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES]
    bundle = _bundle_with_fee_schedule_hit([])
    result = enforce_coding_from_verified_fee_schedule_hit(pillars, bundle)
    assert next(p for p in result if p.pillar == "coding").status == "UNKNOWN"


def test_already_assessed_coding_never_second_guessed():
    for status in ("VERIFIED_POSITIVE", "VERIFIED_NEGATIVE", "MIXED"):
        pillars = [_pillar("coding", status, 40)] + [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES if n != "coding"]
        bundle = _bundle_with_fee_schedule_hit(["92229"])
        result = enforce_coding_from_verified_fee_schedule_hit(pillars, bundle)
        coding = next(p for p in result if p.pillar == "coding")
        assert coding.status == status
        assert coding.score == 40  # untouched, not re-scored to 65


def test_enforce_end_to_end_promotes_coding_and_rescues_scoring():
    pillars = [
        _pillar("fda_status", "VERIFIED_POSITIVE", 90),
        _pillar("coding", "UNKNOWN", None),
        _pillar("coverage", "UNKNOWN", None),
        _pillar("payment", "VERIFIED_POSITIVE", 70),
        _pillar("evidence", "UNKNOWN", None),
        _pillar("billing_workflow", "MIXED", 60),
    ]
    assessment = _assessment(pillars, maturity=None)
    bundle = _bundle_with_fee_schedule_hit(["92229"])
    result = enforce(assessment, bundle)
    promoted_coding = next(p for p in result.pillars if p.pillar == "coding")
    assert promoted_coding.status == "VERIFIED_POSITIVE"
    assert result.scores.maturity_state == "SCORED"  # now 3 assessed pillars, not 2


# --- Rule 1: recompute_maturity ---

def test_recompute_maturity_averages_only_assessed_pillars():
    pillars = [
        _pillar("fda_status", "VERIFIED_POSITIVE", 90),
        _pillar("coding", "VERIFIED_POSITIVE", 70),
        _pillar("coverage", "UNKNOWN", None),
        _pillar("payment", "NA", None),
        _pillar("evidence", "RETRIEVAL_FAILURE", None),
        _pillar("billing_workflow", "MIXED", 80),
    ]
    # (90 + 70 + 80) / 3 = 80, unknown/na/retrieval_failure dropped entirely
    assert recompute_maturity(pillars) == 80


def test_recompute_maturity_none_when_nothing_assessed():
    pillars = [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES]
    assert recompute_maturity(pillars) is None


# --- Rule 2: enforce_not_scored ---

def test_forces_not_scored_when_fewer_than_three_assessed():
    pillars = [
        _pillar("fda_status", "VERIFIED_POSITIVE", 90),
        _pillar("coding", "VERIFIED_POSITIVE", 80),
        _pillar("coverage", "UNKNOWN", None),
        _pillar("payment", "UNKNOWN", None),
        _pillar("evidence", "UNKNOWN", None),
        _pillar("billing_workflow", "UNKNOWN", None),
    ]
    maturity, state, reason = enforce_not_scored(pillars, recompute_maturity(pillars))
    assert state == "NOT_SCORED"
    assert maturity is None
    assert reason == "INSUFFICIENT_DATA_RETRIEVED"


def test_forces_not_scored_when_fda_status_itself_unassessed_even_with_three_others():
    pillars = [
        _pillar("fda_status", "UNKNOWN", None),
        _pillar("coding", "VERIFIED_POSITIVE", 80),
        _pillar("coverage", "VERIFIED_POSITIVE", 80),
        _pillar("payment", "VERIFIED_POSITIVE", 80),
        _pillar("evidence", "UNKNOWN", None),
        _pillar("billing_workflow", "UNKNOWN", None),
    ]
    maturity, state, reason = enforce_not_scored(pillars, recompute_maturity(pillars))
    assert state == "NOT_SCORED"
    assert maturity is None


def test_scored_when_three_assessed_including_fda_status():
    pillars = _all_assessed_pillars([90, 85, 80, 75, 70, 65])
    maturity, state, reason = enforce_not_scored(pillars[:3] + [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES[3:]], 85)
    assert state == "SCORED"
    assert reason is None
    assert maturity == 85


# --- Rule 3: recompute_coverage_pct ---

def test_coverage_pct_is_assessed_over_six():
    pillars = [
        _pillar("fda_status", "VERIFIED_POSITIVE", 90),
        _pillar("coding", "VERIFIED_POSITIVE", 80),
        _pillar("coverage", "VERIFIED_POSITIVE", 70),
        _pillar("payment", "UNKNOWN", None),
        _pillar("evidence", "NA", None),
        _pillar("billing_workflow", "RETRIEVAL_FAILURE", None),
    ]
    assert recompute_coverage_pct(pillars) == 50  # 3/6


# --- Rule 4: clamp_research_confidence ---

def test_confidence_clamped_when_openfda_entirely_failed():
    bundle = EvidenceBundle(sources={}, all_openfda_failed=True, all_cms_failed=False)
    assert clamp_research_confidence(90, bundle) == 60


def test_confidence_clamped_when_cms_entirely_failed():
    bundle = EvidenceBundle(sources={}, all_openfda_failed=False, all_cms_failed=True)
    assert clamp_research_confidence(90, bundle) == 60


def test_confidence_not_clamped_when_already_below_cap():
    bundle = EvidenceBundle(sources={}, all_openfda_failed=True, all_cms_failed=False)
    assert clamp_research_confidence(40, bundle) == 40


def test_confidence_untouched_when_no_full_source_failure():
    bundle = _no_failure_bundle()
    assert clamp_research_confidence(90, bundle) == 90


# --- Rule 5: risk-flag independence (the key invariant from benchmark_suite.json) ---

def test_risk_flag_change_never_changes_maturity():
    pillars = _all_assessed_pillars([90, 88, 85, 80, 75, 70])
    low_risk = _assessment(pillars, maturity=85, risk_flag="LOW")
    critical_risk = _assessment(pillars, maturity=85, risk_flag="CRITICAL")

    result_low = enforce(low_risk, _no_failure_bundle())
    result_critical = enforce(critical_risk, _no_failure_bundle())

    assert result_low.scores.maturity == result_critical.scores.maturity
    assert result_low.scores.risk_flag == "LOW"
    assert result_critical.scores.risk_flag == "CRITICAL"


# --- enforce(): full integration of all 5 rules ---

def test_enforce_overrides_model_score_when_it_disagrees_by_more_than_five():
    pillars = _all_assessed_pillars([90, 90, 90, 90, 90, 90])  # recomputed = 90
    assessment = _assessment(pillars, maturity=50)  # model says 50, off by 40
    result = enforce(assessment, _no_failure_bundle())
    assert result.scores.maturity == 90


def test_enforce_keeps_model_score_when_within_tolerance():
    pillars = _all_assessed_pillars([90, 90, 90, 90, 90, 90])  # recomputed = 90
    assessment = _assessment(pillars, maturity=87)  # within 5
    result = enforce(assessment, _no_failure_bundle())
    assert result.scores.maturity == 90  # recompute always wins when both present; still close


def test_enforce_never_produces_zero_for_retrieval_outage():
    # Fixture #10's exact scenario: both sources failed entirely.
    pillars = [_pillar(n, "UNKNOWN", None) for n in _PILLAR_NAMES]
    assessment = _assessment(pillars, maturity=0)  # a hypothetical bad model output
    bundle = EvidenceBundle(sources={}, all_openfda_failed=True, all_cms_failed=True)
    result = enforce(assessment, bundle)
    assert result.scores.maturity_state == "NOT_SCORED"
    assert result.scores.maturity is None
    assert result.scores.not_scored_reason == "INSUFFICIENT_DATA_RETRIEVED"
    assert result.scores.research_confidence <= 60
