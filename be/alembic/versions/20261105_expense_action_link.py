"""Link expenses recorded automatically from completed event actions (#348)."""

from alembic import op
import sqlalchemy as sa

revision = "20261105_expense_action_link"
down_revision = "20261105_planning_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ExpenseSource는 VARCHAR로 저장해(CHECK 없음) ACTION 값 추가에는 DDL이 필요 없다.
    op.add_column("expenses", sa.Column("action_id", sa.String(26), nullable=True))
    op.create_foreign_key(
        "fk_expenses_action",
        "expenses",
        "actions",
        ["action_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_expenses_action_id", "expenses", ["action_id"])


def downgrade() -> None:
    op.drop_constraint("uq_expenses_action_id", "expenses", type_="unique")
    op.drop_constraint("fk_expenses_action", "expenses", type_="foreignkey")
    op.drop_column("expenses", "action_id")
