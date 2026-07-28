"""add products.name_manually_set

Revision ID: 0014_product_name_manually_set
Revises: 0013_runtime_settings_table
Create Date: 2026-07-28

User-requested rename option for a product's title (Products list and the
results page). Without this flag, every completed quick_scan run silently
overwrites Product.name with whatever Stage 3 resolved
(quick_scan_tasks.py::_sync_product_name_from_result) -- a user's manual
rename would just get undone the next time they re-run a scan on that
product. This flag makes a manual rename sticky: once set, the
auto-sync-from-result step skips that product instead of overwriting it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0014_product_name_manually_set"
down_revision: Union[str, None] = "0013_runtime_settings_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("name_manually_set", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("products", "name_manually_set")
