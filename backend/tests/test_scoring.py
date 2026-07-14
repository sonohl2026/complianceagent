from app.models.enums import RiskLevel, Verdict
from app.services.analysis.scoring import apply_readiness_score_guardrail


def test_no_cap_needed_when_score_already_respects_rules():
    score, note = apply_readiness_score_guardrail(
        model_score=15,
        overall_verdict=Verdict.STOP,
        overall_risk=RiskLevel.CRITICAL,
        finding_risks=[RiskLevel.LOW],
        finding_statuses=["VERIFIED"],
    )
    assert score == 15
    assert note is None


def test_stop_verdict_caps_high_score():
    score, note = apply_readiness_score_guardrail(
        model_score=85,
        overall_verdict=Verdict.STOP,
        overall_risk=RiskLevel.MEDIUM,
        finding_risks=[],
        finding_statuses=[],
    )
    assert score == 25
    assert note is not None
    assert "85" in note  # the model's original number is quoted, not hidden
    assert "STOP" in note


def test_go_verdict_with_no_critical_findings_is_never_capped():
    score, note = apply_readiness_score_guardrail(
        model_score=90,
        overall_verdict=Verdict.GO,
        overall_risk=RiskLevel.LOW,
        finding_risks=[RiskLevel.LOW, RiskLevel.MEDIUM],
        finding_statuses=["VERIFIED", "LIKELY"],
    )
    assert score == 90
    assert note is None


def test_critical_finding_caps_score_even_with_go_verdict():
    # A model could theoretically report GO overall while still logging one
    # CRITICAL-risk finding -- the guardrail catches that inconsistency.
    score, note = apply_readiness_score_guardrail(
        model_score=95,
        overall_verdict=Verdict.GO,
        overall_risk=RiskLevel.LOW,
        finding_risks=[RiskLevel.CRITICAL],
        finding_statuses=["VERIFIED"],
    )
    assert score == 40
    assert "CRITICAL" in note


def test_unresolved_high_risk_finding_caps_score():
    score, note = apply_readiness_score_guardrail(
        model_score=75,
        overall_verdict=Verdict.CONDITIONAL_GO,
        overall_risk=RiskLevel.MEDIUM,
        finding_risks=[RiskLevel.HIGH],
        finding_statuses=["MISSING"],
    )
    assert score == 60
    assert "MISSING" in note or "UNRESOLVED" in note


def test_multiple_caps_uses_the_tightest_one():
    # STOP (cap 25) and a CRITICAL finding (cap 40) both apply -- the
    # tighter cap wins.
    score, note = apply_readiness_score_guardrail(
        model_score=99,
        overall_verdict=Verdict.STOP,
        overall_risk=RiskLevel.LOW,
        finding_risks=[RiskLevel.CRITICAL],
        finding_statuses=["VERIFIED"],
    )
    assert score == 25


def test_guardrail_never_raises_the_models_own_score():
    # Even under a rule that *could* apply, a model score already below the
    # cap must be left untouched, never bumped up to the cap.
    score, note = apply_readiness_score_guardrail(
        model_score=10,
        overall_verdict=Verdict.STOP,
        overall_risk=RiskLevel.LOW,
        finding_risks=[],
        finding_statuses=[],
    )
    assert score == 10
    assert note is None


def test_resolved_high_risk_finding_does_not_trigger_the_unresolved_cap():
    score, note = apply_readiness_score_guardrail(
        model_score=80,
        overall_verdict=Verdict.CONDITIONAL_GO,
        overall_risk=RiskLevel.MEDIUM,
        finding_risks=[RiskLevel.HIGH],
        finding_statuses=["VERIFIED"],  # not MISSING/UNRESOLVED
    )
    assert score == 80
    assert note is None
