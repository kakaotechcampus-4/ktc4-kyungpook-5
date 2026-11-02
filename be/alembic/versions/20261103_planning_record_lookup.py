"""Keep the last P1 lookup for restoring the references card without an AI call."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261103_planning_record_lookup"
down_revision = "20261102_event_cancel_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("last_record_lookup", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "last_record_lookup")
