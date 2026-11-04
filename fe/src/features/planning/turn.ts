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

// skipped 줄이 사라지는 움직임 시간. index.css의 --animate-line-out과 맞춘다.
export const LINE_EXIT_MS = 180

// 화면에 그리는 작업 줄. slot은 줄의 자리(React key)다. 보통 operationId와 같고,
// 거절된 조건 줄을 다시 시도한 조건이 이어 쓰면 처음 줄의 자리를 물려받는다.
export interface TurnLine extends PlanProgress {
  slot?: string
}

// 같은 작업(operationId)의 줄은 제자리에서 결과 줄로 바꾼다.
// 끝에 다시 붙이면 "기록을 찾고 있어요"가 완료되는 순간 줄 순서가 바뀌어 위아래로 튄다.
//   "조건을 반영하고 있어요"(running) → "예상 인원 40명 반영했어요"(completed)  같은 자리
//   "조건을 반영하고 있어요"(running) → skipped(거절·같은 값)                  그대로 둠(보류)
//
// skipped 줄은 바로 지우지 않는다. 모델이 거절 이유를 보고 같은 변경을 다시 요청하는 일이 있어서다.
//   "…참가비는 20000원" → [검색, 참가비 변경] → 참가비 거절(검색 결과 전) → 다시 [참가비 변경] → 반영
// 바로 지우면 조건 줄이 사라졌다 다시 생긴다. 그래서 같은 턴에 조건 시작이 다시 오면 그 자리를
// 이어 쓰고, 오지 않으면 답변이 시작될 때 지운다(dropSkipped). 그동안은 "반영하고 있어요"로 보인다.
// skipped는 지울 줄이 있을 때만 의미가 있다. 없으면(예: 재접속으로 줄을 비운 뒤) 새로 붙이지 않는다.
export function upsertProgress(lines: TurnLine[], event: PlanProgress): TurnLine[] {
  const index = lines.findIndex((line) => line.operationId === event.operationId)
  if (index >= 0) {
    const old = lines[index]
    const next = [...lines]
    // 보류 중에는 진행 중 문구를 그대로 보인다("바뀐 조건이 없어요"는 화면에 쓰지 않는다).
    next[index] = {
      ...event,
      slot: old.slot,
      text: event.status === 'skipped' ? old.text : event.text,
    }
    return next
  }
  if (event.status === 'skipped') return lines
  const held = lines.findIndex((line) => line.status === 'skipped')
  if (event.kind === 'condition_started' && held >= 0) {
    const next = [...lines]
    next[held] = { ...event, slot: lines[held].slot ?? lines[held].operationId }
    return next
  }
  return [...lines, event].slice(-MAX_TURN_LINES)
}

// 답변이 시작되면 보류 중인 skipped 줄을 사라지는 움직임 뒤 목록에서 뺀다. 남은 줄은 그대로다.
export function dropSkipped(lines: TurnLine[]): TurnLine[] {
  return lines.filter((line) => line.status !== 'skipped')
}

// 답변 위에 남길 줄. 끝나지 않았거나(running) 결과가 없는(skipped) 줄은 남기지 않는다.
// 기록 없음(empty)은 토리가 실제로 찾아본 일이라 남긴다.
export function finishedLines(lines: TurnLine[]): TurnLine[] {
  return lines.filter(
    (line) => line.status === 'completed' || line.status === 'empty' || line.status === 'failed',
  )
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
