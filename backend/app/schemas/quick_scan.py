from pydantic import BaseModel, model_validator


class QuickScanCreateRequest(BaseModel):
    product_id: str | None = None
    source_text: str | None = None
    source_url: str | None = None

    @model_validator(mode="after")
    def require_text_or_url(self) -> "QuickScanCreateRequest":
        if not self.source_text and not self.source_url:
            raise ValueError("Provide either source_text or source_url -- Stage 1 needs actual document/page text.")
        return self


class OverrideItem(BaseModel):
    target: str  # "product" | "pillar"
    key: str
    value: str


class OverrideRequest(BaseModel):
    overrides: list[OverrideItem]


class ResolveSourceConflictRequest(BaseModel):
    """Picks which detected product group to proceed with, after a
    multi-source submission's divergence check found 2+ distinct products
    among the attached sources (see
    quick_scan_tasks.py::_run_source_check and
    source_divergence.py::check_source_divergence)."""

    group_index: int


class ConfirmSiteRequest(BaseModel):
    """Confirms a candidate site -- either the one the web-search fallback
    proposed on a name-only submission's zero-hit (see
    pipeline.py::_find_candidate_site), or a link the user supplies directly
    when correcting an identity they believe the agent got wrong (see
    ProductIdentityEdit's link field). Either way the URL is fetched and
    analyzed like any other link submission. product_name, if given,
    overrides the stored name hint -- lets a user correct the name and
    supply the right link in the same action."""

    url: str
    product_name: str | None = None
