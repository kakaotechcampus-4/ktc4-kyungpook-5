// 시연용 예시 데이터. 주소에 ?demo를 붙였을 때만 화면에 쓴다(실제 화면은 빈 목록에서 시작).
// 모양은 API 응답과 같게 두고, 날짜는 오늘 기준으로 잡아 D-day가 늘 시안처럼 보이게 한다.
import type {
  EventAction,
  EventDetail,
  EventStep,
  EventSummary,
  StepState,
} from '@/features/events/types'

// 오늘에서 n일 뒤의 "YYYY-MM-DD"
function day(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return d.toLocaleDateString('en-CA')
}

// 한국 시각 그날 23:59 마감
const deadline = (n: number) => `${day(n)}T14:59:00Z`

// M1 스테퍼(DEMO_STEPS)와 단계 수를 맞춘다.
// 앞에서 done개는 완료, 그다음 하나는 진행 중, 나머지는 예정
function progress(total: number, done: number): EventSummary['stepProgress'] {
  return Array.from({ length: total }, (_, i) => ({
    stepOrder: (i + 1) * 10,
    state: (i < done ? 'DONE' : i === done ? 'CURRENT' : 'TODO') as StepState,
  }))
}

export const DEMO_EVENTS: EventSummary[] = [
  {
    id: 'evt_9f2c8a',
    title: '2026 봄 MT',
    status: 'ON_GOING',
    startDate: day(11),
    endDate: day(12),
    dday: 11,
    currentStepName: '입금 확인',
    stepProgress: progress(8, 4),
    pendingApprovalCount: 3,
    location: '가평 ○○펜션',
    headcount: 32,
  },
  {
    id: 'evt_c41d07',
    title: '2026 가을 해커톤',
    status: 'ON_GOING',
    startDate: day(24),
    endDate: day(25),
    dday: 24,
    currentStepName: '장소 대관',
    stepProgress: progress(7, 2),
    pendingApprovalCount: 1,
    location: '공대 7호관 세미나실',
    headcount: 40,
  },
  {
    id: 'evt_5be210',
    title: '여름 워크샵',
    status: 'PLANNING',
    startDate: null,
    endDate: null,
    dday: null,
    currentStepName: null,
    stepProgress: progress(7, 0),
    pendingApprovalCount: 0,
    location: null,
    headcount: null,
  },
  {
    id: 'evt_0a7f33',
    title: '2026 새내기 배움터',
    status: 'COMPLETE',
    startDate: '2026-02-21',
    endDate: '2026-02-22',
    dday: null,
    currentStepName: null,
    stepProgress: progress(13, 13),
    pendingApprovalCount: 0,
    location: '교내',
    headcount: 48,
  },
  {
    id: 'evt_7e9c12',
    title: '2025 겨울 해커톤',
    status: 'COMPLETE',
    startDate: '2026-01-10',
    endDate: '2026-01-11',
    dday: null,
    currentStepName: null,
    stepProgress: progress(11, 11),
    pendingApprovalCount: 0,
    location: '교내',
    headcount: 26,
  },
]

function steps(names: string[], offsets: number[], done: number): EventStep[] {
  return names.map((name, i) => ({
    id: `stp_${i}`,
    stepOrder: (i + 1) * 10,
    name,
    state: i < done ? 'DONE' : i === done ? 'CURRENT' : 'TODO',
    deadline: deadline(offsets[i]),
  }))
}

export const DEMO_STEPS: Record<string, EventStep[]> = {
  evt_9f2c8a: steps(
    [
      '담당 배치',
      '수요 조사',
      '일정 확정',
      '모집 공지',
      '입금 확인',
      '사전 안내',
      '행사 당일',
      '정산·기록',
    ],
    [-8, -5, -3, -1, 2, 9, 11, 15],
    4,
  ),
  evt_c41d07: steps(
    ['담당 배치', '주제 선정', '장소 대관', '참가 모집', '멘토 섭외', '해커톤 당일', '시상·정산'],
    [-6, -2, 3, 12, 22, 24, 28],
    2,
  ),
}

// 담당은 명세에 없어 시연용으로만 적는다(types.ts TODO 참고)
const DEMO_MANAGERS: Record<string, string> = {
  evt_9f2c8a: '박수겸 · 총무',
  evt_c41d07: '김지훈 · 회장',
}

// L2 상단 카드. 목록 한 줄에 현재 단계·담당을 붙인다.
export const DEMO_EVENT_DETAILS: Record<string, EventDetail> = Object.fromEntries(
  DEMO_EVENTS.map((e) => {
    const current = DEMO_STEPS[e.id]?.find((s) => s.state === 'CURRENT')
    const detail: EventDetail = {
      id: e.id,
      title: e.title,
      status: e.status,
      startDate: e.startDate,
      endDate: e.endDate,
      dday: e.dday,
      location: e.location,
      headcount: e.headcount,
      currentStep: current
        ? { id: current.id, stepOrder: current.stepOrder, name: current.name }
        : null,
      manager: DEMO_MANAGERS[e.id] ?? null,
    }
    return [e.id, detail]
  }),
)

export const DEMO_ACTIONS: Record<string, EventAction[]> = {
  evt_9f2c8a: [
    {
      id: 'act_21',
      type: 'EXTERNAL_SEND',
      title: '미납자 4명에게 2차 납부 안내 문자 보내기',
      subtitle: '대상 4명 · 비용 0원',
      dueDate: day(2),
    },
    {
      id: 'act_22',
      type: 'TRANSFER',
      title: '펜션 계약금 100,000원 이체하고 예약 확정',
      subtitle: '마감 다음 날부터 환불 불가 · 잔고 2,412,000원',
      dueDate: day(4),
    },
    {
      id: 'act_23',
      type: 'EXPENSE',
      title: '장보기·버스 잔금 등 지출 4건 묶음 승인',
      subtitle: '합계 182,000원 · 영수증 4건 확인됨',
      dueDate: day(13),
    },
  ],
  evt_c41d07: [
    {
      id: 'act_31',
      type: 'CONTRACT',
      title: '공대 7호관 세미나실 1박 2일 대관 신청서 제출',
      subtitle: '학과 사무실 승인 필요 · 야간 사용 신청 포함',
      dueDate: day(3),
    },
  ],
}
