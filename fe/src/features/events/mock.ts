// 시연용 예시 데이터. 주소에 ?demo를 붙였을 때만 화면에 쓴다(실제 화면은 빈 목록에서 시작).
// 모양은 API 응답과 같게 두고, 날짜는 오늘 기준으로 잡아 D-day가 늘 시안처럼 보이게 한다.
import type {
  ActionPage,
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

// 오늘에서 n일 뒤 한국 시각 "hh:mm"
const at = (n: number, time: string) => new Date(`${day(n)}T${time}:00+09:00`).toISOString()

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

// current는 진행 중인 단계에만 덧붙인다(L2 현재 단계 카드)
function steps(
  names: string[],
  offsets: number[],
  done: number,
  current?: Partial<EventStep>,
): EventStep[] {
  return names.map((name, i) => ({
    id: `stp_${i}`,
    stepOrder: (i + 1) * 10,
    name,
    state: i < done ? 'DONE' : i === done ? 'CURRENT' : 'TODO',
    deadline: deadline(offsets[i]),
    ...(i === done ? current : undefined),
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
    {
      actor: 'AI',
      startsAt: at(-1, '00:00'),
      doneActions: [
        { id: 'act_11', title: '입금 12건을 참가자 명단과 대조했어요.', status: 'DONE' },
        { id: 'act_12', title: '입금자명이 다른 2건을 확인 요청으로 올렸어요.', status: 'DONE' },
        { id: 'act_13', title: '미납자 목록을 5명 → 4명으로 갱신했어요.', status: 'DONE' },
      ],
      remainingActions: [
        {
          id: 'act_21',
          title: '미납자 4명에게 2차 안내 발송',
          status: 'PENDING',
          approveNeeded: true,
        },
        {
          id: 'act_25',
          title: '미응답 회원 9명에게 신청 마감 안내',
          status: 'APPROVED',
          approveNeeded: true,
        },
      ],
    },
  ),
  evt_c41d07: steps(
    ['담당 배치', '주제 선정', '장소 대관', '참가 모집', '멘토 섭외', '해커톤 당일', '시상·정산'],
    [-6, -2, 3, 12, 22, 24, 28],
    2,
    // 토리가 한 일 없이 승인할 일만 남은 단계. L2에서 토리 박스가 숨는 경우를 보여 준다.
    {
      actor: 'APPROVAL_REQUIRED',
      startsAt: at(-2, '00:00'),
      doneActions: [],
      remainingActions: [
        {
          id: 'act_31',
          title: '공대 7호관 세미나실 1박 2일 대관 신청서 제출',
          status: 'PENDING',
          approveNeeded: true,
        },
      ],
    },
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
      status: 'PENDING',
    },
    {
      id: 'act_22',
      type: 'TRANSFER',
      title: '펜션 계약금 100,000원 이체하고 예약 확정',
      subtitle: '마감 다음 날부터 환불 불가 · 잔고 2,412,000원',
      dueDate: day(4),
      status: 'PENDING',
    },
    {
      id: 'act_23',
      type: 'EXPENSE',
      title: '장보기·버스 잔금 등 지출 4건 묶음 승인',
      subtitle: '합계 182,000원 · 영수증 4건 확인됨',
      dueDate: day(13),
      status: 'PENDING',
    },
  ],
  evt_c41d07: [
    {
      id: 'act_31',
      type: 'CONTRACT',
      title: '공대 7호관 세미나실 1박 2일 대관 신청서 제출',
      subtitle: '학과 사무실 승인 필요 · 야간 사용 신청 포함',
      dueDate: day(3),
      status: 'PENDING',
    },
  ],
}

// L2 확인 요청. 가을 해커톤은 비워 두어 빈 상태를 볼 수 있게 한다.
export const DEMO_CONFIRMATIONS: Record<string, EventAction[]> = {
  evt_9f2c8a: [
    {
      id: 'act_31',
      type: 'CONFIRMATION',
      title: '입금자명이 명단과 다릅니다',
      subtitle: '"박지영 母" 45,000원 — 박지영 님 회비로 처리할까요?',
      dueDate: null,
      status: 'PENDING',
      options: [
        { key: 'MATCH', label: '맞아요' },
        { key: 'NOT_MATCH', label: '아니에요' },
      ],
      allowManual: true,
    },
    {
      id: 'act_32',
      type: 'CONFIRMATION',
      title: '어느 행사인지 모르겠습니다',
      subtitle: '학생회 지원금 500,000원 — 봄 MT에 넣을까요, 공동 회계로 둘까요?',
      dueDate: null,
      status: 'PENDING',
      options: [
        { key: 'ASSIGN_EVENT', label: '봄 MT에 넣기' },
        { key: 'ASSIGN_CLUB', label: '공동 회계로' },
      ],
      allowManual: true,
    },
  ],
}

const PARK = { id: 'mbr_01', name: '박수겸', role: 'MANAGER' } as const
const KIM = { id: 'mbr_02', name: '김지훈', role: 'OWNER' } as const

// L2 처리된 승인. 최근 몇 건과 전체 개수.
export const DEMO_RESOLVED: Record<string, ActionPage> = {
  evt_9f2c8a: {
    totalCount: 12,
    items: [
      {
        id: 'act_41',
        type: 'CONTRACT',
        title: '장소 후보를 펜션 A로 확정',
        subtitle: null,
        dueDate: null,
        status: 'DONE',
        resolvedAt: at(0, '11:40'),
        resolvedBy: PARK,
      },
      {
        id: 'act_42',
        type: 'EXTERNAL_SEND',
        title: '모집 공고를 단톡방에 발송',
        subtitle: null,
        dueDate: null,
        status: 'DONE',
        resolvedAt: at(-1, '15:30'),
        resolvedBy: KIM,
      },
      {
        id: 'act_09',
        type: 'TRANSFER',
        title: '버스 대절 업체 B와 계약',
        subtitle: null,
        dueDate: null,
        status: 'DENIED',
        resolvedAt: at(-2, '17:02'),
        resolvedBy: PARK,
      },
    ],
  },
  evt_c41d07: {
    totalCount: 1,
    items: [
      {
        id: 'act_51',
        type: 'NOTICE',
        title: '해커톤 주제 후보 3개를 단톡방에 공지',
        subtitle: null,
        dueDate: null,
        status: 'APPROVED',
        resolvedAt: at(-1, '20:10'),
        resolvedBy: KIM,
      },
    ],
  },
}

// Step 모달의 할 일 · 처리된 일. 행사 → 단계 id → Action. 같은 건은 M1 · L2와 id를 맞춘다.
export const DEMO_STEP_ACTIONS: Record<string, Record<string, EventAction[]>> = {
  evt_9f2c8a: {
    // 4. 모집 공지(완료): L2 처리된 승인의 "모집 공고를 단톡방에 발송"과 같은 건
    stp_3: [
      {
        id: 'act_42',
        type: 'EXTERNAL_SEND',
        title: '모집 공고를 단톡방에 발송',
        subtitle: '대상 전체 회원 32명',
        dueDate: day(-1),
        status: 'DONE',
        resolvedAt: at(-1, '15:30'),
        resolvedBy: KIM,
      },
    ],
    // 5. 입금 확인(진행 중): 승인 대기는 M1의 act_21과 같은 건
    stp_4: [
      {
        id: 'act_21',
        type: 'EXTERNAL_SEND',
        title: '미납자 4명에게 2차 납부 안내 문자 보내기',
        subtitle: '대상 4명 · 비용 0원',
        dueDate: day(2),
        status: 'PENDING',
        content: '○○○님, 봄 MT 참가비 45,000원이 아직 확인되지 않았습니다.',
      },
      {
        id: 'act_25',
        type: 'NOTICE',
        title: '미응답 회원 9명에게 신청 마감 안내',
        subtitle: '대상 9명 · 비용 0원',
        dueDate: day(2),
        status: 'APPROVED',
        resolvedAt: at(0, '09:20'),
        resolvedBy: PARK,
        content:
          '안녕하세요. 봄 MT 참가 신청이 곧 마감됩니다. 아직 응답하지 않은 분은 신청 여부를 알려주세요.',
      },
      {
        id: 'act_26',
        type: 'EXTERNAL_SEND',
        title: '미납자 5명에게 1차 납부 안내 문자 보내기',
        subtitle: '대상 5명 · 비용 0원',
        dueDate: day(-1),
        status: 'DONE',
        resolvedAt: at(-1, '10:15'),
        resolvedBy: PARK,
      },
    ],
  },
  evt_c41d07: {
    // 3. 장소 대관(진행 중): M1의 act_31과 같은 건
    stp_2: [
      {
        id: 'act_31',
        type: 'CONTRACT',
        title: '공대 7호관 세미나실 1박 2일 대관 신청서 제출',
        subtitle: '학과 사무실 승인 필요 · 야간 사용 신청 포함',
        dueDate: day(3),
        status: 'PENDING',
        content: '해커톤 당일부터 다음 날까지 세미나실 1박 2일 대관. 야간 사용 신청 포함.',
      },
    ],
  },
}
