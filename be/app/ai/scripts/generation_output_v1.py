"""#276 전 생성 모델 출력 형식(planning-generation-v1). 현재 생성 경로에서는 쓰지 않는다.

v1은 단계 코드 칸에 StepCode 17개(카탈로그 13 + CANCEL_* 4)를 허용했다. 두 곳에서만 쓴다.
- 진단 파일 읽기: #276 전에 저장한 실패 초안에는 CANCEL_*가 들어 있다. 현재 형식으로 읽으면 거절되므로
  이 형식으로 읽어 원래 검증 규칙(catalog_partition)으로 다시 거절되는지 재검사한다.
- 수정 전후 비교: 비교 실행기의 수정 전 변형이 이 형식을 모델에 보낸다.
모델 요청에 실리는 이름·설명·필드가 v1과 같아야 하므로 클래스 이름과 docstring을 바꾸지 않는다.
"""

from pydantic import Field

from app.ai.contracts import ContractModel, ExcludedPlanStep, NonBlankStr, PlanStepFields
from app.ai.features.planning.generation.schemas import ModelAssumption


class ModelStep(PlanStepFields):
    pass


class PlanComposition(ContractModel):
    """LLM의 구조화 출력. 이름·담당·출처 객체는 모델이 쓰지 않는다."""
    steps: tuple[ModelStep, ...] = Field(min_length=1, max_length=13)
    excluded_steps: tuple[ExcludedPlanStep, ...] = ()
    assumptions: tuple[ModelAssumption, ...] = ()
    open_questions: tuple[NonBlankStr, ...] = ()
    warnings: tuple[NonBlankStr, ...] = ()
