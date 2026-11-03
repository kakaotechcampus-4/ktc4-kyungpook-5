"""Permanent record chunks and explicit indexing result.

Revision ID: 20261019_record_chunks
Revises: 2ffdcc2aee5b
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import VECTOR

revision = "20261019_record_chunks"
down_revision = "2ffdcc2aee5b"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("records", sa.Column("index_error", postgresql.JSONB(), nullable=True))
    op.create_table(
        "record_chunks",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("record_id", sa.String(26), sa.ForeignKey("records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("location", postgresql.JSONB(), nullable=False),
        sa.Column("block_indexes", postgresql.JSONB(), nullable=False),
        sa.Column("embedding", VECTOR(1536), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("record_id", "chunk_index"),
    )
    op.create_index("ix_record_chunks_record_id", "record_chunks", ["record_id"])


def downgrade():
    op.drop_table("record_chunks")
    op.drop_column("records", "index_error")
