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

GUARDRAIL (added after a real incident -- see conversation record): a test
that reused the literal production table name "pfs" for its own throwaway
fixture data, then deleted it in teardown, silently wiped the real cached
fee-schedule data every time the test suite ran against the same Redis
instance as the running app. Rather than rely on every future test author
remembering to use an isolated table name, _client() itself routes to a
completely separate Redis *database* (index 1, vs. production's 0) whenever
PYTEST_CURRENT_TEST is set -- pytest sets this automatically for the
duration of every test (including fixture setup/teardown), so this holds
even if a test still writes under the table name "pfs": it physically
cannot reach the same keyspace as production. Structural, not a naming
convention that can be forgotten again.
"""

import json
import os
import time
from urllib.parse import urlsplit, urlunsplit

import redis.asyncio as redis

from app.config import get_settings
from app.services.fee_schedule.types import CodeFormat, FeeScheduleEntry

_DATA_KEY_TEMPLATE = "fee_schedule:{table}:data"
_REFRESHED_AT_KEY_TEMPLATE = "fee_schedule:{table}:refreshed_at"
_TEST_DB_INDEX = "1"


def _redis_url() -> str:
    base_url = get_settings().redis_url
    if os.environ.get("PYTEST_CURRENT_TEST") is None:
        return base_url
    parts = urlsplit(base_url)
    return urlunsplit(parts._replace(path=f"/{_TEST_DB_INDEX}"))


def _client() -> redis.Redis:
    return redis.from_url(_redis_url(), decode_responses=True)


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
