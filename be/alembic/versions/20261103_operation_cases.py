"""Persist event operation situations and their confirmation results."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261103_operation_cases'
down_revision = '20261103_decision_judge_input'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'operation_cases',
        sa.Column('id', sa.String(26), primary_key=True),
        sa.Column('event_id', sa.String(26), sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('client_request_id', sa.String(100), nullable=False),
        sa.Column('situation', sa.Text(), nullable=False),
        sa.Column('action_id', sa.String(26), sa.ForeignKey('actions.id', ondelete='SET NULL')),
        sa.Column('question_status', sa.String(20), nullable=False),
        sa.Column('result_status', sa.String(20), nullable=False),
        sa.Column('result', JSONB()),
        sa.Column('error_code', sa.String(64)),
        sa.Column('attempt_id', sa.String(32)),
        sa.Column('attempt_started_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('modified_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('event_id', 'client_request_id', name='uq_operation_case_request'),
    )
    op.create_index('ix_operation_cases_event_id', 'operation_cases', ['event_id'])


def downgrade() -> None:
    op.drop_index('ix_operation_cases_event_id', table_name='operation_cases')
    op.drop_table('operation_cases')
