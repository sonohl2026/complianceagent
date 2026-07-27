"""move runtime settings from a local JSON file to the database

Revision ID: 0013_runtime_settings_table
Revises: 0012_products_only_ia
Create Date: 2026-07-27

Hosted deployment prep: runtime settings (OpenRouter/Brave API keys, model
slugs, privacy toggles) have lived in a local JSON file on disk
(app/services/storage/settings_store.py) since this app only ran under
docker-compose with a persistent bind-mounted volume. A host like Render's
free tier has no persistent disk across restarts/redeploys, so that file
would silently reset to defaults (including losing the OpenRouter API key)
on every deploy. This moves the same flat JSON blob into one singleton row
in Postgres instead -- same shape, same DEFAULTS-merge semantics, just a
durable place to put it.

If a local app_settings.json already exists (true for this repo's own
existing local dev deployment), its contents seed the new row so the
already-configured local API keys aren't lost the first time this
migration runs.
"""
import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013_runtime_settings_table"
down_revision: Union[str, None] = "0012_products_only_ia"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_SETTINGS_FILE = Path("/app/data/storage/config/app_settings.json")


def upgrade() -> None:
    op.create_table(
        "runtime_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    seed_data = {}
    if _LEGACY_SETTINGS_FILE.exists():
        try:
            seed_data = json.loads(_LEGACY_SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            seed_data = {}

    bind = op.get_bind()
    bind.execute(
        text("INSERT INTO runtime_settings (id, data) VALUES (1, CAST(:data AS JSONB))"),
        {"data": json.dumps(seed_data)},
    )


def downgrade() -> None:
    op.drop_table("runtime_settings")
