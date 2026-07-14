"""Deterministic guardrail on the model's self-reported readiness_score
(user-requested follow-up to the reporting work: the model's own number was
never checked against anything -- see docs/data-model.md). This can only
ever LOWER the model's score, never raise it: these are hard caps for
internal consistency (a STOP verdict can't coexist with a high readiness
score, an unresolved CRITICAL finding can't coexist with "ready for
market"), not a replacement for the model's own judgment about the
specific facts of a given analysis.
"""

from dataclasses import dataclass

from app.models.enums import RiskLevel, Verdict

_UNRESOLVED_STATUSES = {"MISSING", "UNRESOLVED"}
_HIGH_SEVERITY_RISKS = {RiskLevel.CRITICAL, RiskLevel.HIGH}


@dataclass
class ScoreCap:
    cap: int
    reason: str


def apply_readiness_score_guardrail(
    *,
    model_score: int,
    overall_verdict: Verdict,
    overall_risk: RiskLevel,
    finding_risks: list[RiskLevel],
    finding_statuses: list[str],
) -> tuple[int, str | None]:
    """Returns (final_score, note). note is None when no cap applied (the
    model's own score already respected every rule)."""
    caps: list[ScoreCap] = []

    if overall_verdict == Verdict.STOP:
        caps.append(ScoreCap(25, "overall verdict is STOP"))
    if overall_risk == RiskLevel.CRITICAL:
        caps.append(ScoreCap(30, "overall risk is CRITICAL"))
    if RiskLevel.CRITICAL in finding_risks:
        caps.append(ScoreCap(40, "at least one finding carries CRITICAL risk"))
    if any(
        status in _UNRESOLVED_STATUSES and risk in _HIGH_SEVERITY_RISKS
        for status, risk in zip(finding_statuses, finding_risks)
    ):
        caps.append(ScoreCap(60, "at least one MISSING/UNRESOLVED finding carries HIGH or CRITICAL risk"))

    if not caps:
        return model_score, None

    tightest = min(caps, key=lambda c: c.cap)
    if model_score <= tightest.cap:
        return model_score, None

    note = f"Readiness score capped at {tightest.cap} (model reported {model_score}): {tightest.reason}."
    return tightest.cap, note
