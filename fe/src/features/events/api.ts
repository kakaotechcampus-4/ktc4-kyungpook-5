// 서버 호출 함수 + 응답 타입
//
// TODO: BE에 아직 `GET /events` / `GET /events/drafts`가 없다(현재 mock API는
// `GET /events/{eventId}/actions` 하나뿐). 엔드포인트가 생기면 아래 목업을
// apiGet 호출로 갈아끼우면 되도록 FE API 명세 §2 응답 모양 그대로 만들어 둔다.
import type { EventListView } from '@/features/events/types'

export function getEventList(): EventListView {
  return {
    ongoing: [
      {
        id: 'evt_9f2c8a',
        title: '2026 봄 MT',
        status: 'ON_GOING',
        startDate: '2026-03-21',
        endDate: '2026-03-22',
        dday: 11,
        currentStepName: '수납',
        stepProgress: [
          { stepOrder: 10, state: 'DONE' },
          { stepOrder: 20, state: 'DONE' },
          { stepOrder: 30, state: 'DONE' },
          { stepOrder: 40, state: 'DONE' },
          { stepOrder: 50, state: 'CURRENT' },
          { stepOrder: 60, state: 'CURRENT' },
          { stepOrder: 70, state: 'TODO' },
          { stepOrder: 80, state: 'TODO' },
          { stepOrder: 90, state: 'TODO' },
        ],
        pendingApprovalCount: 3,
        payment: { paidCount: 28, totalCount: 32, collected: 1260000, target: 1440000 },
        budget: { spent: 588000, planned: 1940000 },
      },
      {
        id: 'evt_seminar',
        title: '3월 정기 세미나',
        status: 'ON_GOING',
        startDate: '2026-03-27',
        endDate: null,
        dday: 17,
        currentStepName: '연사 섭외',
        stepProgress: [
          { stepOrder: 10, state: 'DONE' },
          { stepOrder: 20, state: 'DONE' },
          { stepOrder: 30, state: 'CURRENT' },
          { stepOrder: 40, state: 'TODO' },
          { stepOrder: 50, state: 'TODO' },
          { stepOrder: 60, state: 'TODO' },
          { stepOrder: 70, state: 'TODO' },
        ],
        pendingApprovalCount: 1,
        payment: null,
        budget: { spent: 0, planned: 300000 },
      },
      {
        id: 'evt_welcome',
        title: '신입생 환영회',
        status: 'ON_GOING',
        startDate: '2026-04-03',
        endDate: null,
        dday: 24,
        currentStepName: '수요 조사',
        stepProgress: [
          { stepOrder: 10, state: 'DONE' },
          { stepOrder: 20, state: 'CURRENT' },
          { stepOrder: 30, state: 'TODO' },
          { stepOrder: 40, state: 'TODO' },
          { stepOrder: 50, state: 'TODO' },
          { stepOrder: 60, state: 'TODO' },
          { stepOrder: 70, state: 'TODO' },
          { stepOrder: 80, state: 'TODO' },
        ],
        pendingApprovalCount: 1,
        payment: null,
        budget: { spent: 25000, planned: 800000 },
      },
    ],
    drafts: [{ id: 'evt_summer', title: '여름 워크샵', stageLabel: '2단계에서 멈춤' }],
    completedCount: 7,
  }
}

// ── L2 행사 상세 ──
//
// 확인 요청 / 처리된 승인만 BE mock API(GET /events/{eventId}/actions)가 나와 있어
// 실제로 연동한다. 헤더·단계는 엔드포인트 구현 전이고, 예산·수납은 명세에서도 아직
// ⏸ 보류라 목업이다. 엔드포인트가 생기면 아래 목업만 apiGet 호출로 갈아끼운다.
import { apiGetPage } from '@/shared/api/client'
import type { EventAction, EventDetail, EventStep, PaymentIssue } from '@/features/events/types'

