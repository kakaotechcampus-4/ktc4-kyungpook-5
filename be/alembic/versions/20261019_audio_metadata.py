"""Keep WS audio metadata without retaining original audio files.

Revision ID: 20261019_audio_metadata
Revises: 20261019_candidate_details
"""
from alembic import op
import sqlalchemy as sa

revision = "20261019_audio_metadata"
down_revision = "20261019_candidate_details"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("meeting_audio_chunks", "storage_key", existing_type=sa.String(512), nullable=True)


def downgrade():
    # Null means no retained file, never invent a usable storage location.
    op.execute("UPDATE meeting_audio_chunks SET storage_key = 'not-retained' WHERE storage_key IS NULL")
    op.alter_column("meeting_audio_chunks", "storage_key", existing_type=sa.String(512), nullable=False)
