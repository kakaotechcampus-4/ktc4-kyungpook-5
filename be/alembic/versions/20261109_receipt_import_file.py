"""Keep the uploaded receipt file on receipt_imports; create the records row on confirm (#367)."""

from alembic import op
import sqlalchemy as sa

revision = "20261109_receipt_import_file"
down_revision = "20261106_action_content_draft"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("receipt_imports", sa.Column("file_name", sa.String(255), nullable=True))
    op.add_column("receipt_imports", sa.Column("storage_key", sa.String(512), nullable=True))
    op.add_column("receipt_imports", sa.Column("file_size", sa.BigInteger(), nullable=True))
    # 이미 올린 가져오기는 업로드 때 만든 자료함 기록에서 파일 정보를 옮겨 온다.
    # 기록 자체는 지우지 않는다(확정 안 된 영수증 기록 정리는 별도 판단).
    op.execute(
        """
        UPDATE receipt_imports AS ri
        SET file_name = r.file_name, storage_key = r.storage_key, file_size = r.size
        FROM records AS r
        WHERE ri.record_id = r.id
        """
    )


def downgrade() -> None:
    op.drop_column("receipt_imports", "file_size")
    op.drop_column("receipt_imports", "storage_key")
    op.drop_column("receipt_imports", "file_name")
