"""Versioned master-prompt loading (build spec §21) and module-prompt file
loading. The master prompt is a DB row, editable/versionable from the
Settings UI (upload a PDF/DOCX/MD/TXT, parsed and stored as a new
PromptVersion, never hand-edited in the repo -- see
app.api.v1.prompts::upload_master_prompt); module prompts are static files
checked into prompts/ since they're implementation detail of each pipeline
stage, not something an end user edits per the spec.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.prompt_version import PromptVersion

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)

_MODULE_PROMPT_FILES = {
    "product_fact_extraction": "product_fact_extraction.md",
    "claim_extraction": "claim_extraction.md",
    "regulatory_analysis": "regulatory_analysis.md",
    "coding_analysis": "coding_analysis.md",
    "coverage_analysis": "coverage_analysis.md",
    "payment_analysis": "payment_analysis.md",
    "billing_analysis": "billing_analysis.md",
    "marketing_analysis": "marketing_analysis.md",
    "synthesis": "synthesis.md",
    "citation_audit": "citation_audit.md",
    "chat_qa": "chat_qa.md",
    "material_change_assessment": "material_change_assessment.md",
    "quick_scan_stage1": "quick_scan_stage1_extraction.md",
    "quick_scan_code_candidates": "quick_scan_code_candidates.md",
    "quick_scan_code_refinement": "quick_scan_code_refinement.md",
    "quick_scan_code_relevance_gate": "quick_scan_code_relevance_gate.md",
    "quick_scan_source_divergence": "quick_scan_source_divergence.md",
}


async def get_active_master_prompt(db: AsyncSession) -> PromptVersion:
    """Return the active PromptVersion row, seeding one from
    prompts/master_system_prompt.md on first use if none exists yet."""
    active = await db.scalar(
        select(PromptVersion).where(
            PromptVersion.name == "master_system_prompt", PromptVersion.is_active.is_(True)
        )
    )
    if active is not None:
        return active

    content = _read_master_prompt_file()
    prompt_version = PromptVersion(
        name="master_system_prompt",
        version_label="1",
        content=content,
        is_active=True,
        change_summary="Seeded automatically from prompts/master_system_prompt.md",
    )
    db.add(prompt_version)
    await db.commit()
    await db.refresh(prompt_version)
    return prompt_version


def _read_master_prompt_file() -> str:
    settings = get_settings()
    path = settings.prompts_path / "master_system_prompt.md"
    raw = path.read_text()
    return _FRONTMATTER_RE.sub("", raw, count=1).strip()


def load_module_prompt(stage_name: str) -> str:
    if stage_name not in _MODULE_PROMPT_FILES:
        raise ValueError(f"Unknown pipeline stage {stage_name!r}")
    settings = get_settings()
    path = settings.prompts_path / _MODULE_PROMPT_FILES[stage_name]
    raw = path.read_text()
    return _FRONTMATTER_RE.sub("", raw, count=1).strip()


async def list_master_prompt_versions(db: AsyncSession) -> list[PromptVersion]:
    result = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.name == "master_system_prompt")
        .order_by(PromptVersion.created_at.desc())
    )
    return list(result.scalars().all())


async def get_master_prompt_version(db: AsyncSession, version_id) -> PromptVersion | None:
    version = await db.get(PromptVersion, version_id)
    if version is None or version.name != "master_system_prompt":
        return None
    return version


async def create_master_prompt_version(
    db: AsyncSession, *, content: str, change_summary: str
) -> PromptVersion:
    """Uploads (from Settings) always activate immediately -- there is only
    ever one controlling master prompt for a run, never a staged draft, so
    "upload" and "make this the active version" are the same action here."""
    count = await db.scalar(
        select(func.count()).select_from(PromptVersion).where(PromptVersion.name == "master_system_prompt")
    )
    await db.execute(
        PromptVersion.__table__.update()
        .where(PromptVersion.name == "master_system_prompt")
        .values(is_active=False)
    )
    version = PromptVersion(
        name="master_system_prompt",
        version_label=str((count or 0) + 1),
        content=content,
        is_active=True,
        change_summary=change_summary,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


async def activate_master_prompt_version(db: AsyncSession, version_id) -> PromptVersion | None:
    """Rollback: re-activate a previously-uploaded version (its content is
    untouched, still stored from when it was first uploaded)."""
    version = await get_master_prompt_version(db, version_id)
    if version is None:
        return None
    await db.execute(
        PromptVersion.__table__.update()
        .where(PromptVersion.name == "master_system_prompt")
        .values(is_active=False)
    )
    version.is_active = True
    await db.commit()
    await db.refresh(version)
    return version
