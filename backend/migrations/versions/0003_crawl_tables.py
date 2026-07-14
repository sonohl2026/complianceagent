"""add crawl_snapshots and crawled_pages

Revision ID: 0003_crawl_tables
Revises: 0002_vector_index
Create Date: 2026-07-02

Hand-authored and cross-checked against app.models via the same mock-engine
DDL-dump technique used for 0001_initial_schema (see that file's docstring).
crawl_status reuses the same enum values as job_status but is a distinct
Postgres type (crawl_status) so CrawlSnapshot.status isn't coupled to the
generic Job model's enum lifecycle.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_crawl_tables"
down_revision: Union[str, None] = "0002_vector_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

crawl_status_enum = postgresql.ENUM(
    "QUEUED", "RUNNING", "COMPLETE", "FAILED", "CANCELLED", name="crawl_status"
)
robots_status_enum = postgresql.ENUM("ALLOWED", "DISALLOWED", "UNKNOWN", name="robots_status")


def upgrade() -> None:
    op.create_table(
        "crawl_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("root_url", sa.String(2048), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", crawl_status_enum, nullable=False, server_default="QUEUED"),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("crawl_settings_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_summary", sa.Text()),
        sa.Column(
            "previous_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("crawl_snapshots.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "crawled_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("crawl_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(512)),
        sa.Column("http_status", sa.Integer()),
        sa.Column("content_type", sa.String(255)),
        sa.Column("html_path", sa.String(1024)),
        sa.Column("screenshot_path", sa.String(1024)),
        sa.Column("text_path", sa.String(1024)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("word_count", sa.Integer()),
        sa.Column("last_modified", sa.String(255)),
        sa.Column("robots_status", robots_status_enum, nullable=False, server_default="UNKNOWN"),
        sa.Column("changed_from_prior", sa.Boolean()),
        sa.Column("change_summary", sa.Text()),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="SET NULL"),
        ),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crawled_pages_sha256", "crawled_pages", ["sha256"])


def downgrade() -> None:
    op.drop_table("crawled_pages")
    op.drop_table("crawl_snapshots")

    bind = op.get_bind()
    robots_status_enum.drop(bind, checkfirst=True)
    crawl_status_enum.drop(bind, checkfirst=True)
