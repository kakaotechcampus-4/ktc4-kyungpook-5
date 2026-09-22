// 서버 호출 함수 + 응답 타입 — FE API 명세 §1 행사 계획(P1 · P2).
//
// BE의 계획 라우터가 아직 비어 있어서 **이 호출들은 지금 아무도 부르지 않는다.**
// 화면은 훅에서 목업으로만 움직인다(M1·L2·R1과 같은 방식).
// 엔드포인트가 생기는 것부터 hooks.ts의 해당 함수를 여기 호출로 갈아끼우면 된다.
import { apiGet, apiGetPage, apiPatch, apiPost } from '@/shared/api/client'
import type {
  EventDraftItem,
  EventPlan,
  PlanChatResult,
  PlanChatTurn,
  PlanCollected,
  PlanConversation,
  PlanDraftCreated,
  PlanStep,
  StepPatch,
  StepPhase,
} from '@/features/planning/types'

// TODO: 로그인 응답의 소속 동아리로 바꾼다. 아직 클럽 컨텍스트가 없어 명세 예시값을 쓴다.
export const CURRENT_CLUB_ID = 'clb_3a71c0'

// GET /events/drafts — 라우팅 주의: /events/{eventId}보다 먼저 등록돼야 한다(명세).
export function getDrafts(clubId: string = CURRENT_CLUB_ID): Promise<EventDraftItem[]> {
  return apiGetPage<EventDraftItem>(`/events/drafts?clubId=${encodeURIComponent(clubId)}`).then(
    (body) => body.data,
  )
}

// POST /events — Event(PLANNING) + Conversation을 함께 만들고 첫 인사까지 받는다.
export function createPlan(title?: string, clubId: string = CURRENT_CLUB_ID) {
  return apiPost<PlanDraftCreated>('/events', { clubId, ...(title ? { title } : {}) })
}

// GET /conversations/{conversationId}/messages — "이어서 하기"로 대화를 복원한다.
export function getConversation(conversationId: string): Promise<PlanConversation> {
  return apiGet<PlanConversation>(`/conversations/${conversationId}/messages`)
}

// POST /conversations/{conversationId}/messages — 1단계 챗봇에 한 마디 보낸다.
export function sendMessage(conversationId: string, content: string): Promise<PlanChatResult> {
  return apiPost<PlanChatResult>(`/conversations/${conversationId}/messages`, { content })
}

// POST /events/{eventId}/plan:generate — 수십 초 걸릴 수 있어 로딩 처리가 필요하다(명세).
// 🔸 콜론 표기는 팀 합의 대기 중. `/plan/generate`로 바뀔 수 있다.
export function generatePlan(eventId: string): Promise<EventPlan> {
  return apiPost<EventPlan>(`/events/${eventId}/plan:generate`, {})
}

// GET /events/{eventId}/plan — P2 화면 전체를 한 번에 그린다.
export function getPlan(eventId: string): Promise<EventPlan> {
  return apiGet<EventPlan>(`/events/${eventId}/plan`)
}

// PATCH /events/{eventId}/steps/{stepId} — 보낸 필드만 갱신된다.
export function updateStep(eventId: string, stepId: string, patch: StepPatch): Promise<PlanStep> {
  return apiPatch<PlanStep>(`/events/${eventId}/steps/${stepId}`, patch)
}

// PATCH /events/{eventId}/steps:reorder — 개별 PATCH 금지. 전체를 한 번에 교체한다(명세).
export function reorderSteps(
  eventId: string,
  steps: Array<{ stepId: string; phase: StepPhase }>,
): Promise<PlanStep[]> {
  return apiPatch<PlanStep[]>(`/events/${eventId}/steps:reorder`, { steps })
}

// PATCH /events/{eventId} — 임시 저장. saved_at을 갱신한다.
export function savePlan(
  eventId: string,
  patch: {
    title?: string
    startDate?: string
    endDate?: string
    budgetTotal?: number
    feePerPerson?: number
    headcount?: number
  },
) {
  return apiPatch<{ id: string; title: string; savedAt: string }>(`/events/${eventId}`, patch)
}

// POST /events/{eventId}:confirm — PLANNING → ON_GOING. 새 행사 행이 생기지 않는다.
export function confirmPlan(eventId: string) {
  return apiPost<{ id: string; status: 'ON_GOING'; title: string; startDate: string }>(
    `/events/${eventId}:confirm`,
    {},
  )
}

// ── 목업 ──
// API가 아직 안 떠 있을 때 화면을 확인하기 위한 것. 시안과 같은 데이터다.

export const NEW_PLAN_ID = 'evt_9f2c8a'

