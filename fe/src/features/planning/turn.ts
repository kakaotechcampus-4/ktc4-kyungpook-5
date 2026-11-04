// 토리 응답 한 번의 작업 줄을 다루는 순수 함수(#290). 화면 상태와 떼어 테스트한다.
//
//   [나] 인원은 40명으로 바꿔 줘
//   [토리] ✓ 예상 인원 40명 반영했어요      ← 작업 줄(progress 이벤트)
//          ┌ 인원을 40명으로 바꿨어요. … ┐  ← 답변 말풍선
//
// 작업 줄은 서버에 저장되지 않는다. 답변이 끝난 뒤에도 이번 화면에서는 답변 위에 남겨,
// 진행 표시에서 답변으로 넘어갈 때 줄이 사라지지 않게 한다. 새로고침하면 답변만 남는다.
import type { ChatMessage, PlanProgress } from './types'

// 한 턴에 보이는 작업 줄 수 상한. 조건 반영·기록 검색·초안 생성으로 보통 1~3줄이다.
export const MAX_TURN_LINES = 4

// 같은 작업(operationId)의 줄은 제자리에서 결과 줄로 바꾼다.
// 끝에 다시 붙이면 "기록을 찾고 있어요"가 완료되는 순간 줄 순서가 바뀌어 위아래로 튄다.
export function upsertProgress(lines: PlanProgress[], event: PlanProgress): PlanProgress[] {
  const index = lines.findIndex((line) => line.operationId === event.operationId)
  if (index < 0) return [...lines, event].slice(-MAX_TURN_LINES)
  const next = [...lines]
  next[index] = event
  return next
}

// 이번 화면에서 끝난 턴의 작업 줄. base는 보낼 때 저장돼 있던 대화 수다.
// 서버는 메시지를 자체 ID로 저장해 보낸 messageId로는 찾을 수 없으므로 위치로 찾는다.
export interface TurnReceipt {
  base: number
  lines: PlanProgress[]
}

// 저장된 대화의 각 턴 답변 위에 작업 줄을 붙인다.
// 대화는 뒤에 덧붙기만 하므로 base 자리는 이번 턴의 내 말, 그다음이 토리 답변이다.
// 답변이 저장되지 않은 턴이면 붙이지 않는다(다음 턴 답변에 잘못 붙지 않게).
export function attachReceipts(messages: ChatMessage[], receipts: TurnReceipt[]): ChatMessage[] {
  if (!receipts.length) return messages
  const result = [...messages]
  for (const { base, lines } of receipts) {
    const reply = result[base + 1]
    if (result[base]?.from === '나' && reply?.from === '토리' && lines.length)
      result[base + 1] = { ...reply, receipt: lines }
  }
  return result
}
