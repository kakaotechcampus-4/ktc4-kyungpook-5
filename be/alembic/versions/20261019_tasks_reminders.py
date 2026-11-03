"""Confirmed meeting items and one-shot designated-recipient reminders.

Revision ID: 20261019_tasks_reminders
Revises: 20261019_record_chunks
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261019_tasks_reminders"
down_revision = "20261019_record_chunks"
branch_labels = None
depends_on = None


def _identity_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(26), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "confirmed_tasks",
        *_identity_columns(),
        sa.Column("club_id", sa.String(26), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("suggestion_id", sa.String(26), sa.ForeignKey("task_suggestions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("confirmation_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("confirmed_by", sa.String(26), sa.ForeignKey("members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("suggestion_id", name="uq_confirmed_tasks_suggestion"),
    )
    op.create_index("ix_confirmed_tasks_club_status", "confirmed_tasks", ["club_id", "status"])
    op.create_table(
        "task_reminders",
        *_identity_columns(),
        sa.Column("club_id", sa.String(26), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("confirmed_item_id", sa.String(26), sa.ForeignKey("confirmed_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recipient_account_ids", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("confirmed_item_id", name="uq_task_reminders_item"),
    )
    op.create_index("ix_task_reminders_status_at", "task_reminders", ["status", "reminder_at"])


def downgrade() -> None:
    op.drop_index("ix_task_reminders_status_at", table_name="task_reminders")
    op.drop_table("task_reminders")
    op.drop_index("ix_confirmed_tasks_club_status", table_name="confirmed_tasks")
    op.drop_table("confirmed_tasks")
