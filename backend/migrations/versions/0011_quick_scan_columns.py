"""add quick_scan columns to analysis_runs

Revision ID: 0011_quick_scan_columns
Revises: 0010_monitoring
Create Date: 2026-07-21

The quick_scan pipeline (v2 spec) produces a different, fixed shape --
product identity, three scores, six fixed pillars -- that doesn't map onto
the existing Finding/CodingCandidate/FindingDomain relational schema (see
docs discussion at implementation time). Rather than force a lossy remap
onto FindingDomain's 16 values, this stores the quick_scan result as JSONB
directly on analysis_runs, the same pattern already used for
token_usage_json/cost_json/input_snapshot_json on this exact table. Existing
FULL_COMPLIANCE_ANALYSIS rows are unaffected (all defaults).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011_quick_scan_columns"
down_revision: Union[str, None] = "0010_monitoring"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_runs", sa.Column("quick_scan_result_json", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("analysis_runs", sa.Column("retrieval_bundle_json", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("analysis_runs", sa.Column("retrieval_progress_json", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("analysis_runs", sa.Column("overrides_json", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("analysis_runs", sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("analysis_runs", "revision")
    op.drop_column("analysis_runs", "overrides_json")
    op.drop_column("analysis_runs", "retrieval_progress_json")
    op.drop_column("analysis_runs", "retrieval_bundle_json")
    op.drop_column("analysis_runs", "quick_scan_result_json")
