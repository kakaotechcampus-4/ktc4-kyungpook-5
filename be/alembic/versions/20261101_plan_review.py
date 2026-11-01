"""Plan edit revision on events and the plan_reviews table.

Revision ID: 20261101_plan_review
Revises: 20261030_action_version
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261101_plan_review"
down_revision = "20261030_action_version"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "events",
        sa.Column("plan_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "plan_reviews",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("event_id", sa.String(length=26), nullable=False),
        sa.Column(
            "baseline",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("generated_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("reviewed_revision", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column(
            "items",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "modified_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
        comment="계획 수정 후 AI 검토",
    )


def downgrade():
    op.drop_table("plan_reviews")
    op.drop_column("events", "plan_revision")
