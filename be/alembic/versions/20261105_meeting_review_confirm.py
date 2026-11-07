"""Persist confirmed speaker mappings and review candidate saves."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261105_meeting_review_confirm"
down_revision = ("20261104_meeting_review", "20261101_plan_review")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meeting_reviews", sa.Column("speaker_mappings", JSONB(), nullable=True))
    op.add_column("meeting_reviews", sa.Column("candidate_request_id", sa.String(100), nullable=True))
    op.add_column("meeting_reviews", sa.Column("candidate_hash", sa.String(64), nullable=True))
    op.add_column("meeting_reviews", sa.Column("candidate_ids", JSONB(), nullable=True))
    op.add_column(
        "task_suggestions",
        sa.Column("suggested_assignee_member_id", sa.String(26), nullable=True),
    )
    op.create_foreign_key(
        "fk_task_suggestions_assignee_member",
        "task_suggestions",
        "members",
        ["suggested_assignee_member_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_task_suggestions_assignee_member", "task_suggestions", type_="foreignkey")
    op.drop_column("task_suggestions", "suggested_assignee_member_id")
    op.drop_column("meeting_reviews", "candidate_ids")
    op.drop_column("meeting_reviews", "candidate_hash")
    op.drop_column("meeting_reviews", "candidate_request_id")
    op.drop_column("meeting_reviews", "speaker_mappings")
