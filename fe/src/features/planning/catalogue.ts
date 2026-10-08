// 단계 카탈로그. 13개로 고정이고 묶음도 단계마다 정해져 있다(#69).
// 그래서 수정 화면에서 바꿀 수 있는 건 넣고 빼는 것과 묶음 안의 순서뿐이다.
import type { StepActor, StepPhase } from '@/features/planning/types'

export interface CatalogueStep {
  code: string
  phase: StepPhase
  name: string
  actor: StepActor
  // 이 단계에 붙는 Action. 없는 단계도 있다(행사 당일).
  actions: string
}

export const STEP_CATALOGUE: CatalogueStep[] = [
  {
    code: 'ASSIGN_STAFF',
    phase: '사전 준비',
    name: '담당 인원 배치',
    actor: '직접 수행',
    actions: '확인 요청',
  },
  {
    code: 'SCOUT_VENUE',
    phase: '사전 준비',
    name: '장소·교통 알아보기',
    actor: '직접 수행',
    actions: '확인 요청',
  },
  {
    code: 'SURVEY_DEMAND',
    phase: '사전 준비',
    name: '사전 수요 조사',
    actor: '승인 필요',
    actions: '공지',
  },
  {
    code: 'RECRUIT_NOTICE',
    phase: '모집 · 확정',
    name: '모집 공지',
    actor: '승인 필요',
    actions: '공지',
  },
  {
    code: 'CHECK_RESPONSES',
    phase: '모집 · 확정',
    name: '응답 확인',
    actor: '승인 필요',
    actions: '공지',
  },
  {
    code: 'CONFIRM_HEADCOUNT',
    phase: '모집 · 확정',
    name: '인원·일정 확정',
    actor: 'AI 실행',
    actions: '확인 요청',
  },
  {
    code: 'BOOK_VENUE',
    phase: '모집 · 확정',
    name: '예약',
    actor: '승인 필요',
    actions: '계약 · 이체',
  },
  {
    code: 'COLLECT_FEES',
    phase: '모집 · 확정',
    name: '참가비 수금',
    actor: 'AI 실행',
    actions: '공지 · 개별 연락',
  },
  {
    code: 'PRE_NOTICE',
    phase: '행사 진행 · 마무리',
    name: '사전 안내',
    actor: '승인 필요',
    actions: '공지',
  },
  {
    code: 'EVENT_DAY',
    phase: '행사 진행 · 마무리',
    name: '행사 당일',
    actor: '직접 수행',
    actions: 'Action 없음',
  },
  {
    code: 'SETTLE_EXPENSES',
    phase: '행사 진행 · 마무리',
    name: '지출 정산',
    actor: '승인 필요',
    actions: '지출',
  },
  {
    code: 'REFUND_FEES',
    phase: '행사 진행 · 마무리',
    name: '참가비 환급',
    actor: '승인 필요',
    actions: '이체',
  },
  {
    code: 'RECORD_FEEDBACK',
    phase: '행사 진행 · 마무리',
    name: '피드백 기록',
    actor: 'AI 실행',
    actions: '확인 요청',
  },
]

// 묶음은 셋으로 고정이고 순서도 바뀌지 않는다. 비어 있어도 늘 그린다.
export const PHASES: StepPhase[] = ['사전 준비', '모집 · 확정', '행사 진행 · 마무리']

export const PHASE_HINT: Record<StepPhase, string> = {
  '사전 준비': '행사를 정하기 전에 해 둘 일',
  '모집 · 확정': '사람을 모으고 수를 확정하는 일',
  '행사 진행 · 마무리': '행사 당일과 그 뒤에 할 일',
}

// 완성 예시에 쓰는 포함 단계와 일정. 빼둔 셋은 사전 수요 조사·참가비 환급·피드백 기록이다.
export const DEMO_INCLUDED: Record<string, string> = {
  ASSIGN_STAFF: '3/2 – 3/3',
  SCOUT_VENUE: '3/3 – 3/6',
  RECRUIT_NOTICE: '3/10 – 3/12',
  CHECK_RESPONSES: '3/12 – 3/13',
  CONFIRM_HEADCOUNT: '3/13',
  BOOK_VENUE: '3/13 – 3/14',
  COLLECT_FEES: '3/14 – 3/18',
  PRE_NOTICE: '3/19',
  EVENT_DAY: '3/21 – 3/22',
  SETTLE_EXPENSES: '3/23',
}
