"""BE가 재시도 안내를 정할 수 있게 오류 타입이 갈라져 있는지 확인한다."""

from app.ai.errors import (
    AIConfigError,
    AIEmptyRecordError,
    AIError,
    AIInvalidResponseError,
    AIRetryableError,
    AITimeoutError,
)


def test_재시도할_수_있는_실패는_한_타입으로_잡힌다():
    """BE가 AIRetryableError 하나만 잡으면 재시도 안내 대상이 모두 걸린다."""
    assert issubclass(AITimeoutError, AIRetryableError)
    assert issubclass(AIInvalidResponseError, AIRetryableError)


def test_설정_오류는_재시도_대상이_아니다():
    """주소·키·모델 문제는 다시 보내도 같은 결과라 안내가 달라야 한다."""
    assert not issubclass(AIConfigError, AIRetryableError)
    assert issubclass(AIConfigError, AIError)


def test_빈_기록_오류는_재시도_대상이_아니다():
    """같은 파일을 다시 색인해도 내용이 없어 BE는 바로 FAILED로 바꾼다."""
    assert not issubclass(AIEmptyRecordError, AIRetryableError)
    assert issubclass(AIEmptyRecordError, AIError)
