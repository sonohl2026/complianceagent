"""Pure ranking math for hybrid retrieval: reciprocal-rank fusion plus an
authority-level boost. Kept dependency-free (no DB, no SQLAlchemy) so it can
be unit-tested without a live Postgres instance.

Build spec §12.2: "Apply a retrieval boost to: (1) binding current
authority ... (5) working company drafts ... (7) competitor analogies. Do
not allow semantic similarity alone to outrank authority" — implemented as a
multiplicative boost on top of fused rank scores, not a hard override, so a
highly relevant Level 3 source can still outrank a barely-relevant Level 1
source, while ties and near-ties resolve toward the higher authority level.
"""

from app.models.enums import AuthorityLevel

RRF_K = 60

# Multiplicative boost applied to the fused RRF score. 0.0 = no boost.
AUTHORITY_BOOST: dict[AuthorityLevel | None, float] = {
    AuthorityLevel.LEVEL_1_CONTROLLED_COMPANY_OR_BINDING_AUTHORITY: 0.60,
    AuthorityLevel.LEVEL_2_VERIFIED_INTERNAL_EVIDENCE: 0.40,
    AuthorityLevel.LEVEL_3_OFFICIAL_EXTERNAL_AUTHORITY: 0.30,
    AuthorityLevel.LEVEL_4_WORKING_DRAFT: 0.10,
    AuthorityLevel.LEVEL_5_SECONDARY_OR_ANALOG: 0.0,
    None: 0.0,
}


def reciprocal_rank_fusion(
    *ranked_id_lists: list[str], k: int = RRF_K
) -> dict[str, float]:
    """Combine any number of ranked-id lists (best first) into one fused
    score per id via RRF: score(d) = sum(1 / (k + rank)) across lists where
    d appears (rank is 1-indexed). Ids absent from a list simply don't
    contribute from that list."""
    scores: dict[str, float] = {}
    for ranked_ids in ranked_id_lists:
        for rank, doc_id in enumerate(ranked_ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def apply_authority_boost(
    fused_scores: dict[str, float],
    authority_levels: dict[str, AuthorityLevel | None],
) -> dict[str, float]:
    """Multiply each fused score by (1 + boost) for its document's
    authority_level. Ids missing from `authority_levels` are treated as
    unboosted (boost 0.0)."""
    boosted: dict[str, float] = {}
    for doc_id, score in fused_scores.items():
        level = authority_levels.get(doc_id)
        boost = AUTHORITY_BOOST.get(level, 0.0)
        boosted[doc_id] = score * (1.0 + boost)
    return boosted


def rank_ids(scores: dict[str, float]) -> list[str]:
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]
