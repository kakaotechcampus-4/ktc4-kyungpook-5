"""고정 단계의 표시 정보와 허용 행동. 모델은 코드를 고르고 코드는 속성을 보완한다."""

from app.core.enums import ActionType, StepActor, StepCode, StepPhase

from ....contracts import ContractModel
from ....planning_catalog import PLANNING_STEP_NAMES


class CatalogStep(ContractModel):
    code: StepCode
    name: str
    phase: StepPhase
    actor: StepActor
    actions: tuple[ActionType, ...] = ()


# CONFIRMATION은 운영 중 필요한 질문이 생겼을 때 만든다. 계획에 미리 생성하지 않는다.
CATALOG = (
    CatalogStep(code=StepCode.ASSIGN_ROLES, name=PLANNING_STEP_NAMES[StepCode.ASSIGN_ROLES], phase=StepPhase.PREPARATION, actor=StepActor.MANUAL),
    CatalogStep(code=StepCode.RESEARCH_VENUE, name=PLANNING_STEP_NAMES[StepCode.RESEARCH_VENUE], phase=StepPhase.PREPARATION, actor=StepActor.MANUAL),
    CatalogStep(code=StepCode.DEMAND_SURVEY, name=PLANNING_STEP_NAMES[StepCode.DEMAND_SURVEY], phase=StepPhase.PREPARATION,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.NOTICE,)),
    CatalogStep(code=StepCode.RECRUIT_NOTICE, name=PLANNING_STEP_NAMES[StepCode.RECRUIT_NOTICE], phase=StepPhase.RECRUITING,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.NOTICE,)),
    CatalogStep(code=StepCode.CHECK_RESPONSES, name=PLANNING_STEP_NAMES[StepCode.CHECK_RESPONSES], phase=StepPhase.RECRUITING,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.NOTICE,)),
    CatalogStep(code=StepCode.CONFIRM_DETAILS, name=PLANNING_STEP_NAMES[StepCode.CONFIRM_DETAILS], phase=StepPhase.RECRUITING, actor=StepActor.AI),
    CatalogStep(code=StepCode.BOOK_VENUE, name=PLANNING_STEP_NAMES[StepCode.BOOK_VENUE], phase=StepPhase.RECRUITING,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.CONTRACT, ActionType.TRANSFER)),
    CatalogStep(code=StepCode.COLLECT_FEES, name=PLANNING_STEP_NAMES[StepCode.COLLECT_FEES], phase=StepPhase.RECRUITING,
                actor=StepActor.AI, actions=(ActionType.NOTICE, ActionType.EXTERNAL_SEND)),
    CatalogStep(code=StepCode.PRE_EVENT_NOTICE, name=PLANNING_STEP_NAMES[StepCode.PRE_EVENT_NOTICE], phase=StepPhase.EXECUTION,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.NOTICE,)),
    CatalogStep(code=StepCode.EVENT_DAY, name=PLANNING_STEP_NAMES[StepCode.EVENT_DAY], phase=StepPhase.EXECUTION, actor=StepActor.MANUAL),
    CatalogStep(code=StepCode.SETTLE_EXPENSES, name=PLANNING_STEP_NAMES[StepCode.SETTLE_EXPENSES], phase=StepPhase.EXECUTION,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.EXPENSE,)),
    CatalogStep(code=StepCode.REFUND_FEES, name=PLANNING_STEP_NAMES[StepCode.REFUND_FEES], phase=StepPhase.EXECUTION,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.TRANSFER,)),
    CatalogStep(code=StepCode.RECORD_FEEDBACK, name=PLANNING_STEP_NAMES[StepCode.RECORD_FEEDBACK], phase=StepPhase.EXECUTION, actor=StepActor.AI),
)
BY_CODE = {item.code: item for item in CATALOG}
PHASE_ORDER = (StepPhase.PREPARATION, StepPhase.RECRUITING, StepPhase.EXECUTION)
