// 목록이 들어올 때 항목을 한 번에 띄우지 않고 차례로 띄운다(#353).
// 위에서 아래로 훑는 느낌을 주어, 한 덩어리가 툭 나타나는 것보다 읽기 쉽다.
//
// 앞 8개까지만 늦춘다. 그 뒤로는 기다리는 시간이 길어지기만 하고 눈에 띄지 않는다.
// 30ms로 뒀더니 차례로 뜨는 것이 느껴지지 않아 70ms로 늘렸다.
// 70ms × 7 = 490ms 로, 마지막 항목이 반 초 안에는 자리를 잡는다.
const STEP_MS = 70
const MAX_INDEX = 7

export function staggerDelay(index: number): string {
  return `${Math.min(index, MAX_INDEX) * STEP_MS}ms`
}
