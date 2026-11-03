"""Optimistic lock version for planning steps."""
from alembic import op
import sqlalchemy as sa

revision = "20261102_step_version"
down_revision = "20261030_action_version"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "steps",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade():
    op.drop_column("steps", "version")
