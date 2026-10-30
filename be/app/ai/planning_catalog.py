"""계획 단계의 고정 속성. 공개 계약과 생성 코드, BE 서비스가 같은 목록을 읽는다."""

from types import MappingProxyType

from app.core.enums import ActionType, StepActor, StepCode, StepPhase


# Graph나 계약 타입을 import하지 않는 공통 데이터다. 취소 단계는 계획 카탈로그 밖이다.
PLANNING_STEP_NAMES = MappingProxyType({
    StepCode.ASSIGN_ROLES: "담당 인원 배치",
    StepCode.RESEARCH_VENUE: "장소·교통 알아보기",
    StepCode.DEMAND_SURVEY: "사전 수요 조사",
    StepCode.RECRUIT_NOTICE: "모집 공지",
    StepCode.CHECK_RESPONSES: "응답 확인",
    StepCode.CONFIRM_DETAILS: "인원·일정 확정",
    StepCode.BOOK_VENUE: "예약",
    StepCode.COLLECT_FEES: "참가비 수금",
    StepCode.PRE_EVENT_NOTICE: "사전 안내",
    StepCode.EVENT_DAY: "행사 당일",
    StepCode.SETTLE_EXPENSES: "지출 정산",
    StepCode.REFUND_FEES: "참가비 환급",
    StepCode.RECORD_FEEDBACK: "피드백 기록",
})

# 묶음이 놓이는 차례. 단계 구성을 바꿔도 사전 준비가 마무리 뒤로 갈 수는 없다.
PLANNING_PHASE_ORDER = (StepPhase.PREPARATION, StepPhase.RECRUITING, StepPhase.EXECUTION)

# 묶음은 카탈로그가 정한다(#69). 모델도 운영진도 단계를 다른 묶음으로 옮기지 못한다.
PLANNING_STEP_PHASES = MappingProxyType({
    StepCode.ASSIGN_ROLES: StepPhase.PREPARATION,
    StepCode.RESEARCH_VENUE: StepPhase.PREPARATION,
    StepCode.DEMAND_SURVEY: StepPhase.PREPARATION,
    StepCode.RECRUIT_NOTICE: StepPhase.RECRUITING,
    StepCode.CHECK_RESPONSES: StepPhase.RECRUITING,
    StepCode.CONFIRM_DETAILS: StepPhase.RECRUITING,
    StepCode.BOOK_VENUE: StepPhase.RECRUITING,
    StepCode.COLLECT_FEES: StepPhase.RECRUITING,
    StepCode.PRE_EVENT_NOTICE: StepPhase.EXECUTION,
    StepCode.EVENT_DAY: StepPhase.EXECUTION,
    StepCode.SETTLE_EXPENSES: StepPhase.EXECUTION,
    StepCode.REFUND_FEES: StepPhase.EXECUTION,
    StepCode.RECORD_FEEDBACK: StepPhase.EXECUTION,
})

PLANNING_STEP_ACTORS = MappingProxyType({
    StepCode.ASSIGN_ROLES: StepActor.MANUAL,
    StepCode.RESEARCH_VENUE: StepActor.MANUAL,
    StepCode.DEMAND_SURVEY: StepActor.APPROVAL_REQUIRED,
    StepCode.RECRUIT_NOTICE: StepActor.APPROVAL_REQUIRED,
    StepCode.CHECK_RESPONSES: StepActor.APPROVAL_REQUIRED,
    StepCode.CONFIRM_DETAILS: StepActor.AI,
    StepCode.BOOK_VENUE: StepActor.APPROVAL_REQUIRED,
    StepCode.COLLECT_FEES: StepActor.AI,
    StepCode.PRE_EVENT_NOTICE: StepActor.APPROVAL_REQUIRED,
    StepCode.EVENT_DAY: StepActor.MANUAL,
    StepCode.SETTLE_EXPENSES: StepActor.APPROVAL_REQUIRED,
    StepCode.REFUND_FEES: StepActor.APPROVAL_REQUIRED,
    StepCode.RECORD_FEEDBACK: StepActor.AI,
})

# 계획에 미리 만들어 두는 Action. CONFIRMATION은 운영 중 필요할 때 생긴다.
PLANNING_STEP_ACTIONS = MappingProxyType({
    StepCode.DEMAND_SURVEY: (ActionType.NOTICE,),
    StepCode.RECRUIT_NOTICE: (ActionType.NOTICE,),
    StepCode.CHECK_RESPONSES: (ActionType.NOTICE,),
    StepCode.BOOK_VENUE: (ActionType.CONTRACT, ActionType.TRANSFER),
    StepCode.COLLECT_FEES: (ActionType.NOTICE, ActionType.EXTERNAL_SEND),
    StepCode.PRE_EVENT_NOTICE: (ActionType.NOTICE,),
    StepCode.SETTLE_EXPENSES: (ActionType.EXPENSE,),
    StepCode.REFUND_FEES: (ActionType.TRANSFER,),
})
