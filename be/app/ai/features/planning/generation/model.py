"""긴 계획 JSON에 필요한 출력 한도를 대화 모델과 분리한다."""

from ....config import AISettings
from ....llm import ainvoke_structured, build_chat_model


PLAN_MAX_OUTPUT_TOKENS = 8192


def build_plan_model(settings: AISettings | None = None, **overrides):
    # 한도를 생략하면 게이트웨이가 2,000토큰에서 응답을 끊었다.
    # 13단계·일정·행동의 JSON과 모델 추론이 같은 출력 예산을 사용한다.
    # 이 게이트웨이는 2,000토큰을 넘는 일반 응답을 거절한다.
    # 전송만 스트리밍하고 ainvoke_structured가 완성본을 모아 검증한다.
    return build_chat_model(settings, **{"max_tokens": PLAN_MAX_OUTPUT_TOKENS, "streaming": True, **overrides})


async def invoke_plan_composition(messages, schema):
    return await ainvoke_structured(messages, schema, model=build_plan_model())
