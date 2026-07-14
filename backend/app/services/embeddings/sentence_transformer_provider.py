"""Local CPU-by-default embedding provider backed by Sentence Transformers.

Never calls out to an external embedding API. The model is loaded once per
process (module-level cache) since loading is comparatively expensive; the
worker process embeds in batches (config: EMBEDDING_BATCH_SIZE) rather than
one chunk at a time.
"""

from functools import lru_cache

from app.config import get_settings
from app.services.embeddings.base import EmbeddingModelInfo


class SentenceTransformerProvider:
    def __init__(self, model_name: str | None = None, device: str | None = None):
        settings = get_settings()
        self._model_name = model_name or settings.local_embedding_model
        self._device = device or settings.embedding_device
        self._batch_size = settings.embedding_batch_size
        self._model = _load_model(self._model_name, self._device)
        dims = self._model.get_sentence_embedding_dimension()
        self._info = EmbeddingModelInfo(name=self._model_name, dimensions=dims)

    @property
    def info(self) -> EmbeddingModelInfo:
        return self._info

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = self._model.encode([text], show_progress_bar=False, normalize_embeddings=True)[0]
        return vector.tolist()


@lru_cache(maxsize=4)
def _load_model(model_name: str, device: str):
    # Imported lazily: sentence-transformers/torch are heavy and unnecessary
    # for API-only code paths (e.g. running just the FastAPI app for
    # CRUD endpoints without ever touching embeddings).
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=device)


_default_provider: SentenceTransformerProvider | None = None


def get_embedding_provider() -> SentenceTransformerProvider:
    global _default_provider
    if _default_provider is None:
        _default_provider = SentenceTransformerProvider()
    return _default_provider
