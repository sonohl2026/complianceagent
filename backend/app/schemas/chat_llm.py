from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class ChatAnswerResult(BaseModel):
    model_config = _STRICT
    answer: str
    citation_labels: list[str]
    confidence: str = Field(description="HIGH | MEDIUM | LOW | INSUFFICIENT_EVIDENCE")
