"""마이그레이션 head가 하나인지 DB 없이 확인한다.

두 브랜치가 같은 부모에서 각각 마이그레이션을 만들면 git 충돌 없이 head가 둘이 된다.
그러면 `alembic upgrade head`가 "Multiple head revisions" 오류로 멈추고, 운영 배포 전 검사도
맞지 않는다(11-05에 두 번 일어남). PR 단계의 CI에서 먼저 실패시켜 머지 전에 부모를 고치게 한다.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def test_alembic_has_single_head() -> None:
    heads = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads()
    assert len(heads) == 1, (
        f"마이그레이션 head가 {len(heads)}개입니다: {sorted(heads)}. "
        "새 마이그레이션의 down_revision을 최신 develop의 head로 바꾸세요."
    )
