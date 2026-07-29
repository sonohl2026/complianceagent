import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import quick_scans
from app.models.enums import JobStatus
from app.schemas.quick_scan import ResolveSourceConflictRequest


def _run(status, retrieval_bundle_json=None, input_snapshot_json=None):
    return MagicMock(
        analysis_type="quick_scan",
        status=status,
        retrieval_bundle_json=retrieval_bundle_json or {},
        input_snapshot_json=input_snapshot_json or {},
    )


async def test_404s_when_run_missing():
    db = AsyncMock()
    db.get.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await quick_scans.resolve_source_conflict(uuid.uuid4(), ResolveSourceConflictRequest(group_index=0), db)
    assert exc_info.value.status_code == 404


async def test_400s_when_not_awaiting_confirmation():
    db = AsyncMock()
    db.get.return_value = _run(JobStatus.COMPLETE)
    with pytest.raises(HTTPException) as exc_info:
        await quick_scans.resolve_source_conflict(uuid.uuid4(), ResolveSourceConflictRequest(group_index=0), db)
    assert exc_info.value.status_code == 400


async def test_400s_when_no_conflict_recorded():
    db = AsyncMock()
    db.get.return_value = _run(JobStatus.AWAITING_CONFIRMATION, retrieval_bundle_json={})
    with pytest.raises(HTTPException) as exc_info:
        await quick_scans.resolve_source_conflict(uuid.uuid4(), ResolveSourceConflictRequest(group_index=0), db)
    assert exc_info.value.status_code == 400


async def test_400s_on_invalid_group_index():
    conflict = {"groups": [{"product_name": "X", "manufacturer": "", "source_indices": [0]}]}
    db = AsyncMock()
    db.get.return_value = _run(JobStatus.AWAITING_CONFIRMATION, retrieval_bundle_json={"source_conflict": conflict})
    with pytest.raises(HTTPException) as exc_info:
        await quick_scans.resolve_source_conflict(uuid.uuid4(), ResolveSourceConflictRequest(group_index=5), db)
    assert exc_info.value.status_code == 400


async def test_merges_only_the_chosen_group_and_requeues(monkeypatch):
    fake_task = MagicMock()
    monkeypatch.setattr(quick_scans, "run_quick_scan_task", fake_task)

    conflict = {
        "groups": [
            {"product_name": "SonoHL", "manufacturer": "", "source_indices": [0]},
            {"product_name": "Impella", "manufacturer": "Abiomed, Inc.", "source_indices": [1]},
        ],
    }
    run = _run(
        JobStatus.AWAITING_CONFIRMATION,
        retrieval_bundle_json={"source_conflict": conflict},
        input_snapshot_json={"per_source_texts": ["SonoHL source text", "Impella source text"], "product_name_hint": None},
    )
    db = AsyncMock()
    db.get.return_value = run

    await quick_scans.resolve_source_conflict(uuid.uuid4(), ResolveSourceConflictRequest(group_index=1), db)

    assert "Impella source text" in run.input_snapshot_json["source_text"]
    assert "SonoHL source text" not in run.input_snapshot_json["source_text"]
    assert run.status == JobStatus.QUEUED
    fake_task.delay.assert_called_once()
