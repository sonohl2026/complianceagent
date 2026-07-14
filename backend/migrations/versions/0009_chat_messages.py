"""add chat_messages (Milestone 7: project-scoped Q&A with cited answers)

Revision ID: 0009_chat_messages
Revises: 0008_readiness_score_note
Create Date: 2026-07-14

One row per message (role "user" or "assistant"), scoped to a project.
citations_json holds resolved {role, document_title, section_title,
page_number, url, quoted_text} dicts -- same shape as a pipeline Citation,
kept as JSON rather than relational rows since chat messages have no
analysis_run_id to hang a Citation off of.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009_chat_messages"
down_revision: Union[str, None] = "0008_readiness_score_note"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chat_messages_project_id", "chat_messages", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_project_id", table_name="chat_messages")
    op.drop_table("chat_messages")
