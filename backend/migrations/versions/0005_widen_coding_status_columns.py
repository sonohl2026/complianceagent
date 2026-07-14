"""widen coding_candidates status columns from varchar(64) to text

Revision ID: 0005_widen_status_cols
Revises: 0004_analysis_tables
Create Date: 2026-07-08

Real incident this fixes: the compliance pipeline writes full explanatory
sentences into coverage_status/payment_status/billing_status (e.g.
"UNDETERMINED -- coverage is payer- and policy-specific and cannot be
assessed without verified FDA status [CURRENT-SOURCE VERIFICATION
REQUIRED]"), which is exactly the intended behavior (explain *why*
something is unresolved rather than collapse it to a short code) but
overflowed the VARCHAR(64) columns those fields were originally given,
raising asyncpg.exceptions.StringDataRightTruncationError and rolling back
the whole analysis.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_widen_status_cols"
down_revision: Union[str, None] = "0004_analysis_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = ["coverage_status", "payment_status", "billing_status"]


def upgrade() -> None:
    for column in COLUMNS:
        op.alter_column(
            "coding_candidates", column, existing_type=sa.String(64), type_=sa.Text(), existing_nullable=True
        )


def downgrade() -> None:
    # Not perfectly reversible: any value longer than 64 chars already
    # written would fail to downgrade. Truncate defensively rather than
    # leave the downgrade broken.
    bind = op.get_bind()
    for column in COLUMNS:
        bind.execute(sa.text(f"UPDATE coding_candidates SET {column} = LEFT({column}, 64)"))
        op.alter_column(
            "coding_candidates", column, existing_type=sa.Text(), type_=sa.String(64), existing_nullable=True
        )
