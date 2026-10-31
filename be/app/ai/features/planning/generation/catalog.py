"""고정 단계의 표시 정보와 허용 행동. 모델은 코드를 고르고 코드는 속성을 보완한다."""

from app.core.enums import ActionType, StepActor, StepCode, StepPhase

from ....contracts import ContractModel
from ....planning_catalog import (
    PLANNING_STEP_ACTIONS,
    PLANNING_STEP_ACTORS,
    PLANNING_PHASE_ORDER,
    PLANNING_STEP_NAMES,
    PLANNING_STEP_PHASES,
)


class CatalogStep(ContractModel):
    code: StepCode
    name: str
    phase: StepPhase
    actor: StepActor
    actions: tuple[ActionType, ...] = ()


# 속성은 planning_catalog가 들고 있다. 같은 표를 BE 서비스도 읽는다 — 단계를
# 다시 넣을 때 묶음·담당이 어긋나지 않게 하기 위해서다.
CATALOG = tuple(
    CatalogStep(
        code=code,
        name=name,
        phase=PLANNING_STEP_PHASES[code],
        actor=PLANNING_STEP_ACTORS[code],
        actions=PLANNING_STEP_ACTIONS.get(code, ()),
    )
    for code, name in PLANNING_STEP_NAMES.items()
)
BY_CODE = {item.code: item for item in CATALOG}
PHASE_ORDER = PLANNING_PHASE_ORDER
