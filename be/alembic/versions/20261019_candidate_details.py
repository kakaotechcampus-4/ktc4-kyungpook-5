"""Keep interpreted candidate times and separate item assignee from Push recipients.

Revision ID: 20261019_candidate_details
Revises: 20261019_push
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261019_candidate_details"
down_revision = "20261019_push"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_suggestions", sa.Column("kind", sa.String(16), nullable=True))
    op.add_column("task_suggestions", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_suggestions", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_suggestions", sa.Column("unresolved_fields", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default="[]"))
    op.alter_column("task_suggestions", "unresolved_fields", server_default=None)
    op.add_column("confirmed_tasks", sa.Column("assignee_name", sa.String(100), nullable=True))
    op.add_column("confirmed_tasks", sa.Column("assignee_account_id", sa.String(26), nullable=True))
    op.create_foreign_key("fk_confirmed_tasks_assignee_account", "confirmed_tasks", "accounts", ["assignee_account_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_confirmed_tasks_assignee_account", "confirmed_tasks", type_="foreignkey")
    op.drop_column("confirmed_tasks", "assignee_account_id")
    op.drop_column("confirmed_tasks", "assignee_name")
    for column in ("unresolved_fields", "scheduled_at", "due_at", "kind"):
        op.drop_column("task_suggestions", column)