// 새 계획을 시작했을 때의 첫 인사. POST /events 응답의 messages[0]에 해당한다.
export function getGreetingMock(): PlanChatTurn {
  return {
    id: 'msg_01',
    role: 'ASSISTANT',
    content: '어떤 행사를 준비하시나요?',
    createdAt: '2026-03-01T04:12:00Z',
    quickReplies: ['MT', 'WELCOME', 'PICNIC', 'ACADEMIC'],
  }
}

export function getEmptyCollectedMock(): PlanCollected {
  return {
    eventType: null,
    startDate: null,
    endDate: null,
    headcount: null,
    budgetTotal: null,
    locationCandidates: null,
  }
}

export function getCollectedMock(): PlanCollected {
  return {
    eventType: 'MT',
    startDate: '2026-03-21',
    endDate: '2026-03-22',
    headcount: 32,
    budgetTotal: 2000000,
    locationCandidates: ['가평', '양평'],
  }
}

// 시안의 1단계 대화 그대로. 말풍선 안의 칩·참고 카드는 화면 전용 필드다(types.ts 참고).
export function getConversationMock(): PlanChatTurn[] {
  return [
    getGreetingMock(),
    {
      id: 'msg_02',
      role: 'USER',
      content: '봄 MT요. 3월 셋째 주 주말에 1박 2일로 생각하고 있어요.',
      createdAt: '2026-03-01T04:14:00Z',
    },
    {
      id: 'msg_03',
      role: 'ASSISTANT',
      content: '작년 봄 MT 기록을 찾았습니다. 이 내용을 출발점으로 쓸까요?',
      createdAt: '2026-03-01T04:15:00Z',
      reference: {
        title: '2025 봄 MT · 정산 문서에서 불러옴',
        rows: [
          ['참가 인원', '32명 (신청 35명 · 취소 3명)'],
          ['장소', '가평 ○○펜션 1박'],
          ['1인 회비', '40,000원'],
          ['총 지출', '1,700,000원 (예비비 초과 1건)'],
        ],
      },
    },
    {
      id: 'msg_04',
      role: 'USER',
      content: '네. 인원은 32명 정도, 예산은 200만 원 안쪽, 장소는 가평 아니면 양평이요.',
      createdAt: '2026-03-01T04:18:00Z',
    },
    {
      id: 'msg_05',
      role: 'ASSISTANT',
      content: '정리했습니다. 이대로 다음 단계로 넘어가면 필요한 할 일 블록을 배열해 드릴게요.',
      createdAt: '2026-03-01T04:20:00Z',
    },
  ]
}

export function getDraftsMock(): EventDraftItem[] {
  return [
    {
      id: 'evt_5c11a2',
      title: '여름 워크샵',
      stage: 'CHAT',
      savedAt: '2026-03-02T11:40:00Z',
      conversationId: 'cnv_88ae01',
    },
    {
      id: 'evt_7b02f4',
      title: '가을 체육대회',
      stage: 'FLOW',
      savedAt: '2026-02-28T09:02:00Z',
      conversationId: 'cnv_12cc33',
    },
  ]
}

