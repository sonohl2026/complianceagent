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
import html
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

import httpx

from app.services.evidence_retrieval import cms_coverage_client, openfda_client
from app.services.evidence_retrieval.types import RetrievalStatus, SourceEvidence
from app.services.storage.settings_store import load_runtime_settings


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


_OPENFDA_CONCURRENCY = 5  # small, defensive throttle -- openFDA's public rate
# limit isn't officially pinned down for anonymous callers, and there's no
# reason to risk it for one quick_scan's worth of 7 calls; this still runs
# them almost entirely in parallel, just never more than 5 in flight at once.


async def _run_openfda(
    client: httpx.AsyncClient, stage1: Stage1Like, on_progress: ProgressCallback | None,
) -> dict[str, SourceEvidence]:
    # Previously a plain sequential for-loop despite the module docstring's
    # own "parallel HTTP" claim -- see status report §2/§4. Each endpoint's
    # OWN internal fallback order (exact name -> aliases -> manufacturer,
    # stop at first verified hit -- openfda_client.py::search_with_fallback)
    # is untouched; only the ACROSS-endpoint dispatch changes from sequential
    # to concurrent.
    semaphore = asyncio.Semaphore(_OPENFDA_CONCURRENCY)

    async def _one(search_fn) -> tuple[str, SourceEvidence]:
        async with semaphore:
            evidence = await search_fn(
                client, product_name=stage1.product_name, manufacturer=stage1.manufacturer, aliases=stage1.aliases,
            )
        if on_progress is not None:
            await on_progress(evidence.source, evidence)
        return evidence.source, evidence

    pairs = await asyncio.gather(*(_one(search_fn) for search_fn in _OPENFDA_SEARCHES.values()))
    return dict(pairs)


def _clean_text(value):
    if not isinstance(value, str):
        return value
    return re.sub(r"<[^>]+>", " ", html.unescape(value)).strip()


def _clean_document(document: dict) -> dict:
    # CMS's detail responses HTML-escape and tag-wrap narrative fields (e.g.
    # "&lt;p&gt;...&lt;/p&gt;") -- clean every string field generically rather
    # than hardcoding per-resource field names (ncd/lcd/article each have a
    # different set of narrative fields, and CMS can add more over time).
    return {k: _clean_text(v) for k, v in document.items()}


async def _fetch_top_match_detail(
    client: httpx.AsyncClient, resource: str, listing_hit: SourceEvidence, settings: dict,
) -> SourceEvidence | None:
    matches = listing_hit.data.get("matches") or []
    if not matches:
        return None
    top = matches[0]
    doc_id, version = top.get("document_id"), top.get("document_version")
    if doc_id is None or version is None:
        return None
    detail = await cms_coverage_client.get_licensed_document(client, resource, str(doc_id), str(version), settings)
    if detail.status == RetrievalStatus.HIT:
        detail.data = {**detail.data, "document": _clean_document(detail.data["document"])}
    return detail


async def _run_cms(
    client: httpx.AsyncClient, stage1: Stage1Like, on_progress: ProgressCallback | None, settings: dict,
) -> dict[str, SourceEvidence]:
    # A listing match only confirms a coverage document EXISTS (title-only
    # search); the actual coding/coverage narrative -- where a CMS "Billing
    # and Coding" article would enumerate real CPT/HCPCS codes -- lives in
    # the document's full body, fetched here via the already-built
    # get_licensed_document (NCD is unlicensed; LCD/Article require
    # settings["cms_license_accepted"], enforced by that function itself).
    # Only the top-ranked match gets a detail fetch, to keep this to at most
    # one extra HTTP call per resource rather than one per matched row.
    #
    # Previously a sequential for-loop across the 3 resources -- now each
    # resource's own (listing -> conditional detail) sequence runs
    # concurrently with the other resources' (CMS's own docs put its
    # throttle at 10,000 req/s, so no semaphore needed here unlike openFDA).

    async def _one(resource: str) -> dict[str, SourceEvidence]:
        result: dict[str, SourceEvidence] = {}
        evidence = await cms_coverage_client.search_unlicensed(client, resource, stage1.candidate_search_terms)
        result[evidence.source] = evidence
        if on_progress is not None:
            await on_progress(evidence.source, evidence)

        if evidence.status != RetrievalStatus.HIT:
            return result
        detail = await _fetch_top_match_detail(client, resource, evidence, settings)
        if detail is None:
            return result
        result[detail.source] = detail
        if on_progress is not None:
            await on_progress(detail.source, detail)
        return result

    per_resource = await asyncio.gather(*(_one(resource) for resource in _CMS_RESOURCES))
    merged: dict[str, SourceEvidence] = {}
    for result in per_resource:
        merged.update(result)
    return merged


def _serialize_progress(on_progress: ProgressCallback | None) -> ProgressCallback | None:
    """Now that up to 10 sources (7 openFDA + 3 CMS) can resolve genuinely
    concurrently -- previously just 2 coarse groups -- a caller-supplied
    on_progress that isn't itself concurrency-safe (pipeline.py's closure
    calls db.commit() on one shared AsyncSession, which is NOT safe to touch
    from multiple coroutines at once) would race. Hit this for real during
    verification: a concurrent commit corrupted the session badly enough
    that even the task's own failure-handling commit couldn't run, silently
    orphaning the run in RUNNING forever. A single lock here serializes the
    actual callback invocations without serializing the HTTP calls
    themselves -- the slow part stays parallel, only the fast DB write
    is queued."""
    if on_progress is None:
        return None
    lock = asyncio.Lock()

    async def _wrapped(source_name: str, evidence: SourceEvidence) -> None:
        async with lock:
            await on_progress(source_name, evidence)

    return _wrapped


async def run_evidence_retrieval(
    stage1: Stage1Like, on_progress: ProgressCallback | None = None, settings: dict | None = None,
) -> EvidenceBundle:
    # settings defaults to the real app settings store (cms_license_accepted
    # etc.) so production call sites don't need to pass it; tests inject an
    # explicit dict for determinism, matching cms_coverage_client's own test
    # convention rather than depending on file-backed state.
    if settings is None:
        settings = load_runtime_settings()
    on_progress = _serialize_progress(on_progress)
    async with httpx.AsyncClient() as client:
        openfda_results, cms_results = await _gather_both(client, stage1, on_progress, settings)

    all_sources = {**openfda_results, **cms_results}
    all_openfda_failed = bool(openfda_results) and all(
        e.status == RetrievalStatus.RETRIEVAL_FAILURE for e in openfda_results.values()
    )
    all_cms_failed = bool(cms_results) and all(
        e.status == RetrievalStatus.RETRIEVAL_FAILURE for e in cms_results.values()
    )
    return EvidenceBundle(sources=all_sources, all_openfda_failed=all_openfda_failed, all_cms_failed=all_cms_failed)


async def _gather_both(client, stage1, on_progress, settings):
    openfda_task = _run_openfda(client, stage1, on_progress)
    cms_task = _run_cms(client, stage1, on_progress, settings)
    openfda_results, cms_results = await asyncio.gather(openfda_task, cms_task)
    return openfda_results, cms_results
