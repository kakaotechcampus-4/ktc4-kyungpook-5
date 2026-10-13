// P1 시연용 예시. 주소에 ?demo가 있을 때만 쓴다(다른 화면과 같은 방식).
// TODO(연동): POST /plans/chat
import type { ChatMessage, PlanFacts } from '@/features/planning/types'

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
