import redis.asyncio as redis_lib
import pytest

from app.config import get_settings
from app.services.fee_schedule import cache
from app.services.fee_schedule.types import CodeFormat, FeeScheduleEntry

_TEST_TABLE = "test_pfs_cache"


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    client = cache._client()
    try:
        await client.delete(
            cache._DATA_KEY_TEMPLATE.format(table=_TEST_TABLE),
            cache._REFRESHED_AT_KEY_TEMPLATE.format(table=_TEST_TABLE),
        )
    finally:
        await client.aclose()


async def test_store_and_lookup_round_trip():
    entry = FeeScheduleEntry(
        code="76705", code_format=CodeFormat.CPT_CATEGORY_I, active=True,
        source="pfs", payment_system="PFS", rate_usd=86.17, status_code="A", description=None,
    )
    await cache.store_table(_TEST_TABLE, {"76705": entry})
    found = await cache.lookup(_TEST_TABLE, "76705")
    assert found == entry


async def test_lookup_is_case_insensitive():
    entry = FeeScheduleEntry(
        code="A4238", code_format=CodeFormat.HCPCS_LEVEL_II, active=False,
        source="pfs", payment_system="PFS", rate_usd=None, status_code="X", description="Adju cgm supply allowance",
    )
    await cache.store_table(_TEST_TABLE, {"A4238": entry})
    assert await cache.lookup(_TEST_TABLE, "a4238") == entry


async def test_lookup_missing_code_returns_none():
    await cache.store_table(_TEST_TABLE, {})
    assert await cache.lookup(_TEST_TABLE, "99999") is None


async def test_lookup_before_any_store_returns_none():
    assert await cache.lookup("nonexistent_table_never_stored", "76705") is None


async def test_last_refreshed_at_set_on_store():
    assert await cache.last_refreshed_at(_TEST_TABLE) is None
    await cache.store_table(_TEST_TABLE, {})
    assert await cache.last_refreshed_at(_TEST_TABLE) is not None


async def test_pytest_writes_never_reach_production_db_even_under_the_real_table_name():
    # The actual incident this guards against: a test reused the literal
    # production table name "pfs", so its setup/teardown clobbered real
    # cached data every time the suite ran. This proves the fix holds even
    # in that exact failure mode -- write under pytest using the real name
    # "pfs", then check via a connection pinned to production's db (0,
    # bypassing cache._client()'s own test detection) that nothing landed
    # there.
    key = cache._DATA_KEY_TEMPLATE.format(table="pfs")
    prod_client = redis_lib.from_url(get_settings().redis_url, decode_responses=True)
    try:
        preexisting = await prod_client.get(key)
        try:
            entry = FeeScheduleEntry(
                code="00000", code_format=CodeFormat.UNKNOWN, active=True,
                source="pfs", payment_system="PFS", rate_usd=1.0, status_code="A", description=None,
            )
            await cache.store_table("pfs", {"00000": entry})  # under pytest -- should land in the test db, not here
            assert await prod_client.get(key) == preexisting  # production db untouched
        finally:
            client = cache._client()
            try:
                await client.delete(key, cache._REFRESHED_AT_KEY_TEMPLATE.format(table="pfs"))
            finally:
                await client.aclose()
    finally:
        await prod_client.aclose()
