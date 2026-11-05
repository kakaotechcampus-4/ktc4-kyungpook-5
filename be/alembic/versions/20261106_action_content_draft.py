"""Draft status columns for operating NOTICE/EXTERNAL_SEND action content (#334).

Revision ID: 20261106_action_content_draft
Revises: 20261105_planning_history
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261106_action_content_draft"
down_revision = "20261105_planning_history"
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows have never requested a draft, so they start at NONE with no unknowns.
    op.add_column(
        "actions",
        sa.Column("content_status", sa.String(length=32), nullable=False, server_default="NONE"),
    )
    op.add_column("actions", sa.Column("content_source", sa.String(length=32), nullable=True))
    op.add_column(
        "actions",
        sa.Column(
            "content_unknowns",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column("actions", sa.Column("draft_attempt_id", sa.String(length=32), nullable=True))
    op.add_column(
        "actions", sa.Column("draft_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("actions", sa.Column("draft_error_code", sa.String(length=64), nullable=True))


def downgrade():
    op.drop_column("actions", "draft_error_code")
    op.drop_column("actions", "draft_started_at")
    op.drop_column("actions", "draft_attempt_id")
    op.drop_column("actions", "content_unknowns")
    op.drop_column("actions", "content_source")
    op.drop_column("actions", "content_status")
