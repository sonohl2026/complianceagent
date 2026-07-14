"""add analysis_runs.readiness_score_note

Revision ID: 0008_readiness_score_note
Revises: 0007_compliance_issues
Create Date: 2026-07-14

Supports a deterministic guardrail on the model's self-reported
readiness_score (app.services.analysis.scoring::apply_readiness_score_guardrail):
explains *why* the final score isn't simply whatever the model said, when a
hard internal-consistency rule lowered it (e.g. a STOP verdict can't
coexist with a high readiness score).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008_readiness_score_note"
down_revision: Union[str, None] = "0007_compliance_issues"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_runs", sa.Column("readiness_score_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_runs", "readiness_score_note")
