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
