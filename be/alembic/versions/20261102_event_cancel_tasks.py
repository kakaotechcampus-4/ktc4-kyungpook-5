"""persist event cancellation checklist"""
from alembic import op
import sqlalchemy as sa

revision = "20261102_event_cancel_tasks"
down_revision = "20261102_step_version"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "event_cancel_tasks",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("event_id", sa.String(length=26), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_order", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by", sa.String(length=26), sa.ForeignKey("members.id", ondelete="SET NULL")),
    )
    op.create_index("ix_event_cancel_tasks_event_order", "event_cancel_tasks", ["event_id", "task_order"], unique=True)

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_event_cancel_tasks_event_order")
    op.execute("DROP TABLE IF EXISTS event_cancel_tasks")
