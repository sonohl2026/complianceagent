from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmbeddingModelInfo:
    """Identifies exactly which model/version produced an embedding, so a
    later model change can be detected and trigger a full reindex
    (build spec §5: "record the exact embedding model and version used;
    support complete re-indexing when the model changes")."""

    name: str
    dimensions: int
    revision: str | None = None


class EmbeddingProvider(Protocol):
    """Local-first embedding interface. A future local model swap or an
    external embedding service can implement this same interface without
    changing any calling code (build spec §5)."""

    @property
    def info(self) -> EmbeddingModelInfo: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of chunk texts (used at ingestion time)."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string (used at retrieval time)."""
        ...
