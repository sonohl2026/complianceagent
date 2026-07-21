"""Representative source text + (for the free DRY_RUN_LLM mode) scripted
Stage-1/Stage-3 responses for each benchmark_suite.json fixture.

benchmark_suite.json describes each fixture as a *scenario* ("feed a
published clinical paper about SAPIEN 3 TAVR outcomes...") rather than
literal text, so the harness needs an actual document to feed Stage 1 --
these are hand-written excerpts matching each fixture's input_hint/name
closely enough to exercise the real retrieval layer against the real device
the fixture names.
"""

FIXTURE_SOURCE_TEXT = {
    1: """We report 5-year outcomes from a cohort of patients undergoing transcatheter
    aortic valve replacement with the SAPIEN 3 valve system (Edwards Lifesciences).
    All-cause mortality at 5 years was 45.1% in the transcatheter group.""",
    2: """The Azure XT pacemaker from Medtronic is a dual-chamber pacing system
    indicated for bradycardia. It features BlueSync technology for wireless
    connectivity with patient monitors and is MRI conditional.""",
    3: """IDx-DR (marketed as LumineticsCore) is an autonomous AI system that analyzes
    retinal images to detect more than mild diabetic retinopathy without requiring a
    clinician to interpret the image. Intended for primary care settings.""",
    4: """The Dexcom G7 Continuous Glucose Monitoring System is a small wearable sensor
    worn on the back of the upper arm or abdomen that measures glucose levels every 5
    minutes for up to 10 days and sends readings to a compatible smart device.""",
    5: """Vscan Air is a wireless, handheld point-of-care ultrasound probe intended to
    help clinicians visualize anatomical structures during physical examination. It
    connects to a smartphone or tablet via the Vscan Air app.""",
    6: """The company announced that its next-generation responsive neurostimulation
    device received FDA Breakthrough Device designation for the treatment of
    drug-resistant epilepsy. The device remains under clinical development and does
    not yet have an assigned CPT code or NCD.""",
    7: """PulseWave Analyzer is a novel non-invasive arterial stiffness monitoring
    device used during outpatient cardiology visits. A Category III CPT code has been
    established for the associated professional service, though payer coverage
    remains at each plan's discretion.""",
    8: """Medtronic issued a Class I recall for certain MiniMed 600 series insulin pump
    models due to a retainer ring issue that could allow over- or under-delivery of
    insulin. The pump remains covered under existing DME benefit categories for
    patients not affected by the recalled lot numbers.""",
    9: """Our seed-stage startup is developing a novel wearable acoustic sensing patch
    intended to detect early signs of cardiopulmonary distress. We have not yet
    submitted anything to the FDA and are currently in the prototype/bench-testing
    phase.""",
    10: """Any input works for this fixture -- it simulates a total retrieval outage,
    not a specific device.""",
}

# Free/fast DRY_RUN_LLM mode: scripted Stage-1 + (post-enforcement-shaped)
# Stage-3 responses per fixture, tailored to land inside that fixture's own
# expected band. This does not validate real-world retrieval or model
# quality (the real `make bench` run does that) -- it validates that the
# pipeline plumbing, schema, and scoring-enforcement math all still work
# after a code change, for $0 and in under a second.
_PILLAR_NAMES = ["fda_status", "coding", "coverage", "payment", "evidence", "billing_workflow"]


def _dry_pillars(scores: list[int | None], statuses: list[str] | None = None) -> list[dict]:
    statuses = statuses or ["VERIFIED_POSITIVE" if s is not None else "UNKNOWN" for s in scores]
    return [
        {
            "pillar": name, "status": status, "score": score,
            "finding": f"dry-run finding for {name}", "detail": "dry-run detail",
            "citation": None, "gap": None, "action": None,
        }
        for name, status, score in zip(_PILLAR_NAMES, statuses, scores)
    ]


DRY_RUN_STAGE1 = {
    fid: {
        "product_name": f"fixture-{fid}-product", "manufacturer": f"fixture-{fid}-mfr",
        "aliases": [], "intended_use": "dry-run", "technology_type": "dry-run",
        "dev_stage_guess": "commercial", "candidate_search_terms": ["dry-run term"],
    }
    for fid in range(1, 11)
}

DRY_RUN_STAGE3 = {
    1: {"scores": {"maturity": 90, "risk_flag": "MEDIUM"}, "pillars": _dry_pillars([95, 85, 90, 80, 85, 80])},
    2: {"scores": {"maturity": 90, "risk_flag": "LOW"}, "pillars": _dry_pillars([95, 90, 85, 85, 90, 90])},
    3: {"scores": {"maturity": 85, "risk_flag": "LOW"}, "pillars": _dry_pillars([90, 85, 80, 85, 85, 80])},
    4: {"scores": {"maturity": 85, "risk_flag": "LOW"}, "pillars": _dry_pillars([90, 85, 80, 85, 85, 80])},
    5: {"scores": {"maturity": 72, "risk_flag": "LOW"}, "pillars": _dry_pillars([80, 75, 70, 65, 70, 70])},
    6: {"scores": {"maturity": 50, "risk_flag": "LOW"}, "pillars": _dry_pillars([60, None, None, None, 55, 45], ["VERIFIED_POSITIVE", "UNKNOWN", "UNKNOWN", "UNKNOWN", "VERIFIED_POSITIVE", "MIXED"])},
    7: {"scores": {"maturity": 45, "risk_flag": "MEDIUM"}, "pillars": _dry_pillars([60, 45, 40, None, 45, None], ["VERIFIED_POSITIVE", "VERIFIED_POSITIVE", "MIXED", "UNKNOWN", "VERIFIED_POSITIVE", "UNKNOWN"])},
    8: {"scores": {"maturity": 88, "risk_flag": "HIGH"}, "pillars": _dry_pillars([90, 85, 90, 85, 85, 90])},
    9: {"scores": {"maturity": 15, "risk_flag": "LOW"}, "pillars": _dry_pillars([20, None, None, None, 15, 10], ["VERIFIED_NEGATIVE", "UNKNOWN", "UNKNOWN", "UNKNOWN", "VERIFIED_NEGATIVE", "MIXED"])},
    # Fixture 10 (retrieval outage): the scripted Stage-3 content here is
    # irrelevant to the actual test -- enforce()'s force_not_scored (driven
    # by the respx-mocked all-sources-failed evidence bundle, not by
    # anything Stage 3 says) overrides to NOT_SCORED regardless. A
    # deliberately "confident-looking" fake response here exercises exactly
    # that override path.
    10: {"scores": {"maturity": 80, "risk_flag": "LOW"}, "pillars": _dry_pillars([80, 80, 80, 80, 80, 80])},
}


def dry_run_stage3_response(fixture_id: int) -> dict:
    base = DRY_RUN_STAGE3[fixture_id]
    return {
        "product": {
            "name": f"fixture-{fixture_id}-product", "manufacturer": f"fixture-{fixture_id}-mfr",
            "fda_status": "dry-run", "identifiers": [], "dev_stage": "commercial",
        },
        "scores": {
            "maturity": base["scores"]["maturity"], "maturity_state": "SCORED", "not_scored_reason": None,
            "assessment_coverage_pct": 100, "research_confidence": 90,
            "risk_flag": base["scores"]["risk_flag"], "stage_context": "dry-run stage context, on-track.",
        },
        "pillars": base["pillars"],
        "top_gaps": [], "next_steps": [],
        "disclaimer": (
            "Informational market-access analysis only; not legal, regulatory, or coding advice. "
            "Verify all codes and rates against official sources before billing."
        ),
    }