// 시안의 7단계. 마감 시각은 KST 기준 문구와 맞도록 UTC로 적었다(3/12 23:59 KST = 14:59Z).
// 🔸 "세부사항 조정"·"피드백 기록"은 ActionType에 딱 맞는 값이 없다. 시안도 이 둘만
// 배지가 없어서, 배지가 붙지 않는 CONFIRMATION으로 뒀다.
export function getPlanMock(): EventPlan {
  return {
    eventId: NEW_PLAN_ID,
    title: '2026 봄 MT',
    phases: [
      {
        phase: 'PREPARATION',
        name: '사전 준비',
        description: '인원과 예산의 윤곽을 잡습니다',
        steps: [
          {
            id: 'stp_01',
            stepOrder: 10,
            phase: 'PREPARATION',
            name: '사전 수요 조사',
            actor: 'APPROVAL_REQUIRED',
            startedTime: '2026-03-05T00:00:00Z',
            deadline: null,
            actions: [
              {
                id: 'act_01',
                type: 'NOTICE',
                title: '수요조사 폼 발송',
                subtitle:
                  '수요조사 폼을 만들어 단톡방에 올립니다. 폼 생성은 자동, 발송 직전 승인 한 번.',
                irreversible: true,
                approveNeeded: true,
                amount: null,
              },
            ],
          },
          {
            id: 'stp_02',
            stepOrder: 20,
            phase: 'PREPARATION',
            name: '세부사항 조정',
            actor: 'AI',
            startedTime: '2026-03-07T00:00:00Z',
            deadline: null,
            actions: [
              {
                id: 'act_02',
                type: 'CONFIRMATION',
                title: '인원 · 예산 재계산',
                subtitle: '응답을 반영해 인원·예산을 다시 계산하고 최종 일정을 확정합니다.',
                irreversible: false,
                approveNeeded: false,
                amount: null,
              },
            ],
          },
        ],
      },
      {
        phase: 'RECRUITING',
        name: '모집 · 확정',
        description: '자리를 잡고 참가비를 걷습니다',
        steps: [
          {
            id: 'stp_03',
            stepOrder: 30,
            phase: 'RECRUITING',
            name: '장소 · 차량 확보',
            actor: 'MANUAL',
            startedTime: '2026-03-08T00:00:00Z',
            deadline: '2026-03-09T09:00:00Z',
            actions: [],
          },
          {
            id: 'stp_04',
            stepOrder: 40,
            phase: 'RECRUITING',
            name: '최종 모집 공지',
            actor: 'APPROVAL_REQUIRED',
            startedTime: '2026-03-10T00:00:00Z',
            deadline: null,
            actions: [
              {
                id: 'act_03',
                type: 'NOTICE',
                title: '모집 공지 발송',
                subtitle: '구글 폼 생성 + 단톡방 발송. 발송은 되돌릴 수 없어 승인이 필요합니다.',
                irreversible: true,
                approveNeeded: true,
                amount: null,
              },
            ],
          },
          {
            id: 'stp_05',
            stepOrder: 50,
            phase: 'RECRUITING',
            name: '입금 내역 확인',
            actor: 'AI',
            startedTime: '2026-03-10T00:00:00Z',
            deadline: '2026-03-12T14:59:00Z',
            actions: [
              {
                id: 'act_04',
                type: 'TRANSFER',
                title: '입금자명 대조',
                subtitle:
                  '1인 45,000원 · 마감 3/12 23:59. 입금자명을 자동 대조하고, 미납자 안내는 D-2에 초안까지 준비합니다(발송은 승인).',
                irreversible: false,
                approveNeeded: false,
                amount: 45000,
              },
            ],
          },
        ],
      },
      {
        phase: 'EXECUTION',
        name: '행사 진행 · 마무리',
        description: '돈을 정산하고 기록을 남깁니다',
        steps: [
          {
            id: 'stp_06',
            stepOrder: 60,
            phase: 'EXECUTION',
            name: '영수 처리',
            actor: 'APPROVAL_REQUIRED',
            startedTime: '2026-03-23T00:00:00Z',
            deadline: null,
            actions: [
              {
                id: 'act_05',
                type: 'EXPENSE',
                title: '영수증 정리',
                subtitle: '영수증을 항목별로 정리하고, 예산 초과분만 묶어서 승인 요청합니다.',
                irreversible: false,
                approveNeeded: true,
                amount: null,
              },
            ],
          },
          {
            id: 'stp_07',
            stepOrder: 70,
            phase: 'EXECUTION',
            name: '피드백 기록',
            actor: 'AI',
            startedTime: '2026-03-25T00:00:00Z',
            deadline: null,
            actions: [
              {
                id: 'act_06',
                type: 'CONFIRMATION',
                title: '행사 기록 저장',
                subtitle: '이번 행사 기록을 다음 행사용 자료로 저장합니다.',
                irreversible: false,
                approveNeeded: false,
                amount: null,
              },
            ],
          },
        ],
      },
    ],
    summary: {
      totalSteps: 7,
      countByActor: { AI: 3, APPROVAL_REQUIRED: 3, MANUAL: 1 },
      collectionPlan: { times: 1, feePerPerson: 45000 },
      noticeCount: 2,
      periodStart: '2026-03-02',
      periodEnd: '2026-03-25',
    },
    warnings: [
      {
        source: 'RULE',
        code: 'SCHEDULE_GAP',
        params: {
          fromStep: '입금 마감',
          fromDate: '2026-03-12',
          toStep: '행사 당일',
          toDate: '2026-03-21',
          gapDays: 9,
        },
        suggestion: 'ADD_CHECKPOINT',
        debugMessage: '입금 마감과 행사 당일 사이 9일 공백',
      },
    ],
    excludedSteps: [
      { name: '일정 확정', reason: '세부사항 조정에 포함' },
      { name: '가능 여부 확인·재확인', reason: '장소·차량 확보로 병합' },
      { name: '담당 인원 배치', reason: '각 단계 담당자 항목으로' },
      { name: '과거 기록 참고', reason: '1단계 대화에서 처리' },
      { name: '행사 시작', reason: '행사 당일 표시로' },
      { name: '리허설', reason: '뺀 단계 (MT 해당 없음)' },
    ],
  }
}
