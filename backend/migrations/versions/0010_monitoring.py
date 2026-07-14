"""add scheduled_recrawls, alerts (Milestone 8: monitoring & scheduling)

Revision ID: 0010_monitoring
Revises: 0009_chat_messages
Create Date: 2026-07-14

scheduled_recrawls: recurring recrawl configuration, dispatched by Celery
Beat's monitoring.dispatch_due_recrawls task onto the same crawling.run_crawl
task a manual crawl uses. alerts: material-change flags raised only after a
*scheduled* recrawl (manual one-off crawls don't generate alerts), one row
per changed page the LLM classified as material rather than cosmetic.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_monitoring"
down_revision: Union[str, None] = "0009_chat_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_recrawls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_url", sa.String(2048), nullable=False),
        sa.Column("crawl_settings_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("interval_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scheduled_recrawls_project_id", "scheduled_recrawls", ["project_id"])
    op.create_index("ix_scheduled_recrawls_next_run_at", "scheduled_recrawls", ["next_run_at"])

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("crawl_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("crawl_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_alerts_project_id", "alerts", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_alerts_project_id", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_scheduled_recrawls_next_run_at", table_name="scheduled_recrawls")
    op.drop_index("ix_scheduled_recrawls_project_id", table_name="scheduled_recrawls")
    op.drop_table("scheduled_recrawls")
