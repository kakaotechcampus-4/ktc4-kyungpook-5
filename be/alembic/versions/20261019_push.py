"""Account-owned Web Push browser subscriptions.

Revision ID: 20261019_push
Revises: 20261019_tasks_reminders
"""

from alembic import op
import sqlalchemy as sa

revision = "20261019_push"
down_revision = "20261019_tasks_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("account_id", sa.String(26), nullable=False),
        sa.Column("endpoint_hash", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("expiration_time", sa.DateTime(timezone=True)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("endpoint_hash", name="uq_push_subscriptions_endpoint_hash"),
    )
    op.create_index("ix_push_subscriptions_account_id", "push_subscriptions", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_push_subscriptions_account_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
