"""스키마 공용 기반.

내부(모델·서비스)는 snake_case, API 경계는 camelCase다. 변환은 CamelModel이 맡고
서비스·모델 쪽은 이름을 바꾸지 않는다.
"""

from datetime import UTC, datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel
from app.core.enums import MemberRole


# 일반 동아리원은 서비스 사용자가 아니다. 공개 응답·입력에는 두 역할만 쓴다.
ServiceMemberRole = Literal[MemberRole.OWNER, MemberRole.MANAGER]


def _iso_utc(value: datetime) -> str:
    """명세의 ISO 8601 UTC 표기에 맞춘다. 기본 직렬화는 Z 대신 +00:00으로 나간다."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


UtcDateTime = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


T = TypeVar("T")


class Envelope(CamelModel, Generic[T]):
    """단건 성공 응답 봉투. 목록은 PageMeta 기반 ListResponse를 쓴다."""

    data: T
    meta: None = None


class PageMeta(CamelModel):
    page: int
    size: int
    total_count: int
