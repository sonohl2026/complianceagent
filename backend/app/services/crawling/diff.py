"""Deterministic snapshot-to-snapshot page diffing.

Build spec §10.4: "Do not use the LLM to decide whether a page changed. Use
hashes and deterministic diffing first. Use the LLM only to summarize
material changes." This module does the hash/diff half only; an LLM-based
material-change summary is a Milestone 8 (monitoring) concern layered on
top of this, not a replacement for it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PageSnapshot:
    """Minimal shape needed to diff two crawls -- decoupled from the
    CrawledPage ORM model so this stays unit-testable without a database."""

    canonical_url: str
    sha256: str | None
    title: str | None = None


@dataclass
class PageDiffEntry:
    canonical_url: str
    change_type: str  # "added" | "removed" | "changed" | "unchanged"
    old_sha256: str | None = None
    new_sha256: str | None = None
    old_title: str | None = None
    new_title: str | None = None


def diff_snapshots(
    old_pages: list[PageSnapshot], new_pages: list[PageSnapshot]
) -> list[PageDiffEntry]:
    old_by_url = {p.canonical_url: p for p in old_pages}
    new_by_url = {p.canonical_url: p for p in new_pages}

    entries: list[PageDiffEntry] = []

    for url, new_page in new_by_url.items():
        old_page = old_by_url.get(url)
        if old_page is None:
            entries.append(
                PageDiffEntry(canonical_url=url, change_type="added", new_sha256=new_page.sha256, new_title=new_page.title)
            )
        elif old_page.sha256 != new_page.sha256:
            entries.append(
                PageDiffEntry(
                    canonical_url=url,
                    change_type="changed",
                    old_sha256=old_page.sha256,
                    new_sha256=new_page.sha256,
                    old_title=old_page.title,
                    new_title=new_page.title,
                )
            )
        else:
            entries.append(
                PageDiffEntry(
                    canonical_url=url,
                    change_type="unchanged",
                    old_sha256=old_page.sha256,
                    new_sha256=new_page.sha256,
                    old_title=old_page.title,
                    new_title=new_page.title,
                )
            )

    for url, old_page in old_by_url.items():
        if url not in new_by_url:
            entries.append(
                PageDiffEntry(canonical_url=url, change_type="removed", old_sha256=old_page.sha256, old_title=old_page.title)
            )

    return entries


def summarize_diff(entries: list[PageDiffEntry]) -> dict[str, int]:
    summary = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}
    for entry in entries:
        summary[entry.change_type] += 1
    return summary
