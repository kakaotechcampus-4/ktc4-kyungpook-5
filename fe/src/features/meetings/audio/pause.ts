// 일시정지한 동안에도 무음 프레임이 나가서 durationMs는 계속 늘어난다.
// 녹음 시간에서는 그 시간을 뺀다.
export interface PauseClock {
  durationMs: number
  pausedMs: number
  pausedAtMs: number | null
}

export function pausedAt(clock: PauseClock) {
  return { pausedAtMs: clock.durationMs }
}

export function resumedAt(clock: PauseClock) {
  return {
    pausedMs: clock.pausedMs + clock.durationMs - (clock.pausedAtMs ?? clock.durationMs),
    pausedAtMs: null,
  }
}

export function recordedTime(clock: PauseClock) {
  return (clock.pausedAtMs ?? clock.durationMs) - clock.pausedMs
}
