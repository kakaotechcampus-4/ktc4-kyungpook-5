// 조건 완료 시 바뀐 칸을 강조하고, 저장 결과가 다를 때만 다시 강조한다(#302).
import type { PlanFactKey, PlanFacts } from './types'

// 강조가 보이는 시간. index.css의 --animate-fact-flash와 맞춘다.
export const FACT_FLASH_MS = 1500

// at: 강조를 시작한 시각(Date.now()). 같은 칸이 연달아 바뀌어도 at이 달라 강조가 처음부터 다시 돈다.
export interface FactFlash {
  at: number
  keys: PlanFactKey[]
}

// 값이나 상태(확정·잠정·미정·나중에)가 달라진 칸. 근거 발화만 바뀐 것은 강조하지 않는다.
//   before { 예상 인원: 30명 확정 }  after { 예상 인원: 40명 확정, 일정: 12/5 – 12/6 확정 }
//   → ['예상 인원', '일정']
export function changedFacts(before: PlanFacts, after: PlanFacts): PlanFactKey[] {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)] as PlanFactKey[])
  return [...keys].filter(
    (key) => before[key]?.status !== after[key]?.status || before[key]?.value !== after[key]?.value,
  )
}

// 아직 보여 줄 시간이 남은 강조인지. 다른 계획을 보다 돌아와 패널이 다시 그려질 때
// 지난 강조가 또 켜지지 않게 한다.
export function flashLeft(flash: FactFlash | null | undefined, now: number): number {
  if (!flash || !flash.keys.length) return 0
  return Math.max(0, flash.at + FACT_FLASH_MS - now)
}
