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
