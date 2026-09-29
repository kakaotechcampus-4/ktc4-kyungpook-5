"""seed current club

Revision ID: 730ba45f4965
Revises: 89e7125c6db4
Create Date: 2026-09-30 02:00:39.043832

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '730ba45f4965'
down_revision: Union[str, Sequence[str], None] = '89e7125c6db4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 인증 도입 전까지 현재 사용자로 쓰는 동아리·회원 (#63).
# 동아리 값은 FE CURRENT_CLUB_ID·로그인 목업(auth/api.ts)과 같다.
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
)


def upgrade() -> None:
    op.bulk_insert(
        clubs, [{"id": CLUB_ID, "name": "컴퓨터학부 학술동아리 ○○", "category": "학술"}]
    )
    op.bulk_insert(
        members,
        [{"id": MEMBER_ID, "club_id": CLUB_ID, "name": "김지훈", "role": "OWNER"}],
    )


def downgrade() -> None:
    op.execute(members.delete().where(members.c.id == MEMBER_ID))
    op.execute(clubs.delete().where(clubs.c.id == CLUB_ID))
