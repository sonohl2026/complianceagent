from app.services.fee_schedule import description_search


def test_finds_real_code_via_abbreviated_description():
    # Real case this was built for: 92229's real CMS description is heavily
    # abbreviated ("Img rta detc/mntr ds poc aly" = imaging retina detection/
    # monitoring disease point-of-care autonomous analysis) and an LLM's own
    # memorized knowledge of it is unreliable (confirmed empirically -- see
    # code_candidates.py's module docstring).
    descriptions = {
        "92229": "Img rta detc/mntr ds poc aly",
        "00702": "Anes upr ant abd wall lvr bx",
        "82013": "Acetylcholinesterase assay",
        "G0077": "Care manag h vst new pt 30 m",
    }
    query = (
        "AI diagnostic software Analyzes retinal images to detect more than mild diabetic "
        "retinopathy without requiring a clinician to interpret the image in primary care settings"
    )
    results = description_search.find_candidates(query, descriptions)
    assert "92229" in results


def test_real_signal_outranks_a_known_false_positive_prone_code():
    # Real false positive found during tuning: "anes"/"upr"/"ant" (from an
    # unrelated anesthesia code, 00702) spuriously matches "diagnostic"/
    # "interpret"/"primary" via short (2-character) substring coincidence --
    # and this module deliberately does NOT try to eliminate that here (see
    # module docstring: no single mechanical threshold is both tight enough
    # to reject that class of noise and loose enough to keep genuine
    # abbreviation matches, which are often themselves only 2 characters
    # after vowel-stripping). This pre-filter stays loose on purpose; a
    # separate LLM call makes the actual precision judgment against the
    # real, grounded shortlist this produces (verified live and in
    # test_code_candidates.py that it correctly rejects 00702-like noise
    # when shown alongside a genuine match). What this module itself must
    # guarantee is that the real signal isn't buried by the noise -- it
    # ranks at or above a known false-positive-prone code.
    descriptions = {
        "92229": "Img rta detc/mntr ds poc aly",
        "00702": "Anes upr ant abd wall lvr bx",
    }
    query = (
        "AI diagnostic software Analyzes retinal images to detect more than mild diabetic "
        "retinopathy without requiring a clinician to interpret the image in primary care settings"
    )
    results = description_search.find_candidates(query, descriptions)
    assert results.index("92229") <= results.index("00702")


def test_empty_query_returns_no_candidates():
    assert description_search.find_candidates("", {"92229": "Img rta detc/mntr ds poc aly"}) == []


def test_no_matching_descriptions_returns_empty():
    descriptions = {"82013": "Acetylcholinesterase assay"}
    query = "wireless handheld point-of-care ultrasound probe"
    assert description_search.find_candidates(query, descriptions) == []


def test_results_capped_and_ranked_by_match_count():
    query = "point of care autonomous retinal disease detection and monitoring imaging analysis"
    descriptions = {f"code{i}": "Unrelated filler text about something else entirely" for i in range(50)}
    descriptions["92229"] = "Img rta detc/mntr ds poc aly"
    results = description_search.find_candidates(query, descriptions)
    assert len(results) <= description_search._MAX_PREFILTER_RESULTS
    assert results[0] == "92229"  # highest match count should rank first
