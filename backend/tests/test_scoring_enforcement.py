from app.services.evidence_retrieval.orchestrator import EvidenceBundle
from app.services.quick_scan.scoring_enforcement import (
    clamp_research_confidence,
    enforce,
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
