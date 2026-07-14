from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.prompts import extract_prompt_text
from app.services.analysis.prompts_service import (
    activate_master_prompt_version,
    create_master_prompt_version,
)


def test_extract_prompt_text_accepts_readable_content():
    text = "A" * 500
    assert extract_prompt_text(text) == text


def test_extract_prompt_text_strips_leading_frontmatter():
    text = "---\ntitle: v1\n---\n" + "Real prompt content. " * 20
    result = extract_prompt_text(text)
    assert "title: v1" not in result
    assert "Real prompt content." in result


def test_extract_prompt_text_rejects_near_empty_extraction():
    # Simulates a scanned/image-only PDF with no real text layer.
    with pytest.raises(ValueError, match="no real text layer"):
        extract_prompt_text("scanned image, no OCR")


def test_extract_prompt_text_rejects_whitespace_only():
    with pytest.raises(ValueError):
        extract_prompt_text("   \n\n   ")


def _mock_result(items):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


def _mock_scalar_count(count):
    db = AsyncMock()
    db.scalar.return_value = count
    return db


@pytest.mark.asyncio
async def test_create_master_prompt_version_increments_version_label():
    db = _mock_scalar_count(3)
    db.add = MagicMock()

    version = await create_master_prompt_version(db, content="new prompt text", change_summary="test upload")

    assert version.version_label == "4"
    assert version.is_active is True
    assert version.content == "new prompt text"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_master_prompt_version_deactivates_others_first():
    db = _mock_scalar_count(0)
    db.add = MagicMock()

    await create_master_prompt_version(db, content="x" * 300, change_summary="test")

    # The deactivate-all UPDATE must run before the new row is added, so the
    # new version ends up the sole active one.
    update_statement = db.execute.call_args_list[0].args[0]
    assert str(update_statement.compile(compile_kwargs={"literal_binds": True})).count("is_active") >= 1
    assert db.add.call_args.args[0].is_active is True


@pytest.mark.asyncio
async def test_activate_master_prompt_version_returns_none_for_unknown_id():
    db = AsyncMock()
    db.get.return_value = None

    result = await activate_master_prompt_version(db, "nonexistent-id")

    assert result is None
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_activate_master_prompt_version_rejects_wrong_name():
    # Defense against ever cross-activating a differently-named PromptVersion
    # row (today there's only "master_system_prompt", but the model supports
    # more slots per its own docstring).
    db = AsyncMock()
    other_prompt = MagicMock(name="module_prompt_x")
    other_prompt.name = "some_other_prompt_slot"
    db.get.return_value = other_prompt

    result = await activate_master_prompt_version(db, "some-id")

    assert result is None


@pytest.mark.asyncio
async def test_activate_master_prompt_version_activates_and_returns_it():
    db = AsyncMock()
    target = MagicMock(is_active=False)
    target.name = "master_system_prompt"
    db.get.return_value = target

    result = await activate_master_prompt_version(db, "some-id")

    assert result is target
    assert target.is_active is True
    db.commit.assert_awaited_once()
