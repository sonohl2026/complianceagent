"""widen coding_candidates code/code_year columns from varchar to text

Revision ID: 0006_widen_code_cols
Revises: 0005_widen_status_cols
Create Date: 2026-07-13

Real incident this fixes: the compliance pipeline writes an explanatory
disclaimer into code_year (e.g. "[CURRENT-SOURCE VERIFICATION REQUIRED:
confirm applicable FY ICD-10-PCS code set]") when it cannot determine a
concrete code year -- the same "explain why, don't leave it blank"
philosophy already documented for coverage/payment/billing_status in
0005 -- which overflowed the VARCHAR(16) column and crashed the whole
analysis with asyncpg.exceptions.StringDataRightTruncationError. code is
widened alongside it as a preventive measure since it's the same shape of
field (free text when no concrete value is available) and only 32 chars.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_widen_code_cols"
down_revision: Union[str, None] = "0005_widen_status_cols"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("coding_candidates", "code", existing_type=sa.String(32), type_=sa.Text(), existing_nullable=True)
    op.alter_column(
        "coding_candidates", "code_year", existing_type=sa.String(16), type_=sa.Text(), existing_nullable=True
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE coding_candidates SET code = LEFT(code, 32)"))
    bind.execute(sa.text("UPDATE coding_candidates SET code_year = LEFT(code_year, 16)"))
    op.alter_column("coding_candidates", "code", existing_type=sa.Text(), type_=sa.String(32), existing_nullable=True)
    op.alter_column(
        "coding_candidates", "code_year", existing_type=sa.Text(), type_=sa.String(16), existing_nullable=True
    )
