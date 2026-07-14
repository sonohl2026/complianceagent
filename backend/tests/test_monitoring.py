import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import JobStatus
from app.services.monitoring.material_change import _synthetic_chunk, assess_material_changes
from app.services.monitoring.scheduling import dispatch_due_schedules


def test_synthetic_chunk_carries_label_and_text():
    chunk = _synthetic_chunk("OLD: https://example.com", "old page content")
    assert chunk.citation_label == "OLD: https://example.com"
    assert chunk.text == "old page content"


def _mock_result(items):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


@pytest.mark.asyncio
async def test_dispatch_due_schedules_enqueues_and_advances_next_run(monkeypatch):
    schedule = MagicMock(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        start_url="https://example.com",
        crawl_settings_json={"start_url": "https://example.com"},
        interval_hours=24,
        is_active=True,
        next_run_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [
        _mock_result([schedule]),  # the due-schedules query
    ]
    db.scalar.return_value = None  # no previous COMPLETE snapshot

    mock_task = MagicMock()
    mock_task.delay = MagicMock()

    # dispatch_due_schedules does `from app.workers.crawl_tasks import
    # run_crawl_task` as a deferred import (to avoid a circular import at
    # module load) -- patch sys.modules so that import resolves to a fake
    # module instead of pulling in the real Celery task (and its own
    # @celery_app.task registration machinery).
    import sys
    import types

    fake_module = types.ModuleType("app.workers.crawl_tasks")
    fake_module.run_crawl_task = mock_task
    monkeypatch.setitem(sys.modules, "app.workers.crawl_tasks", fake_module)

    dispatched = await dispatch_due_schedules(db)

    assert dispatched == 1
    mock_task.delay.assert_called_once()
    assert schedule.next_run_at > datetime.now(timezone.utc) + timedelta(hours=23)
    assert schedule.last_run_at is not None


@pytest.mark.asyncio
async def test_dispatch_due_schedules_marks_failed_on_enqueue_error(monkeypatch):
    schedule = MagicMock(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        start_url="https://example.com",
        crawl_settings_json={},
        interval_hours=24,
        is_active=True,
        next_run_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [_mock_result([schedule])]
    db.scalar.return_value = None

    mock_task = MagicMock()
    mock_task.delay = MagicMock(side_effect=RuntimeError("broker down"))

    import sys
    import types

    fake_module = types.ModuleType("app.workers.crawl_tasks")
    fake_module.run_crawl_task = mock_task
    monkeypatch.setitem(sys.modules, "app.workers.crawl_tasks", fake_module)

    dispatched = await dispatch_due_schedules(db)

    assert dispatched == 0


@pytest.mark.asyncio
async def test_dispatch_due_schedules_skips_when_nothing_due():
    db = AsyncMock()
    db.execute.side_effect = [_mock_result([])]

    dispatched = await dispatch_due_schedules(db)

    assert dispatched == 0
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_assess_material_changes_skips_first_ever_crawl():
    # No previous_snapshot_id means there is nothing to compare against --
    # must not attempt any LLM call.
    snapshot = MagicMock(previous_snapshot_id=None)
    db = AsyncMock()

    result = await assess_material_changes(db, MagicMock(), "model", snapshot)

    assert result == []
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_assess_material_changes_skips_when_nothing_changed():
    snapshot = MagicMock(previous_snapshot_id=uuid.uuid4(), id=uuid.uuid4())
    db = AsyncMock()
    db.execute.side_effect = [_mock_result([])]  # no changed_from_prior pages

    llm = AsyncMock()
    result = await assess_material_changes(db, llm, "model", snapshot)

    assert result == []
    llm.structured_completion.assert_not_awaited()
