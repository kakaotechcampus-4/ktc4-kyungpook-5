// 이전 데모에서 사용하던 localStorage 형식이다. 계획 저장·시작은 이제 서버 API를
// 사용하므로 새 화면 경로에서는 읽지 않는다. 기존 브라우저 데이터 호환만 남긴다.

const KEY = 'unyounghae_local_plan_v1'

export interface LocalPlan {
  // 포함한 단계 코드. 배열 순서가 곧 묶음 안의 순서다. null이면 아직 손대지 않았다는 뜻.
  codes: string[] | null
  started: boolean
}

const EMPTY: LocalPlan = { codes: null, started: false }

function readAll(): Record<string, LocalPlan> {
  try {
    const raw = localStorage.getItem(KEY)
    const parsed: unknown = raw === null ? null : JSON.parse(raw)
    return parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, LocalPlan>)
      : {}
  } catch {
    return {}
  }
}

function writeAll(value: Record<string, LocalPlan>): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(value))
  } catch {
    // 저장소를 못 써도 이번 화면의 흐름은 이어갈 수 있다.
  }
}

export function loadLocalPlan(eventId: string): LocalPlan {
  const saved = readAll()[eventId]
  if (!saved) return EMPTY
  return {
    codes: Array.isArray(saved.codes) ? saved.codes.filter((c) => typeof c === 'string') : null,
    started: saved.started === true,
  }
}

export function saveLocalPlan(eventId: string, patch: Partial<LocalPlan>): LocalPlan {
  const all = readAll()
  const next: LocalPlan = { ...EMPTY, ...all[eventId], ...patch }
  all[eventId] = next
  writeAll(all)
  return next
}
