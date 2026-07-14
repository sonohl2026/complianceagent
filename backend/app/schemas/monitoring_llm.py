from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class MaterialChangeEntry(BaseModel):
    model_config = _STRICT
    canonical_url: str
    is_material: bool
    category: str = Field(
        description="NEW_CLAIM | REMOVED_DISCLAIMER | FDA_STATUS_LANGUAGE | PRICING | "
        "INTENDED_USE | COSMETIC | OTHER"
    )
    summary: str = Field(description="One or two sentences on what changed and why it matters (or doesn't)")


class MaterialChangeAssessmentResult(BaseModel):
    model_config = _STRICT
    entries: list[MaterialChangeEntry]
