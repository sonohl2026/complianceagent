import math

import pytest


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b)


@pytest.fixture(scope="module")
def provider():
    try:
        from app.services.embeddings.sentence_transformer_provider import (
            SentenceTransformerProvider,
        )

        return SentenceTransformerProvider()
    except Exception as exc:  # pragma: no cover - only triggers offline / no local model cache
        pytest.skip(f"local embedding model unavailable in this environment: {exc}")


def test_embedding_dimensions_match_pgvector_column(provider):
    from app.models.source_chunk import EMBEDDING_DIM

    vectors = provider.embed_documents(["SonoHL is an investigational device."])
    assert len(vectors[0]) == EMBEDDING_DIM
    assert provider.info.dimensions == EMBEDDING_DIM


def test_query_embeds_closer_to_relevant_document():
    from app.services.embeddings.sentence_transformer_provider import SentenceTransformerProvider

    try:
        provider = SentenceTransformerProvider()
    except Exception as exc:
        pytest.skip(f"local embedding model unavailable in this environment: {exc}")

    docs = [
        "SonoHL is not cleared or approved by the FDA and is investigational.",
        "The wearable vest is available in small, medium, and large sizes.",
    ]
    vectors = provider.embed_documents(docs)
    query_vector = provider.embed_query("Has SonoHL received FDA clearance?")

    fda_similarity = _cosine(query_vector, vectors[0])
    sizing_similarity = _cosine(query_vector, vectors[1])
    assert fda_similarity > sizing_similarity


def test_embed_documents_empty_list_returns_empty(provider):
    assert provider.embed_documents([]) == []
