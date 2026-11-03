"""Optimistic lock version for approving and resolving actions.

Revision ID: 20261030_action_version
Revises: 20261019_audio_metadata
"""
from alembic import op
import sqlalchemy as sa

revision = "20261030_action_version"
down_revision = "20261019_audio_metadata"
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows start at 1, the same first version task suggestions use.
    op.add_column(
        "actions",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade():
    op.drop_column("actions", "version")
