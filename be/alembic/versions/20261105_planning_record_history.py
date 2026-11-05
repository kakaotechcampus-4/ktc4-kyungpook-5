"""Keep P1 reference lookups across turns and reconnects."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261105_planning_history"
down_revision = ("20261105_merge_heads", "20261105_meeting_review_confirm")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("record_lookup_history", JSONB(), nullable=True))
    # Only the last lookup was stored before this migration. Revision zero identifies
    # that legacy snapshot without pretending to know which turn performed the search.
    op.execute("""
        UPDATE conversations
        SET record_lookup_history = jsonb_build_array(
            jsonb_build_object('revision', 0, 'lookup', last_record_lookup)
        )
        WHERE last_record_lookup IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column("conversations", "record_lookup_history")
