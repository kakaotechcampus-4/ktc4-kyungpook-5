"""고정 단계의 표시 정보와 허용 행동. 모델은 코드를 고르고 코드는 속성을 보완한다."""

from app.core.enums import ActionType, StepActor, StepCode, StepPhase

from ....contracts import ContractModel


class CatalogStep(ContractModel):
    code: StepCode
    name: str
    phase: StepPhase
    actor: StepActor
    actions: tuple[ActionType, ...] = ()


# CONFIRMATION은 운영 중 필요한 질문이 생겼을 때 만든다. 계획에 미리 생성하지 않는다.
CATALOG = (
    CatalogStep(code=StepCode.ASSIGN_ROLES, name="담당 인원 배치", phase=StepPhase.PREPARATION, actor=StepActor.MANUAL),
    CatalogStep(code=StepCode.RESEARCH_VENUE, name="장소·교통 알아보기", phase=StepPhase.PREPARATION, actor=StepActor.MANUAL),
    CatalogStep(code=StepCode.DEMAND_SURVEY, name="사전 수요 조사", phase=StepPhase.PREPARATION,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.NOTICE,)),
    CatalogStep(code=StepCode.RECRUIT_NOTICE, name="모집 공지", phase=StepPhase.RECRUITING,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.NOTICE,)),
    CatalogStep(code=StepCode.CHECK_RESPONSES, name="응답 확인", phase=StepPhase.RECRUITING,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.NOTICE,)),
    CatalogStep(code=StepCode.CONFIRM_DETAILS, name="인원·일정 확정", phase=StepPhase.RECRUITING, actor=StepActor.AI),
    CatalogStep(code=StepCode.BOOK_VENUE, name="예약", phase=StepPhase.RECRUITING,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.CONTRACT, ActionType.TRANSFER)),
    CatalogStep(code=StepCode.COLLECT_FEES, name="참가비 수금", phase=StepPhase.RECRUITING,
                actor=StepActor.AI, actions=(ActionType.NOTICE, ActionType.EXTERNAL_SEND)),
    CatalogStep(code=StepCode.PRE_EVENT_NOTICE, name="사전 안내", phase=StepPhase.EXECUTION,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.NOTICE,)),
    CatalogStep(code=StepCode.EVENT_DAY, name="행사 당일", phase=StepPhase.EXECUTION, actor=StepActor.MANUAL),
    CatalogStep(code=StepCode.SETTLE_EXPENSES, name="지출 정산", phase=StepPhase.EXECUTION,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.EXPENSE,)),
    CatalogStep(code=StepCode.REFUND_FEES, name="참가비 환급", phase=StepPhase.EXECUTION,
                actor=StepActor.APPROVAL_REQUIRED, actions=(ActionType.TRANSFER,)),
    CatalogStep(code=StepCode.RECORD_FEEDBACK, name="피드백 기록", phase=StepPhase.EXECUTION, actor=StepActor.AI),
)
BY_CODE = {item.code: item for item in CATALOG}
PHASE_ORDER = (StepPhase.PREPARATION, StepPhase.RECRUITING, StepPhase.EXECUTION)
