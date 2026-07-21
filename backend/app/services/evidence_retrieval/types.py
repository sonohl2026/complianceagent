"""Shared vocabulary for Stage-2 retrieval (quick_scan spec §1.4).

Every external source -- openFDA, CMS Coverage API -- returns one of these
three statuses, never a bare success/failure boolean. The distinction is the
whole point: MISS is legitimate evidence (the source was searched and
genuinely has nothing), RETRIEVAL_FAILURE is an agent/tool limitation (never
evidence about the product). Stage 3 and the scoring-enforcement code both
key off this enum rather than inspecting per-source response shapes.
"""

import enum
from dataclasses import dataclass, field
from typing import Any


class RetrievalStatus(str, enum.Enum):
    HIT = "HIT"
    MISS = "MISS"
    RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"


@dataclass
class SourceEvidence:
    source: str
    status: RetrievalStatus
    latency_ms: int
    data: dict[str, Any] | None = None
    error: str | None = None
    match_confidence: str | None = None  # "exact" | "probable" | "uncertain", set by search-order logic
