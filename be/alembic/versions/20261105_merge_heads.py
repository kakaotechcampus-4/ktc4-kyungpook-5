"""계획 검토와 회의 검토 마이그레이션의 두 갈래를 하나로 잇는다.

Revision ID: 20261105_merge_heads
Revises: 20261101_plan_review, 20261104_meeting_review

두 마이그레이션이 같은 20261103_operation_cases에서 갈라져 head가 둘이 됐다.
그러면 `alembic upgrade head`가 실패하고 배포 전 검사(deployment_preflight.py)도 맞지 않는다.
둘은 서로 다른 테이블만 만들므로 스키마는 바꾸지 않고 순서만 하나로 합친다.
"""

revision = "20261105_merge_heads"
down_revision = ("20261101_plan_review", "20261104_meeting_review")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
