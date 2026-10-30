// 아직 서버 경로가 없는 두 가지(단계 구성 · 행사 시작)를 이 브라우저에만 적어둔다.
// 세부 수정(일정·금액·대상)은 #106 이 열려서 서버로 옮겼다 — 여기 남은 건 둘뿐이다.
// #213 3단계가 오면 이 파일을 지우고 api.ts 의 두 함수만 실호출로 바꾸면 된다.
//
// 서버는 이 값을 전혀 모른다. 다른 기기·다른 계정에서는 보이지 않는다.

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
