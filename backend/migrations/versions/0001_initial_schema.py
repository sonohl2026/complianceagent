"""initial schema: companies, products, projects, source_documents, source_chunks, jobs

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-02

Hand-authored (not `alembic revision --autogenerate`, since this sandbox has
no live Postgres to introspect). The table/column/enum definitions were
cross-checked against `app.models` by compiling `Base.metadata.create_all`
DDL through a SQLAlchemy mock engine (no DB connection required) and
matching this migration to that output exactly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

collection_type_enum = postgresql.ENUM(
    "COMPANY", "AUTHORITY", "THIRD_PARTY", "COMPETITOR", name="collection_type"
)
authority_level_enum = postgresql.ENUM(
    "LEVEL_1_CONTROLLED_COMPANY_OR_BINDING_AUTHORITY",
    "LEVEL_2_VERIFIED_INTERNAL_EVIDENCE",
    "LEVEL_3_OFFICIAL_EXTERNAL_AUTHORITY",
    "LEVEL_4_WORKING_DRAFT",
    "LEVEL_5_SECONDARY_OR_ANALOG",
    name="authority_level",
)
parse_status_enum = postgresql.ENUM(
    "PENDING", "PROCESSING", "COMPLETE", "FAILED", "QUARANTINED", name="parse_status"
)
embedding_status_enum = postgresql.ENUM(
    "PENDING", "PROCESSING", "COMPLETE", "FAILED", "STALE", name="embedding_status"
)
confidentiality_level_enum = postgresql.ENUM(
    "PUBLIC", "INTERNAL", "RESTRICTED", name="confidentiality_level"
)
job_status_enum = postgresql.ENUM(
    "QUEUED", "RUNNING", "COMPLETE", "FAILED", "CANCELLED", name="job_status"
)

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Enum types are created automatically by op.create_table the first time
    # each Enum column is encountered (checkfirst=True is the SQLAlchemy
    # default) — no explicit CREATE TYPE needed here. Dropping a type is NOT
    # symmetric though, so downgrade() below does drop them explicitly.

    # companies, products, projects, source_documents form a foreign-key
    # cycle (products.status_source_id -> source_documents,
    # source_documents.project_id -> projects,
    # projects.default_product_id -> products). Create all four without
    # inline FKs, then add every FK afterward via op.create_foreign_key.
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("legal_name", sa.String(255)),
        sa.Column("website_url", sa.String(2048)),
        sa.Column("description", sa.Text()),
        sa.Column("headquarters", sa.String(255)),
        sa.Column("jurisdictions", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("product_type", sa.String(255)),
        sa.Column("regulatory_stage", sa.String(64)),
        sa.Column("fda_status", sa.String(255)),
        sa.Column("intended_use", sa.Text()),
        sa.Column("indications_for_use", sa.Text()),
        sa.Column("target_population", sa.Text()),
        sa.Column("intended_user", sa.Text()),
        sa.Column("site_of_service", sa.String(255)),
        sa.Column("care_setting", sa.String(255)),
        sa.Column("clinical_output", sa.Text()),
        sa.Column("ai_role", sa.String(64)),
        sa.Column("hardware_version", sa.String(128)),
        sa.Column("software_version", sa.String(128)),
        sa.Column("model_version", sa.String(128)),
        sa.Column("status_source_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("default_product_id", postgresql.UUID(as_uuid=True)),
        sa.Column("jurisdiction", sa.String(255)),
        sa.Column("target_payers", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("analysis_scope", sa.Text()),
        sa.Column("system_prompt_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "source_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True)),
        sa.Column("collection_type", collection_type_enum, nullable=False),
        sa.Column("source_type", sa.String(128)),
        sa.Column("authority_level", authority_level_enum),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("issuer", sa.String(255)),
        sa.Column("url", sa.String(2048)),
        sa.Column("local_path", sa.String(1024)),
        sa.Column("mime_type", sa.String(255)),
        sa.Column("original_filename", sa.String(512)),
        sa.Column("jurisdiction", sa.String(255)),
        sa.Column("document_category", sa.String(255)),
        sa.Column("publication_date", sa.Date()),
        sa.Column("effective_date", sa.Date()),
        sa.Column("expiration_date", sa.Date()),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.String(64)),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superseded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("parse_status", parse_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("embedding_status", embedding_status_enum, nullable=False, server_default="PENDING"),
        sa.Column(
            "confidentiality_level",
            confidentiality_level_enum,
            nullable=False,
            server_default="INTERNAL",
        ),
        sa.Column("parse_error", sa.Text()),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_source_documents_sha256", "source_documents", ["sha256"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(128), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
        ),
        sa.Column("related_id", postgresql.UUID(as_uuid=True), comment="e.g. the SourceDocument, CrawlSnapshot, or AnalysisRun id"),
        sa.Column("status", job_status_enum, nullable=False, server_default="QUEUED"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_stage", sa.String(255)),
        sa.Column("logs", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("error_summary", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "source_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer()),
        sa.Column("page_number", sa.Integer()),
        sa.Column("section_title", sa.String(512)),
        sa.Column("heading_path", sa.String(1024)),
        sa.Column("start_offset", sa.Integer()),
        sa.Column("end_offset", sa.Integer()),
        sa.Column("citation_label", sa.String(512), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("search_vector", postgresql.TSVECTOR()),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_source_chunks_search_vector", "source_chunks", ["search_vector"], postgresql_using="gin"
    )

    op.create_foreign_key(
        "fk_projects_company_id", "projects", "companies", ["company_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_products_company_id", "products", "companies", ["company_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_products_status_source_id",
        "products",
        "source_documents",
        ["status_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_projects_default_product_id",
        "projects",
        "products",
        ["default_product_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_source_documents_project_id",
        "source_documents",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_source_documents_superseded_by_id",
        "source_documents",
        "source_documents",
        ["superseded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_table("source_chunks")
    op.drop_table("jobs")
    op.drop_constraint("fk_source_documents_superseded_by_id", "source_documents", type_="foreignkey")
    op.drop_constraint("fk_source_documents_project_id", "source_documents", type_="foreignkey")
    op.drop_constraint("fk_projects_default_product_id", "projects", type_="foreignkey")
    op.drop_constraint("fk_products_status_source_id", "products", type_="foreignkey")
    op.drop_table("source_documents")
    op.drop_constraint("fk_products_company_id", "products", type_="foreignkey")
    op.drop_constraint("fk_projects_company_id", "projects", type_="foreignkey")
    op.drop_table("projects")
    op.drop_table("products")
    op.drop_table("companies")

    bind = op.get_bind()
    job_status_enum.drop(bind, checkfirst=True)
    confidentiality_level_enum.drop(bind, checkfirst=True)
    embedding_status_enum.drop(bind, checkfirst=True)
    parse_status_enum.drop(bind, checkfirst=True)
    authority_level_enum.drop(bind, checkfirst=True)
    collection_type_enum.drop(bind, checkfirst=True)
