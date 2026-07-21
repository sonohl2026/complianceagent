"""Stage-2 retrieval orchestration (quick_scan spec §1, §1.4).

Fires openFDA + CMS Coverage calls concurrently, reports each source's result
to an optional progress callback as it resolves (feeds
AnalysisRun.retrieval_progress_json for the UI's live feed -- see
app/services/quick_scan/pipeline.py), and centrally enforces the one
cross-cutting failure rule the spec insists live in code, not the model:
if EVERY source failed with RETRIEVAL_FAILURE, the caller must force
NOT_SCORED/INSUFFICIENT_DATA_RETRIEVED -- this module surfaces that as a
boolean on the returned bundle rather than leaving it to be reconstructed by
whoever calls it.
"""

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

import httpx

from app.services.evidence_retrieval import cms_coverage_client, openfda_client
from app.services.evidence_retrieval.types import RetrievalStatus, SourceEvidence


class Stage1Like(Protocol):
    product_name: str
    manufacturer: str
    aliases: list[str]
    candidate_search_terms: list[str]


ProgressCallback = Callable[[str, SourceEvidence], Awaitable[None]]

_OPENFDA_SEARCHES = {
    "510k": openfda_client.search_510k,
    "pma": openfda_client.search_pma,
    "classification": openfda_client.search_classification,
    "recall": openfda_client.search_recall,
    "enforcement": openfda_client.search_enforcement,
    "event": openfda_client.search_event,
    "udi": openfda_client.search_udi,
}
_CMS_RESOURCES = ["ncd", "lcd", "article"]


@dataclass
class EvidenceBundle:
    sources: dict[str, SourceEvidence]
    all_openfda_failed: bool
    all_cms_failed: bool

    @property
    def force_not_scored(self) -> bool:
        # Spec 1.4: both government sources failing entirely -> NOT_SCORED,
        # never a numeric score (fixture #10's exact scenario).
        return self.all_openfda_failed and self.all_cms_failed


async def _run_openfda(client: httpx.AsyncClient, stage1: Stage1Like, on_progress: ProgressCallback | None) -> dict[str, SourceEvidence]:
    results: dict[str, SourceEvidence] = {}
    for name, search_fn in _OPENFDA_SEARCHES.items():
        evidence = await search_fn(
            client, product_name=stage1.product_name, manufacturer=stage1.manufacturer, aliases=stage1.aliases,
        )
        results[evidence.source] = evidence
        if on_progress is not None:
            await on_progress(evidence.source, evidence)
    return results


async def _run_cms(client: httpx.AsyncClient, stage1: Stage1Like, on_progress: ProgressCallback | None) -> dict[str, SourceEvidence]:
    results: dict[str, SourceEvidence] = {}
    for resource in _CMS_RESOURCES:
        evidence = await cms_coverage_client.search_unlicensed(client, resource, stage1.candidate_search_terms)
        results[evidence.source] = evidence
        if on_progress is not None:
            await on_progress(evidence.source, evidence)
    return results


async def run_evidence_retrieval(stage1: Stage1Like, on_progress: ProgressCallback | None = None) -> EvidenceBundle:
    async with httpx.AsyncClient() as client:
        openfda_results, cms_results = await _gather_both(client, stage1, on_progress)

    all_sources = {**openfda_results, **cms_results}
    all_openfda_failed = bool(openfda_results) and all(
        e.status == RetrievalStatus.RETRIEVAL_FAILURE for e in openfda_results.values()
    )
    all_cms_failed = bool(cms_results) and all(
        e.status == RetrievalStatus.RETRIEVAL_FAILURE for e in cms_results.values()
    )
    return EvidenceBundle(sources=all_sources, all_openfda_failed=all_openfda_failed, all_cms_failed=all_cms_failed)


async def _gather_both(client, stage1, on_progress):
    openfda_task = _run_openfda(client, stage1, on_progress)
    cms_task = _run_cms(client, stage1, on_progress)
    openfda_results, cms_results = await asyncio.gather(openfda_task, cms_task)
    return openfda_results, cms_results
