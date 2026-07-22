import pytest

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
