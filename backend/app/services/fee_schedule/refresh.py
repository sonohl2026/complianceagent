"""Refresh orchestration for fee-schedule tables: downloads+parses the
current quarterly release and stores it in Redis (see cache.py). PFS RVU is
the only table implemented so far -- DMEPOS and a standalone HCPCS Level II
registry were scoped for this same effort but deferred (CMS's DMEPOS fee
schedule page doesn't have PFS's clean, consistent per-quarter link
structure; needs its own follow-up investigation rather than a rushed,
fragile scraper).

These files only change ~4x/year, so a weekly check (see the Celery Beat
entry in celery_app.py) is ample lead time -- this isn't trying to catch a
same-day correction.
"""

import logging

import httpx

from app.services.fee_schedule import cache, pfs_client

logger = logging.getLogger(__name__)

_REFRESH_INTERVAL_SECONDS = 7 * 24 * 3600  # weekly


async def refresh_pfs(client: httpx.AsyncClient) -> bool:
    """Returns True if the table was (re-)populated, False on any failure --
    never raises, since a failed refresh should leave the last-known-good
    data in place rather than wipe it."""
    try:
        entries = await pfs_client.download_and_parse(client)
    except Exception as exc:  # noqa: BLE001 - a scrape/parse failure here must never take down quick_scan
        logger.warning("PFS fee-schedule refresh failed, keeping previous data if any: %s", exc)
        return False
    if not entries:
        logger.warning("PFS fee-schedule refresh found no entries, keeping previous data if any")
        return False
    await cache.store_table("pfs", entries)
    logger.info("PFS fee-schedule refreshed: %d codes", len(entries))
    return True


async def ensure_pfs_populated(client: httpx.AsyncClient) -> None:
    """Lazy-fill for first boot / a fresh Redis instance, so the very first
    quick_scan run after deploy doesn't just get MISS on every code until the
    weekly scheduled task happens to run."""
    if await cache.last_refreshed_at("pfs") is None:
        await refresh_pfs(client)
