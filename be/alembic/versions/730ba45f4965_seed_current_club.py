"""seed current club

Revision ID: 730ba45f4965
Revises: dad0675150f5
Create Date: 2026-09-30 02:00:39.043832

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '730ba45f4965'
down_revision: Union[str, Sequence[str], None] = 'dad0675150f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 인증 도입 전까지 현재 사용자로 쓰는 동아리·회원 (#63).
# 동아리 id는 FE 동아리 찾기 데모 목업(#77)과 맞춰 두었다.
# 이후 모델 변경에 흔들리지 않도록 app.models 를 import 하지 않는다.
CLUB_ID = "clb_3a71c0"
MEMBER_ID = "mbr_3a71c0"

clubs = sa.table(
    "clubs",
    sa.column("id", sa.String),
    sa.column("name", sa.String),
    sa.column("category", sa.String),
)
members = sa.table(
    "members",
    sa.column("id", sa.String),
    sa.column("club_id", sa.String),
    sa.column("name", sa.String),
    sa.column("role", sa.String),
    sa.column("status", sa.String),
    sa.column("notify_approval_pending", sa.Boolean),
    sa.column("notify_step_delay", sa.Boolean),
)


def upgrade() -> None:
    op.bulk_insert(
        clubs,
        [{"id": CLUB_ID, "name": "컴퓨터학부 학술동아리 ○○", "category": "ACADEMIC"}],
    )
    # NOT NULL 컬럼의 기본값은 모델(default=)에만 있고 DB에는 없다.
    # bulk_insert는 모델을 거치지 않으므로 직접 채운다.
    op.bulk_insert(
        members,
        [
            {
                "id": MEMBER_ID,
                "club_id": CLUB_ID,
                "name": "김지훈",
                "role": "OWNER",
                "status": "ACTIVE",
                "notify_approval_pending": True,
                "notify_step_delay": True,
            }
        ],
    )


def downgrade() -> None:
    op.execute(members.delete().where(members.c.id == MEMBER_ID))
    op.execute(clubs.delete().where(clubs.c.id == CLUB_ID))
