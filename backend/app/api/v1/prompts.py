"""Master compliance system prompt management (user-requested): swap the
active master prompt from the Settings UI by uploading a PDF/DOCX/MD/TXT
file, the same way an OpenRouter API key is swapped in -- never by hand-
editing prompts/master_system_prompt.md in the repo. Every upload becomes a
new, permanently-retained PromptVersion row (build spec §21: versioned, not
hardcoded); nothing is ever overwritten, so switching back to an earlier
version is just re-activating its row.
"""

import re
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.prompt_version import PromptVersionDetail, PromptVersionSummary
from app.services.analysis.prompts_service import (
    activate_master_prompt_version,
    create_master_prompt_version,
    get_master_prompt_version,
    list_master_prompt_versions,
)
from app.services.parsing.base import ParsingError
from app.services.parsing.dispatch import parse_document
from app.services.parsing.validation import UploadValidationError, validate_upload

router = APIRouter()

# Deliberately narrower than the general document-upload allow-list
# (app/services/parsing/validation.py also accepts pptx/xlsx/html/csv) --
# none of those make sense as a system prompt document.
_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}

# Below this, something went wrong in extraction (e.g. a scanned/image-only
# PDF with no text layer) even if the file itself parsed without error --
# reject rather than silently activate a near-empty "master prompt".
_MIN_READABLE_CHARACTERS = 200

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def extract_prompt_text(full_text: str) -> str:
    """Strips any leading YAML frontmatter (in case a re-exported/edited copy
    of prompts/master_system_prompt.md is re-uploaded) and confirms the
    result looks like real, readable content. Raises ValueError -- caught by
    the endpoint and turned into a 422 -- rather than silently activating a
    near-empty "master prompt" (e.g. from a scanned/image-only PDF with no
    text layer)."""
    stripped = _FRONTMATTER_RE.sub("", full_text, count=1).strip()
    if len(stripped) < _MIN_READABLE_CHARACTERS:
        raise ValueError(
            f"Only {len(stripped)} character(s) of readable text were extracted -- this usually "
            "means the file has no real text layer (e.g. a scanned PDF with no OCR). Upload a "
            "text-based PDF/DOCX/MD/TXT instead."
        )
    return stripped


@router.get("/prompts/master/versions", response_model=list[PromptVersionSummary])
async def list_master_versions(db: AsyncSession = Depends(get_db)) -> list:
    return await list_master_prompt_versions(db)


@router.get("/prompts/master/versions/{version_id}", response_model=PromptVersionDetail)
async def get_master_version(version_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    version = await get_master_prompt_version(db, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return version


@router.post("/prompts/master/upload", response_model=PromptVersionDetail, status_code=201)
async def upload_master_prompt(
    file: UploadFile = File(...),
    change_summary: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    filename = file.filename or "upload"

    try:
        validated = validate_upload(filename, content)
    except UploadValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc

    if validated.extension not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type {validated.extension!r} for a master prompt. "
            f"Allowed: {sorted(_ALLOWED_EXTENSIONS)}.",
        )

    try:
        parsed = parse_document(validated.extension, content)
    except ParsingError as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse {filename!r}: {exc}") from exc

    try:
        extracted_text = extract_prompt_text(parsed.full_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{exc} (file: {filename!r})") from exc

    version = await create_master_prompt_version(
        db,
        content=extracted_text,
        change_summary=change_summary or f"Uploaded from {filename}",
    )
    return version


@router.post("/prompts/master/versions/{version_id}/activate", response_model=PromptVersionDetail)
async def activate_master_version(version_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    version = await activate_master_prompt_version(db, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return version