export function getEventDetail(): EventDetail {
  return {
    id: 'evt_9f2c8a',
    title: '2026 봄 MT',
    status: 'ON_GOING',
    startDate: '2026-03-21',
    endDate: '2026-03-22',
    dday: 11,
    location: '가평 ○○펜션',
    headcount: 32,
    // 헤더 배지는 단계 이름이 아니라 지금 어느 국면인지를 보여준다(L1 목록의 표기와 같다).
    currentStep: { id: 'stp_09', stepOrder: 90, name: '수납' },
    payment: { paidCount: 28, totalCount: 32, collected: 1260000, target: 1440000 },
    budget: { spent: 588000, planned: 1940000 },
  }
}

// 이름은 진행 상황 막대에 그대로 들어가므로 짧은 표기를 쓴다.
const STEP_SEEDS: Array<[name: string, actor: EventStep['actor'], state: EventStep['state']]> = [
  ['과거 기록', 'AI', 'DONE'],
  ['담당 배치', 'MANUAL', 'DONE'],
  ['수요 조사', 'APPROVAL_REQUIRED', 'DONE'],
  ['세부 조정', 'AI', 'DONE'],
  ['가능 확인', 'MANUAL', 'DONE'],
  ['일정 확정', 'MANUAL', 'DONE'],
  ['모집 공지', 'APPROVAL_REQUIRED', 'DONE'],
  ['수요 마감', 'AI', 'DONE'],
  ['입금 확인', 'AI', 'CURRENT'],
  ['리허설', 'MANUAL', 'TODO'],
  ['행사 시작', 'MANUAL', 'TODO'],
  ['영수 처리', 'AI', 'TODO'],
  ['피드백', 'AI', 'TODO'],
]

export function getEventSteps(): EventStep[] {
  return STEP_SEEDS.map(([name, actor, state], index) => ({
    id: `stp_${String(index + 1).padStart(2, '0')}`,
    stepOrder: (index + 1) * 10,
    name,
    actor,
    state,
    startedTime: state === 'CURRENT' ? '2026-03-10T00:00:00Z' : null,
    deadline: state === 'CURRENT' ? '2026-03-12T14:59:00Z' : null,
    doneActions:
      state === 'CURRENT'
        ? [
            {
              id: 'act_11',
              title: '입금 12건을 참가자 명단과 대조했습니다',
              status: 'DONE',
              approveNeeded: false,
            },
            {
              id: 'act_12',
              title: '입금자명이 다른 2건을 확인 요청으로 올렸습니다',
              status: 'DONE',
              approveNeeded: false,
            },
            {
              id: 'act_13',
              title: '미납자 목록을 5명 → 4명으로 갱신했습니다',
              status: 'DONE',
              approveNeeded: false,
            },
          ]
        : [],
    remainingActions:
      state === 'CURRENT'
        ? [
            {
              id: 'act_21',
              title: '미납자 4명에게 2차 안내 발송',
              status: 'PENDING',
              approveNeeded: true,
            },
            {
              id: 'act_22',
              title: '마감 3/12 23:59 이후 미납자 자동 정리',
              status: 'PENDING',
              approveNeeded: false,
            },
          ]
        : [],
  }))
}

// ⏸ GET /events/{id}/budget — 합계는 getEventDetail().budget 에 있고 이건 덧붙는 설명이다.
export function getBudgetNote(): string {
  return '진행은 9/13단계(69%)인데 집행은 30%입니다. 숙소 잔금과 식비가 남아 있습니다.'
}

// ⏸ GET /events/{id}/payments
export function getPaymentIssues(): PaymentIssue[] {
  return [
    {
      id: 'pay_1',
      kind: 'UNPAID',
      name: '김○○',
      note: '3/2 신청',
      statusLabel: '안내 발송 대기',
    },
    {
      id: 'pay_2',
      kind: 'UNPAID',
      name: '이○○',
      note: '3/2 신청 · 작년에도 마감 후 납부',
      statusLabel: '안내 발송 대기',
    },
    {
      id: 'pay_3',
      kind: 'UNPAID',
      name: '박○○',
      note: '3/4 신청',
      statusLabel: '안내 발송 대기',
    },
    {
      id: 'pay_4',
      kind: 'REFUND',
      name: '정○○',
      note: '3/9 참석 취소 요청',
      statusLabel: '45,000원 환불 · 승인 필요',
    },
  ]
}

