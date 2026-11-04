"""긴 계획 JSON에 필요한 출력 한도와 추론 깊이를 대화 모델과 분리한다."""

from ....config import AISettings
from ....llm import ainvoke_structured, build_chat_model


PLAN_MAX_OUTPUT_TOKENS = 8192
# 생성 모델의 추론 깊이(#264). 기본값(미지정)과 같은 실행 안에서 번갈아 30건씩 쟀을 때(2026-11-04)
# 추론 토큰 p50이 516 → 240, 생성 호출 p50이 15.4 → 11.1초로 줄었다.
# 계획 검증 통과(26 → 28/30)와 초안 단계 수(중앙값 13)는 줄지 않았다.
# 근거: docs/planning/evaluation-results/planning-generation-reasoning-2026-11-04/README.md
# 채팅 생성(G1)에서는 처음에 low 통과가 적었다(29 → 25/30, 취소 단계 코드 실패). 출력 형식을 카탈로그 13개로 줄인 뒤(#276)
# 다시 재니 둘 다 30/30이고 생성 호출 p50이 18.9 → 10.7초로 줄어 low를 유지했다.
# 근거: docs/planning/evaluation-results/planning-generation-step-codes-2026-11-04/README.md
PLAN_REASONING = {"effort": "low"}


def build_plan_model(settings: AISettings | None = None, **overrides):
    # 한도를 생략하면 게이트웨이가 2,000토큰에서 응답을 끊었다.
    # 13단계·일정·행동의 JSON과 모델 추론이 같은 출력 예산을 사용한다.
    # 이 게이트웨이는 2,000토큰을 넘는 일반 응답을 거절한다.
    # 전송만 스트리밍하고 ainvoke_structured가 완성본을 모아 검증한다.
    return build_chat_model(settings, **{"max_tokens": PLAN_MAX_OUTPUT_TOKENS, "streaming": True,
                                         "reasoning": PLAN_REASONING, **overrides})


async def invoke_plan_composition(messages, schema):
    return await ainvoke_structured(messages, schema, model=build_plan_model())
