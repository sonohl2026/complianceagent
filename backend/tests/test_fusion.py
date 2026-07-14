from app.models.enums import AuthorityLevel
from app.services.retrieval.fusion import apply_authority_boost, rank_ids, reciprocal_rank_fusion


def test_rrf_favors_documents_ranked_high_in_both_lists():
    vector_ranked = ["a", "b", "c"]
    fulltext_ranked = ["b", "a", "c"]
    scores = reciprocal_rank_fusion(vector_ranked, fulltext_ranked)
    assert rank_ids(scores)[0] in ("a", "b")  # both near top of both lists
    assert rank_ids(scores)[-1] == "c"  # last in both lists


def test_rrf_includes_documents_present_in_only_one_list():
    scores = reciprocal_rank_fusion(["a", "b"], ["c"])
    assert set(scores.keys()) == {"a", "b", "c"}


def test_rrf_empty_lists_produce_empty_scores():
    assert reciprocal_rank_fusion([], []) == {}


def test_authority_boost_can_promote_lower_raw_score_above_higher_one():
    # "authority_doc" ranks slightly behind "no_authority_doc" on raw fusion,
    # but is Level 1 (controlled company / binding authority) vs no authority
    # level at all -- the boost should be enough to flip the ordering.
    fused = {"authority_doc": 0.020, "no_authority_doc": 0.022}
    authority_levels = {
        "authority_doc": AuthorityLevel.LEVEL_1_CONTROLLED_COMPANY_OR_BINDING_AUTHORITY,
        "no_authority_doc": None,
    }
    boosted = apply_authority_boost(fused, authority_levels)
    assert rank_ids(boosted)[0] == "authority_doc"


def test_authority_boost_does_not_let_irrelevant_authority_beat_highly_relevant_result():
    # A barely-relevant Level 1 doc should not leapfrog a much more relevant
    # Level 3 doc -- boost is meant to break ties/near-ties, not invert
    # genuinely large relevance gaps.
    fused = {"barely_relevant_level1": 0.002, "highly_relevant_level3": 0.030}
    authority_levels = {
        "barely_relevant_level1": AuthorityLevel.LEVEL_1_CONTROLLED_COMPANY_OR_BINDING_AUTHORITY,
        "highly_relevant_level3": AuthorityLevel.LEVEL_3_OFFICIAL_EXTERNAL_AUTHORITY,
    }
    boosted = apply_authority_boost(fused, authority_levels)
    assert rank_ids(boosted)[0] == "highly_relevant_level3"


def test_authority_boost_defaults_to_zero_for_unknown_ids():
    boosted = apply_authority_boost({"x": 0.01}, {})
    assert boosted["x"] == 0.01


def test_rank_ids_sorts_descending():
    assert rank_ids({"a": 0.1, "b": 0.9, "c": 0.5}) == ["b", "c", "a"]
