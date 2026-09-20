// 서버 호출 함수 + 응답 타입
//
// TODO: M1 메인은 아직 FE API 명세에 없다. 화면 동작 확인용 목업이며,
// 엔드포인트가 정해지면 shared/api/client 호출로 교체한다.
import type { BudgetForecast, EventSummary } from '@/features/dashboard/types'

export function getEventSummaries(): EventSummary[] {
  return [
    {
      id: 'evt_prev',
      title: '2026 새내기 배움터',
      statusLabel: '정산 중',
      ddayLabel: '2/22 종료',
      pendingActions: [
        {
          id: 'act_p1',
          typeLabel: '지출',
          title: '뒤풀이 식대 정산 승인',
          subtitle: '합계 84,000원 · 영수증 1건 확인됨',
        },
      ],
      reasoning: '정산 마지막 항목입니다. 승인하면 이 행사는 COMPLETE로 넘어갑니다.',
      totalSteps: 9,
      currentStepIndex: 8,
      scheduleNote: '9단계 중 8단계 · 마무리 단계',
      steps: [
        { name: '과거 기록 참고', state: 'DONE' },
        { name: '담당 배치', state: 'DONE' },
        { name: '수요 조사', state: 'DONE' },
        { name: '일정 확정', state: 'DONE' },
        { name: '모집 공지', state: 'DONE' },
        { name: '입금 확인', state: 'DONE' },
        { name: '리허설', state: 'DONE' },
        { name: '행사 진행', state: 'DONE' },
        { name: '정산·기록', state: 'CURRENT' },
      ],
    },
    {
      id: 'evt_9f2c8a',
      title: '2026 봄 MT',
      statusLabel: '진행 중',
      ddayLabel: '3/21 출발까지 11일',
      pendingActions: [
        {
          id: 'act_21',
          typeLabel: '외부 발송',
          title: '미납자 4명에게 2차 납부 안내 문자 보내기',
          subtitle: '대상 4명 · 비용 0원 · 마감 D-2',
        },
        {
          id: 'act_09',
          typeLabel: '이체',
          title: '펜션 계약금 100,000원 이체하고 예약 확정',
          subtitle: '3/16부터 환불 불가 · 잔고 2,412,000원',
        },
        {
          id: 'act_15',
          typeLabel: '지출',
          title: '장보기·버스 잔금 등 지출 4건 묶음 승인',
          subtitle: '합계 182,000원 · 영수증 4건 확인됨',
        },
      ],
      reasoning:
        '납부 마감이 이틀 남았는데 1차 안내 이후 사흘째 추가 입금이 없습니다. 계약금 납부일(3/14)이 명단 확정일(3/13)보다 하루 뒤라, 미납이 정리되지 않으면 인원 기준 없이 계약금을 넣게 됩니다.',
      totalSteps: 9,
      currentStepIndex: 3,
      scheduleNote: '9단계 중 4단계 · 예정보다 하루 늦음',
      steps: [
        { name: '과거 기록 참고', state: 'DONE' },
        { name: '담당 배치', state: 'DONE' },
        { name: '수요 조사', state: 'DONE' },
        { name: '일정 확정', state: 'DONE' },
        { name: '모집 공지', state: 'CURRENT' },
        { name: '입금 확인', state: 'CURRENT' },
        { name: '리허설', state: 'TODO' },
        { name: '행사 진행', state: 'TODO' },
        { name: '정산·기록', state: 'TODO' },
      ],
    },
    {
      id: 'evt_summer',
      title: '여름 워크샵',
      statusLabel: '계획 중',
      ddayLabel: '아직 일정 미정',
      pendingActions: [],
      reasoning: '계획 1단계 대화가 아직 진행 중입니다. 확정되면 여기에 승인 대기 항목이 표시됩니다.',
      totalSteps: 7,
      currentStepIndex: 0,
      scheduleNote: '계획 단계 · Step 생성 전',
      steps: [],
    },
  ]
}

export function getBudgetForecast(eventId: string): BudgetForecast {
  if (eventId !== 'evt_9f2c8a') {
    return {
      hasHistory: false,
      confirmedBalance: 0,
      confirmedBalanceNote: '',
      planExpected: 0,
      historicalExpected: 0,
      diffNote: '',
      upcomingTransactions: [],
      chart: { labels: [], actualBalances: [], planLine: [], historicalLine: [] },
    }
  }

  return {
    hasHistory: true,
    confirmedBalance: 2412000,
    confirmedBalanceNote: '3월 10일 입금까지 반영된 실제 금액',
    planExpected: 1930000,
    historicalExpected: 1760000,
    diffNote: '차이 170,000원. 과거에는 계획보다 더 썼습니다.',
    upcomingTransactions: [
      { id: 'tx_1', date: '3/12', label: '회비 미납분 4명', statusLabel: 'confirmed', amount: 180000 },
      { id: 'tx_2', date: '3/14', label: '펜션 계약금', statusLabel: 'pending', amount: -100000 },
      { id: 'tx_3', date: '3/18', label: '버스 잔금·식자재', statusLabel: 'expected', amount: -342000 },
      { id: 'tx_4', date: '3/21', label: '행사 당일 현장비', statusLabel: 'expected', amount: -120000 },
      { id: 'tx_5', date: '3/24', label: '정산·뒤풀이', statusLabel: 'expected', amount: -100000 },
    ],
    chart: {
      labels: ['2/17', '2/24', '3/3', '3/10', '3/14', '3/18', '3/21', '3/24'],
      actualBalances: [1980000, 2150000, 2290000, 2410000, null, null, null, null],
      planLine: [null, null, null, 2410000, 2200000, 2050000, 1980000, 1930000],
      historicalLine: [null, null, null, 2410000, 2100000, 1950000, 1830000, 1760000],
    },
  }
}
