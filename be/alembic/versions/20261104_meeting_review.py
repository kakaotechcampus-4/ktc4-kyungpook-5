"""회의 종료 후 화자와 회의록 검토 상태."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261104_meeting_review'
down_revision = '20261103_operation_cases'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('meeting_reviews',
        sa.Column('id', sa.String(26), primary_key=True),
        sa.Column('meeting_id', sa.String(26), sa.ForeignKey('meetings.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('job_id', sa.String(26), sa.ForeignKey('agent_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('provider_job_id', sa.String(200)), sa.Column('duration_ms', sa.Integer()),
        sa.Column('turns', JSONB()), sa.Column('speaker_names', JSONB()), sa.Column('draft', JSONB()),
        sa.Column('error_code', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('modified_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table('meeting_reviews')
