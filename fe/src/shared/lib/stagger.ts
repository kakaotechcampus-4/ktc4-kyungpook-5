// 목록이 들어올 때 항목을 한 번에 띄우지 않고 차례로 띄운다(#353).
// 위에서 아래로 훑는 느낌을 주어, 한 덩어리가 툭 나타나는 것보다 읽기 쉽다.
//
// 앞 8개까지만 늦춘다. 그 뒤로는 기다리는 시간이 길어지기만 하고 눈에 띄지 않는다.
// 30ms × 7 = 210ms 로, 움직임 자체(turn-in 200ms)와 비슷한 길이에서 끝난다.
const STEP_MS = 30
const MAX_INDEX = 7

export function staggerDelay(index: number): string {
  return `${Math.min(index, MAX_INDEX) * STEP_MS}ms`
}
