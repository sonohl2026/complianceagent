"""Redis-backed storage for parsed fee-schedule tables -- shared across the
api/worker/scheduler processes (unlike cms_coverage_client's per-process
in-memory _listing_cache, which is fine for its cheap listing re-fetch but
would mean every Celery worker independently re-parsing a multi-MB PFS file).
Redis is already in this stack as the Celery broker.

Each table is stored as a single JSON blob under a versioned key
(`fee_schedule:{table}:data`) plus a timestamp key
(`fee_schedule:{table}:refreshed_at`) so refresh.py's scheduled task can
decide whether a re-check is due. A full-replace write (not incremental) --
each quarterly source file is a complete snapshot.
"""

import json
import time

import redis.asyncio as redis

from app.config import get_settings
from app.services.fee_schedule.types import CodeFormat, FeeScheduleEntry

_DATA_KEY_TEMPLATE = "fee_schedule:{table}:data"
_REFRESHED_AT_KEY_TEMPLATE = "fee_schedule:{table}:refreshed_at"


def _client() -> redis.Redis:
    return redis.from_url(get_settings().redis_url, decode_responses=True)


def _entry_to_json(entry: FeeScheduleEntry) -> str:
    return json.dumps({
        "code": entry.code, "code_format": entry.code_format.value, "active": entry.active,
        "source": entry.source, "payment_system": entry.payment_system,
        "rate_usd": entry.rate_usd, "status_code": entry.status_code, "description": entry.description,
    })


def _entry_from_json(raw: str) -> FeeScheduleEntry:
    data = json.loads(raw)
    data["code_format"] = CodeFormat(data["code_format"])
    return FeeScheduleEntry(**data)


async def store_table(table: str, entries: dict[str, FeeScheduleEntry]) -> None:
    client = _client()
    try:
        blob = json.dumps({code: json.loads(_entry_to_json(entry)) for code, entry in entries.items()})
        await client.set(_DATA_KEY_TEMPLATE.format(table=table), blob)
        await client.set(_REFRESHED_AT_KEY_TEMPLATE.format(table=table), str(time.time()))
    finally:
        await client.aclose()


async def lookup(table: str, code: str) -> FeeScheduleEntry | None:
    client = _client()
    try:
        blob = await client.get(_DATA_KEY_TEMPLATE.format(table=table))
    finally:
        await client.aclose()
    if blob is None:
        return None
    data = json.loads(blob)
    entry_dict = data.get(code.strip().upper())
    if entry_dict is None:
        return None
    entry_dict = dict(entry_dict)
    entry_dict["code_format"] = CodeFormat(entry_dict["code_format"])
    return FeeScheduleEntry(**entry_dict)


async def last_refreshed_at(table: str) -> float | None:
    client = _client()
    try:
        value = await client.get(_REFRESHED_AT_KEY_TEMPLATE.format(table=table))
    finally:
        await client.aclose()
    return float(value) if value is not None else None
