"""add ivfflat cosine index on source_chunks.embedding

Revision ID: 0002_vector_index
Revises: 0001_initial_schema
Create Date: 2026-07-02

Uses vector_cosine_ops to match the cosine_distance() (`<=>`) operator used
by app.services.retrieval.hybrid_search. `lists = 100` is the standard
starting point for small-to-medium corpora (build spec §5 asks for local
embeddings at MVP scale, not massive corpora); revisit if a project's chunk
count grows into the millions.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_vector_index"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_source_chunks_embedding_cosine ON source_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_source_chunks_embedding_cosine")
