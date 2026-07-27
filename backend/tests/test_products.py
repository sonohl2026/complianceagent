import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.products import delete_product


def _mock_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


async def test_delete_product_deletes_its_runs_then_itself():
    product_id = uuid.uuid4()
    product = MagicMock(id=product_id)
    run_a, run_b = MagicMock(), MagicMock()

    db = AsyncMock()
    db.get.return_value = product
    db.execute.return_value = _mock_result([run_a, run_b])

    await delete_product(product_id, db)

    assert db.delete.await_args_list == [((run_a,),), ((run_b,),), ((product,),)]
    db.commit.assert_awaited_once()


async def test_delete_product_404s_when_missing():
    db = AsyncMock()
    db.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await delete_product(uuid.uuid4(), db)
    assert exc_info.value.status_code == 404
