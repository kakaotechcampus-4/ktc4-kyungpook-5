"""계획 단계의 고정 이름. 공개 계약과 생성 코드가 같은 목록을 읽는다."""

from types import MappingProxyType

from app.core.enums import StepCode


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
