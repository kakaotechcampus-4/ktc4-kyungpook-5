// 서버에 아직 없는 두 가지(단계 저장 · 행사 시작)를 이 브라우저에만 적어둔다.
// #213 에서 엔드포인트가 생기면 이 파일을 지우고 api.ts 의 두 함수만 실호출로 바꾸면 된다.
//
// 서버는 이 값을 전혀 모른다. 다른 기기·다른 계정에서는 보이지 않는다.

const KEY = 'unyounghae_local_plan_v1'

// 단계 하나의 세부 사항(#106 의 세부 수정 모달이 다루는 값).
// 일정은 Step, 나머지는 그 단계의 Action 에 해당한다. 이름은 서버 계약을 따른다.
export interface LocalSchedule {
  startsAt: string | null
  deadline: string | null
  title?: string
  dueDate?: string | null
  amount?: number | null
  channel?: string
  audience?: string
  sendTiming?: string
  vendor?: string
  cancelTerms?: string
  account?: string
  receiptRequired?: boolean
  approvalMode?: 'BATCH' | 'EACH'
}

export interface LocalPlan {
  // 포함한 단계 코드. 배열 순서가 곧 묶음 안의 순서다. null이면 아직 손대지 않았다는 뜻.
  codes: string[] | null
  // StepCode → 세부 사항. 손댄 단계만 들어간다.
  schedule: Record<string, LocalSchedule>
  started: boolean
}

const EMPTY: LocalPlan = { codes: null, schedule: {}, started: false }

function normalizeSchedule(value: unknown): Record<string, LocalSchedule> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return {}
  const result: Record<string, LocalSchedule> = {}
  for (const [code, raw] of Object.entries(value as Record<string, unknown>)) {
    const item = raw !== null && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
    // 일정 둘만 모양을 보장하고, 나머지 밭은 저장된 값을 그대로 돌려준다.
    result[code] = {
      ...(item as Omit<LocalSchedule, 'startsAt' | 'deadline'>),
      startsAt: typeof item.startsAt === 'string' ? item.startsAt : null,
      deadline: typeof item.deadline === 'string' ? item.deadline : null,
    }
  }
  return result
}

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
    schedule: normalizeSchedule(saved.schedule),
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
