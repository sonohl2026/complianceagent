from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.enums import JobStatus
from app.services.jobs.enqueue import enqueue_job


async def test_enqueue_job_succeeds_without_touching_status():
    db = AsyncMock()
    job = MagicMock(status=JobStatus.QUEUED)
    task = MagicMock()
    task.delay = MagicMock()

    await enqueue_job(db, job, task, "arg1", "arg2")

    task.delay.assert_called_once_with("arg1", "arg2")
    db.commit.assert_not_called()


async def test_enqueue_job_marks_job_failed_when_delay_raises():
    db = AsyncMock()
    job = MagicMock(status=JobStatus.QUEUED, error_summary=None)
    task = MagicMock()
    task.delay.side_effect = ModuleNotFoundError("No module named 'jsonschema'")

    with pytest.raises(HTTPException) as exc_info:
        await enqueue_job(db, job, task, "arg1")

    assert exc_info.value.status_code == 502
    assert job.status == JobStatus.FAILED
    assert "jsonschema" in job.error_summary
    db.commit.assert_awaited_once()


async def test_enqueue_job_also_marks_related_objects_failed():
    db = AsyncMock()
    job = MagicMock(status=JobStatus.QUEUED, error_summary=None)
    related = MagicMock(status=JobStatus.QUEUED, error_summary=None)
    task = MagicMock()
    task.delay.side_effect = RuntimeError("broker unreachable")

    with pytest.raises(HTTPException):
        await enqueue_job(db, job, task, also_fail=[related])

    assert related.status == JobStatus.FAILED
    assert "broker unreachable" in related.error_summary
