// P1 시연용 예시. 주소에 ?demo가 있을 때만 쓴다(다른 화면과 같은 방식).
// TODO(연동): POST /plans/chat
import type {
  ChatMessage,
  PlanFacts,
  PlanStep,
  PlanSummary,
  PlanWarning,
  StepPhase,
} from '@/features/planning/types'

export const FIRST_MESSAGE: ChatMessage = {
  id: 'msg_00',
  from: '토리',
  text: '안녕하세요! 어떤 행사를 준비하시나요?',
  quickReplies: ['MT', '워크샵', '신환회', '직접 입력'],
}

export const DEMO_MESSAGES: ChatMessage[] = [
  { id: 'msg_01', from: '토리', text: '안녕하세요! 어떤 행사를 준비하시나요?' },
  { id: 'msg_02', from: '나', text: '봄 MT 하려고요' },
  {
    id: 'msg_03',
    from: '토리',
    text: '작년 봄 MT 기록을 봤어요. 1박 2일, 가평 펜션, 28명이 참가했네요. 올해도 비슷한 규모일까요?',
  },
  { id: 'msg_04', from: '나', text: '네, 32명 정도 예상해요' },
  {
    id: 'msg_05',
    from: '토리',
    text: '참가비는 작년에 1인 45,000원이었어요. 올해도 같게 할까요?',
    quickReplies: ['같게 할게요', '올릴게요', '아직 모르겠어요'],
  },
  { id: 'msg_06', from: '나', text: '같게 할게요' },
  {
    id: 'msg_07',
    from: '토리',
    text: '좋아요. 일정은 언제가 좋을까요? 작년에는 3월 셋째 주였어요.',
    quickReplies: ['3월 셋째 주', '3월 넷째 주', '직접 입력'],
  },
]

export const DEMO_FACTS: PlanFacts = {
  '행사 이름': { value: '2026 봄 MT', decided: true },
  종류: { value: 'MT · 1박 2일', decided: true },
  '예상 인원': { value: '32명', decided: true },
  참가비: { value: '1인 45,000원', decided: true },
  일정: { value: '아직 안 정했어요', decided: false },
  장소: { value: '후보 2곳 (가평 ○○펜션 외)', decided: false },
}

// 과거 기록을 봤을 때만 보인다. 무엇을 보고 무엇을 알아냈는지 적는다.
export const DEMO_REFERENCE =
  '2025 봄 MT 결과보고 · 28명 · 1인 45,000원 · 가평 ○○펜션. 예비비 130,000원을 잡았는데 172,000원을 썼어요.'

// 계획을 만드는 동안 보이는 단계. 2단계로 넘어갈 때 쓴다.
export const PLAN_STEPS = [
  { label: '과거 기록 확인', desc: '올린 자료가 있으면 먼저 봅니다' },
  { label: '단계 고르기' },
  { label: '일정 계산' },
  { label: '수금·공지 정리' },
]

// ── 2단계 ──
// TODO(연동): POST /plans → GET /plans/{id}/steps
export const DEMO_PLAN_STEPS: PlanStep[] = [
  {
    id: 'stp_01',
    phase: '사전 준비',
    name: '사전 수요 조사',
    actor: '승인 필요',
    actionLabel: '공지',
    date: '3/5',
    desc: '수요조사 폼을 만들어 단톡방에 올립니다. 폼 생성은 자동, 발송 직전 승인 한 번.',
  },
  {
    id: 'stp_02',
    phase: '사전 준비',
    name: '인원·일정 확정',
    actor: 'AI 실행',
    actionLabel: '확인 요청',
    date: '3/7',
    desc: '응답을 반영해 인원·예산을 다시 계산하고 최종 일정을 확정합니다.',
  },
  {
    id: 'stp_03',
    phase: '모집 · 확정',
    name: '예약',
    actor: '직접 수행',
    actionLabel: '계약 · 이체',
    date: '3/8',
    desc: '확정 인원으로 계약하고 계약금을 이체합니다.',
  },
  {
    id: 'stp_04',
    phase: '모집 · 확정',
    name: '모집 공지',
    actor: '승인 필요',
    actionLabel: '공지',
    date: '3/10',
    desc: '구글 폼 생성 + 단톡방 발송. 발송은 되돌릴 수 없어 승인이 필요합니다.',
  },
  {
    id: 'stp_05',
    phase: '모집 · 확정',
    name: '입금 내역 확인',
    actor: 'AI 실행',
    actionLabel: '수금',
    date: '3/12',
    desc: '1인 45,000원 · 마감 3/12 23:59. 입금자명을 자동 대조하고 미납자 안내를 준비합니다.',
  },
  {
    id: 'stp_06',
    phase: '행사 진행 · 마무리',
    name: '지출 정산',
    actor: '승인 필요',
    actionLabel: '지출',
    date: '3/23',
    desc: '영수증을 항목별로 정리하고, 예산 초과분만 묶어서 승인 요청합니다.',
  },
  {
    id: 'stp_07',
    phase: '행사 진행 · 마무리',
    name: '피드백 기록',
    actor: 'AI 실행',
    actionLabel: '확인 요청',
    date: '3/25',
    desc: '이번 행사 기록을 다음 행사용 자료로 저장합니다.',
  },
]

export const PHASE_DESC: Record<StepPhase, string> = {
  '사전 준비': '인원과 예산의 윤곽을 잡습니다',
  '모집 · 확정': '자리를 잡고 참가비를 걷습니다',
  '행사 진행 · 마무리': '돈을 정산하고 기록을 남깁니다',
}

export const DEMO_SUMMARY: PlanSummary = {
  totalSteps: 7,
  aiSteps: 3,
  approvalSteps: 3,
  manualSteps: 1,
  collect: '1회 · 1인 45,000원',
  notice: '2회',
  period: '3/2 → 3/25',
}

export const DEMO_WARNING: PlanWarning = {
  title: '시작 전에 확인해 주세요',
  body: '입금 마감(3/12)과 행사 당일(3/21) 사이가 9일 비어 있어요. 단계를 넣거나 빼서 메울 수 있어요.',
  actionLabel: '단계 수정하기',
}

// 2단계 머리에 붙는 한 줄. 1단계에서 정한 것이 그대로 온다.
export const DEMO_PLAN_META = '2026 봄 MT · 32명 · 예산 2,000,000원 · 3/2 준비 → 3/25 기록'

// 단계를 하나도 안 넣었을 때. P2는 1단계를 거쳐야 들어오는 화면이라 거의 보이지 않는다.
export const EMPTY_SUMMARY: PlanSummary = {
  totalSteps: 0,
  aiSteps: 0,
  approvalSteps: 0,
  manualSteps: 0,
  collect: '없음',
  notice: '없음',
  period: '미정',
}
