"""Compiles the hybrid-retrieval SQLAlchemy queries to SQL text and checks
their structure. No live database needed -- this catches ORM-construction
bugs (wrong columns, wrong join, wrong filter logic) the way an integration
test against real Postgres would, just without requiring one.
"""

import uuid

from sqlalchemy.dialects import postgresql

from app.models.enums import CollectionType
from app.services.retrieval.hybrid_search import (
    RetrievalFilter,
    build_fulltext_candidate_query,
    build_vector_candidate_query,
)


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_vector_query_uses_cosine_distance_operator():
    sql = _sql(build_vector_candidate_query([0.0] * 384, RetrievalFilter(), 10))
    assert "<=>" in sql
    assert "source_chunks.embedding IS NOT NULL" in sql


def test_fulltext_query_uses_tsquery_and_ts_rank():
    sql = _sql(build_fulltext_candidate_query("FDA cleared", RetrievalFilter(), 10))
    assert "plainto_tsquery" in sql
    assert "ts_rank" in sql
    assert "source_chunks.search_vector IS NOT NULL" in sql


def test_project_filter_still_includes_authority_documents():
    project_id = uuid.uuid4()
    sql = _sql(build_vector_candidate_query([0.0] * 384, RetrievalFilter(project_id=project_id), 10))
    assert "source_documents.project_id" in sql
    assert "source_documents.collection_type" in sql
    assert " OR " in sql


def test_restricted_confidentiality_excluded_by_default():
    sql = _sql(build_vector_candidate_query([0.0] * 384, RetrievalFilter(), 10))
    assert "confidentiality_level NOT IN" in sql


def test_collection_type_filter_narrows_when_explicitly_requested():
    filters = RetrievalFilter(collection_types=[CollectionType.AUTHORITY])
    sql = _sql(build_vector_candidate_query([0.0] * 384, filters, 10))
    assert "source_documents.collection_type IN" in sql


def test_non_current_documents_excluded_by_default():
    sql = _sql(build_vector_candidate_query([0.0] * 384, RetrievalFilter(), 10))
    assert "is_current IS true" in sql
