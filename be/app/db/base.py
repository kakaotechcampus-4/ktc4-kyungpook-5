"""선언적 기반 클래스, 전 테이블 공통 컬럼, 공유 컬럼 타입.

id·created_at·modified_at은 모든 테이블에 동일하게 붙으므로 믹스인으로 둔다.
DB 종속 타입도 여기 모아두고 모델은 이름만 쓴다.
"""

from datetime import datetime
from typing import ClassVar

from nanoid import generate
from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.core.enums import CodeEnum

# id = "{3자 접두어}_{21자}" = 25자. 컬럼은 여유를 둬 26자로 잡는다.
ID_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
ID_RANDOM_SIZE = 21
ID_LENGTH = 26


def new_id(prefix: str) -> str:
    return f"{prefix}_{generate(ID_ALPHABET, ID_RANDOM_SIZE)}"


def fk(target: str, *, ondelete: str = "CASCADE") -> ForeignKey:
    """id 컬럼을 가리키는 외래키. 모든 PK가 같은 타입이라 길이를 반복하지 않는다."""
    return ForeignKey(target, ondelete=ondelete)


class Base(DeclarativeBase):
    pass


class IdMixin:
    """접두어가 붙은 문자열 PK.

    하위 클래스는 __id_prefix__를 3자 소문자로 정의한다.
    DB 조회 없이 애플리케이션에서 만들며, 순번이 아니라 총 건수가 드러나지 않는다.
    """

    __id_prefix__: ClassVar[str]

    @declared_attr
    def id(cls) -> Mapped[str]:  # noqa: N805
        prefix = cls.__id_prefix__
        return mapped_column(
            String(ID_LENGTH),
            primary_key=True,
            default=lambda: new_id(prefix),
        )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# --- 공유 컬럼 타입 -----------------------------------------------------

# PostgreSQL에서는 JSONB, 그 외(테스트용 SQLite 등)에서는 JSON으로 컴파일된다.
JsonB = JSON().with_variant(JSONB(), "postgresql")

# 가장 긴 코드는 APPROVAL_REQUIRED(17자). 여유를 둔다.
ENUM_LENGTH = 32


def enum_column(enum_cls: type[CodeEnum]) -> Enum:
    """CodeEnum을 코드 문자열 그대로 VARCHAR에 저장한다.

    DB 네이티브 ENUM 타입과 CHECK 제약을 쓰지 않는다. 값을 추가할 때마다
    마이그레이션이 필요해지기 때문이며, 유효성은 애플리케이션에서 본다.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        length=ENUM_LENGTH,
        values_callable=lambda cls: [member.value for member in cls],
    )
