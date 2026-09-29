"""Alembic 리비전이 현재 ORM 모델과 맞는지 확인한다."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

pytestmark = pytest.mark.db

EXPECTED_TABLES = {
    "agent_log",
    "auth",
    "clubs",
    "members",
    "events",
    "steps",
    "actions",
    "conversations",
    "messages",
    "records",
}


def _table_names(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_and_downgrade_round_trip(alembic_cfg: Config, db_url: str) -> None:
    command.upgrade(alembic_cfg, "head")
    assert EXPECTED_TABLES <= _table_names(db_url)

    command.downgrade(alembic_cfg, "base")
    assert not EXPECTED_TABLES & _table_names(db_url)

    # 다른 DB 테스트가 기대하는 상태로 되돌린다.
    command.upgrade(alembic_cfg, "head")


def test_models_have_no_unmigrated_changes(
    migrated_db_url: str, alembic_cfg: Config
) -> None:
    # 모델을 바꾸고 리비전을 만들지 않으면 여기서 실패한다.
    command.check(alembic_cfg)
