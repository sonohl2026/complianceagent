import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.products import rename_product
from app.schemas.product import ProductRename
from app.workers.quick_scan_tasks import _sync_product_name_from_result


async def test_rename_product_sets_name_and_sticky_flag():
    product = MagicMock(name_manually_set=False)
    db = AsyncMock()
    db.get.return_value = product

    await rename_product(uuid.uuid4(), ProductRename(name="  New Name  "), db)

    assert product.name == "New Name"
    assert product.name_manually_set is True
    db.commit.assert_awaited_once()


async def test_rename_product_rejects_blank_name():
    product = MagicMock()
    db = AsyncMock()
    db.get.return_value = product

    with pytest.raises(HTTPException) as exc_info:
        await rename_product(uuid.uuid4(), ProductRename(name="   "), db)
    assert exc_info.value.status_code == 422


async def test_rename_product_404s_when_missing():
    db = AsyncMock()
    db.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await rename_product(uuid.uuid4(), ProductRename(name="X"), db)
    assert exc_info.value.status_code == 404


async def test_sync_skips_manually_renamed_product():
    product = MagicMock(name_manually_set=True)
    product.name = "User's Custom Name"  # MagicMock(name=...) is reserved for its own repr, not an attribute
    db = AsyncMock()
    db.get.return_value = product
    run = MagicMock(product_id=uuid.uuid4(), quick_scan_result_json={"product": {"name": "Stage 3 Resolved Name"}})

    await _sync_product_name_from_result(db, run)

    assert product.name == "User's Custom Name"


async def test_sync_updates_name_when_not_manually_set():
    product = MagicMock(name_manually_set=False)
    product.name = "Old Name"
    db = AsyncMock()
    db.get.return_value = product
    run = MagicMock(product_id=uuid.uuid4(), quick_scan_result_json={"product": {"name": "Stage 3 Resolved Name"}})

    await _sync_product_name_from_result(db, run)

    assert product.name == "Stage 3 Resolved Name"
