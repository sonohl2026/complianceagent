from unittest.mock import AsyncMock, patch

import pytest

from app.services.fee_schedule import cache, refresh
from app.services.fee_schedule.code_format import CodeFormat
from app.services.fee_schedule.types import FeeScheduleEntry

_TEST_TABLE = "pfs"  # refresh_pfs hardcodes "pfs" -- safe under pytest's db-index isolation (cache.py)


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    client = cache._client()
    try:
        await client.delete(
            cache._DATA_KEY_TEMPLATE.format(table=_TEST_TABLE),
            cache._REFRESHED_AT_KEY_TEMPLATE.format(table=_TEST_TABLE),
            cache._DESCRIPTION_INDEX_KEY_TEMPLATE.format(table=_TEST_TABLE),
        )
    finally:
        await client.aclose()


async def test_refresh_pfs_stores_both_entries_and_description_index():
    entries = {
        "76705": FeeScheduleEntry(code="76705", code_format=CodeFormat.CPT_CATEGORY_I, active=True, source="pfs", payment_system="PFS", rate_usd=86.17, status_code="A", description=None),
    }
    raw_descriptions = {"76705": "Echo exam of abdomen"}
    with patch("app.services.fee_schedule.pfs_client.download_and_parse", AsyncMock(return_value=(entries, raw_descriptions))):
        ok = await refresh.refresh_pfs(client=None)
    assert ok is True
    assert (await cache.lookup("pfs", "76705")).rate_usd == 86.17
    assert (await cache.get_description_index("pfs"))["76705"] == "Echo exam of abdomen"


async def test_refresh_pfs_returns_false_on_none_result_without_wiping_existing_data():
    entry = FeeScheduleEntry(code="76705", code_format=CodeFormat.CPT_CATEGORY_I, active=True, source="pfs", payment_system="PFS", rate_usd=86.17, status_code="A", description=None)
    await cache.store_table("pfs", {"76705": entry})

    with patch("app.services.fee_schedule.pfs_client.download_and_parse", AsyncMock(return_value=None)):
        ok = await refresh.refresh_pfs(client=None)
    assert ok is False
    assert (await cache.lookup("pfs", "76705")).rate_usd == 86.17  # untouched


async def test_refresh_pfs_returns_false_on_exception_without_raising():
    with patch("app.services.fee_schedule.pfs_client.download_and_parse", AsyncMock(side_effect=RuntimeError("network down"))):
        ok = await refresh.refresh_pfs(client=None)
    assert ok is False


async def test_ensure_pfs_populated_skips_refresh_when_already_populated():
    entry = FeeScheduleEntry(code="76705", code_format=CodeFormat.CPT_CATEGORY_I, active=True, source="pfs", payment_system="PFS", rate_usd=86.17, status_code="A", description=None)
    await cache.store_table("pfs", {"76705": entry})

    mock_download = AsyncMock(side_effect=AssertionError("should not be called -- already populated"))
    with patch("app.services.fee_schedule.pfs_client.download_and_parse", mock_download):
        await refresh.ensure_pfs_populated(client=None)
    mock_download.assert_not_called()