// "처리된 승인" 목록은 최근 5건만 보여주고 나머지는 "전체 보기"로 넘긴다.
const RESOLVED_PAGE_SIZE = 5

export interface ActionListResult {
  confirmations: EventAction[]
  resolvedActions: EventAction[]
  resolvedTotalCount: number
}

export async function getEventActionsFromApi(eventId: string): Promise<ActionListResult> {
  const [confirmations, resolved] = await Promise.all([
    apiGetPage<EventAction>(`/events/${eventId}/actions?status=PENDING&type=CONFIRMATION`),
    apiGetPage<EventAction>(
      `/events/${eventId}/actions?status=APPROVED,DONE,DENIED&page=1&size=${RESOLVED_PAGE_SIZE}`,
    ),
  ])

  return {
    confirmations: confirmations.data,
    resolvedActions: resolved.data,
    resolvedTotalCount: resolved.meta?.totalCount ?? resolved.data.length,
  }
}

// API가 아직 안 떠 있을 때 화면을 확인하기 위한 목업. 디자인 시안과 같은 데이터다.
export function getEventActions(): ActionListResult {
  return {
    confirmations: [
      {
        id: 'act_31',
        type: 'CONFIRMATION',
        title: '입금자명이 명단과 다릅니다',
        subtitle: '“박지영 母” 45,000원 — 박지영 님 회비로 처리할까요?',
        status: 'PENDING',
        dueDate: '2026-03-10',
        resolvedAt: null,
        resolvedBy: null,
        denyReason: null,
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
        status: 'PENDING',
        dueDate: '2026-03-08',
        resolvedAt: null,
        resolvedBy: null,
        denyReason: null,
        options: [
          { key: 'ASSIGN_EVENT', label: '봄 MT에 넣기' },
          { key: 'ASSIGN_CLUB', label: '공동 회계로' },
        ],
        allowManual: true,
      },
    ],
    resolvedActions: [
      {
        id: 'act_41',
        type: 'CONTRACT',
        title: '장소 후보를 펜션 A로 확정',
        subtitle: null,
        status: 'DONE',
        dueDate: null,
        resolvedAt: '2026-03-10T02:40:00Z',
        resolvedBy: { id: 'mbr_01', name: '박수겸', role: 'MANAGER' },
        denyReason: null,
        options: null,
        allowManual: null,
      },
      {
        id: 'act_42',
        type: 'EXTERNAL_SEND',
        title: '모집 공고를 단톡방에 발송',
        subtitle: null,
        status: 'DONE',
        dueDate: null,
        resolvedAt: '2026-03-09T06:30:00Z',
        resolvedBy: { id: 'mbr_02', name: '김지훈', role: 'OWNER' },
        denyReason: null,
        options: null,
        allowManual: null,
      },
      {
        id: 'act_09',
        type: 'TRANSFER',
        title: '버스 대절 업체 B와 계약',
        subtitle: null,
        status: 'DENIED',
        dueDate: null,
        resolvedAt: '2026-03-08T08:02:00Z',
        resolvedBy: { id: 'mbr_01', name: '박수겸', role: 'MANAGER' },
        denyReason: '견적이 작년보다 40% 높아 다른 업체를 더 받아보기로 했습니다.',
        options: null,
        allowManual: null,
      },
      {
        id: 'act_43',
        type: 'EXTERNAL_SEND',
        title: '1차 납부 안내 문자 발송',
        subtitle: null,
        status: 'DONE',
        dueDate: null,
        resolvedAt: '2026-03-05T01:15:00Z',
        resolvedBy: { id: 'mbr_03', name: '이서연', role: 'MANAGER' },
        denyReason: null,
        options: null,
        allowManual: null,
      },
      {
        id: 'act_44',
        type: 'EXPENSE',
        title: '예비비를 250,000원으로 올림',
        subtitle: null,
        status: 'APPROVED',
        dueDate: null,
        resolvedAt: '2026-03-03T11:41:00Z',
        resolvedBy: { id: 'mbr_02', name: '김지훈', role: 'OWNER' },
        denyReason: null,
        options: null,
        allowManual: null,
      },
    ],
    resolvedTotalCount: 12,
  }
}
