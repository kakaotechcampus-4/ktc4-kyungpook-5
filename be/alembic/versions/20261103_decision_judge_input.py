"""Keep the meeting judge request and judge time on each context decision (#241)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261103_decision_judge_input"
down_revision = "20261102_event_cancel_tasks"
branch_labels = None
depends_on = None


# Nullable columns without a default: PostgreSQL only updates the catalog, so
# existing rows are not rewritten and the running app keeps working.
def upgrade() -> None:
    op.add_column("context_decisions", sa.Column("judge_input", postgresql.JSONB(), nullable=True))
    op.add_column("context_decisions", sa.Column("judge_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("context_decisions", "judge_ms")
    op.drop_column("context_decisions", "judge_input")
