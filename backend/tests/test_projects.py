import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.projects import delete_project
from app.services.storage.file_storage import LocalFileStorage


def _mock_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    result.all.return_value = rows
    return result


async def test_delete_project_removes_orphaned_document_and_crawl_files(monkeypatch, tmp_path):
    storage = LocalFileStorage(root=tmp_path)
    doc_path = storage.save_bytes("uploads", b"doc content", suffix=".pdf")
    html_path = storage.save_bytes("crawls", b"<html></html>", suffix=".html")
    screenshot_path = storage.save_bytes("crawls", b"png bytes", suffix=".png")

    monkeypatch.setattr("app.api.v1.projects.get_storage", lambda: storage)

    project_id = uuid.uuid4()
    project = MagicMock(id=project_id)

    db = AsyncMock()
    db.get.return_value = project
    db.execute.side_effect = [
        _mock_result([doc_path]),  # SourceDocument.local_path query
        _mock_result([(html_path, screenshot_path, None)]),  # CrawledPage path query
    ]

    await delete_project(project_id, db)

    db.delete.assert_awaited_once_with(project)
    db.commit.assert_awaited_once()
    assert not storage.exists(doc_path)
    assert not storage.exists(html_path)
    assert not storage.exists(screenshot_path)


async def test_delete_project_404s_when_missing():
    db = AsyncMock()
    db.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await delete_project(uuid.uuid4(), db)
    assert exc_info.value.status_code == 404
