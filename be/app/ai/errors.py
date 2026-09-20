"""AI 모듈 내부 오류 타입을 정의

BE에 노출할 오류 형식은 합의 대상이며 여기서 정하지 않는다.
호출 계층의 오류 타입은 ML API 규격 확인 후 추가한다.
"""


class AIError(Exception):
    """AI 모듈에서 발생한 오류의 최상위 타입."""


class AIConfigError(AIError):
    """필요한 설정이 없거나 값이 올바르지 않다."""
