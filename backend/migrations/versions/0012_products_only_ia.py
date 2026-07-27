"""flatten projects into products for the MVP lockdown

Revision ID: 0012_products_only_ia
Revises: 0011_quick_scan_columns
Create Date: 2026-07-27

MVP lockdown order: the project/product page hierarchy is scrapped -- the
app is a Products list and a product's results page, full stop. This
migration does the minimum needed to make analysis_runs product-centric
without deleting anything:

1. analysis_runs.project_id becomes nullable -- new submissions (no project
   concept in the UI anymore) won't have one. The column and its data stay;
   nothing is dropped, so this is fully reversible.
2. A new AWAITING_CONFIRMATION value is added to the analysis_status enum,
   for the name-only identity-confirmation pause (spec Step 3).
3. Data backfill: every existing analysis_run that lacks a product_id gets
   one. Where a project already has a default_product_id, its runs are
   pointed at that product. Otherwise a new Product is created (named from
   the run's own resolved quick_scan identity where available, else the
   project's name) under the project's existing company_id, and the project's
   default_product_id is set to it. Zero rows are deleted or altered
   destructively -- this only fills in a previously-optional association.

Crawl/schedule tables (crawl_snapshots, scheduled_recrawls, alerts) are
deliberately NOT touched here: Step 1 hides their UI but keeps their code
paths and existing project_id scoping as-is, since nothing in the new IA
surfaces them.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012_products_only_ia"
down_revision: Union[str, None] = "0011_quick_scan_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("analysis_runs", "project_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.execute("ALTER TYPE analysis_status ADD VALUE IF NOT EXISTS 'AWAITING_CONFIRMATION'")
    _backfill_products(op.get_bind())


def _backfill_products(bind) -> None:
    projects = bind.execute(
        text("SELECT id, company_id, name, default_product_id FROM projects")
    ).mappings().all()

    for project in projects:
        orphan_runs = bind.execute(
            text(
                "SELECT id, quick_scan_result_json FROM analysis_runs "
                "WHERE project_id = :pid AND product_id IS NULL"
            ),
            {"pid": project["id"]},
        ).mappings().all()
        if not orphan_runs:
            continue

        product_id = project["default_product_id"]
        if product_id is None:
            derived_name = project["name"]
            for run in orphan_runs:
                quick_scan_result = run["quick_scan_result_json"] or {}
                resolved_name = (quick_scan_result.get("product") or {}).get("name")
                if resolved_name:
                    derived_name = resolved_name
                    break

            product_id = uuid.uuid4()
            bind.execute(
                text(
                    "INSERT INTO products (id, company_id, name, created_at, updated_at) "
                    "VALUES (:id, :company_id, :name, now(), now())"
                ),
                {"id": product_id, "company_id": project["company_id"], "name": derived_name},
            )
            bind.execute(
                text("UPDATE projects SET default_product_id = :product_id WHERE id = :id"),
                {"product_id": product_id, "id": project["id"]},
            )

        bind.execute(
            text(
                "UPDATE analysis_runs SET product_id = :product_id "
                "WHERE project_id = :project_id AND product_id IS NULL"
            ),
            {"product_id": product_id, "project_id": project["id"]},
        )


def downgrade() -> None:
    # The data backfill is not reversed (it's additive-only: filling in a
    # previously-null association, not information loss). Enum values can't
    # be dropped in Postgres without recreating the type, which isn't
    # warranted for a downgrade path off an MVP lockdown migration.
    op.alter_column("analysis_runs", "project_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
