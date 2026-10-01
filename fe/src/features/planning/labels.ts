// 서버 enum 코드 → 화면 문구. 행사 계획에서만 쓰므로 shared 대신 여기 둔다.
import { formatCurrency, formatMonthDay } from '@/shared/lib/format'
import { ACTION_TYPE_LABEL } from '@/shared/lib/labels'
import type {
  ActionType,
  EventType,
  PlanCollected,
  PlanWarning,
  StepActor,
} from '@/features/planning/types'

export const EVENT_TYPE_LABEL: Record<EventType, string> = {
  MT: 'MT',
  WELCOME: '개총 · 신환회',
  PICNIC: '피크닉',
  ACADEMIC: '학술행사',
  WORKSHOP: '워크샵',
  ETC: '기타',
}

// 첫 인사 말풍선에 붙는 유형 칩. WORKSHOP·ETC는 시안에 없어 뺐다.
export const EVENT_TYPE_QUICK_REPLIES: EventType[] = ['MT', 'WELCOME', 'PICNIC', 'ACADEMIC']

export const ACTOR_LABEL: Record<StepActor, string> = {
  AI: 'AI 실행',
  APPROVAL_REQUIRED: '승인 필요',
  MANUAL: '직접 수행',
}

// 요약 카드의 단위만 주체마다 다르다(시안: 3개 / 3곳 / 1개).
export const ACTOR_UNIT: Record<StepActor, string> = {
  AI: '개',
  APPROVAL_REQUIRED: '곳',
  MANUAL: '개',
}

// 점 색이 곧 수행 주체다. L2 StepProgressCard의 막대 색과 같은 값을 쓴다.
export const ACTOR_DOT_CLASS: Record<StepActor, string> = {
  AI: 'bg-[#5a7599]',
  APPROVAL_REQUIRED: 'bg-[#aa7c3a]',
  MANUAL: 'bg-white border-2 border-[#cdcdcd]',
}

// "3/21–3/22 (1박 2일)". 종료일이 없거나 같은 날이면 "3/21"만 쓴다.
function periodLabel(startDate: string, endDate: string | null): string {
  const start = formatMonthDay(startDate)
  if (!endDate || endDate === startDate) return start
  const nights = Math.round((Date.parse(endDate) - Date.parse(startDate)) / 86_400_000)
  return `${start}–${formatMonthDay(endDate)} (${nights}박 ${nights + 1}일)`
}

// 계획 화면의 TRANSFER는 회비를 걷는 쪽이라 시안 문구인 "수금"으로 쓴다.
// (L2의 TRANSFER는 나가는 이체라 shared의 "이체"가 맞다.)
const ACTION_BADGE_LABEL: Record<string, string> = { ...ACTION_TYPE_LABEL, TRANSFER: '수금' }

// 시안이 배지를 단 건 밖으로 나가거나 돈이 오가는 행동뿐이다.
// 내부 확인(CONFIRMATION)은 배지 없이 설명만 붙는다.
export function actionBadge(type: ActionType): string | null {
  return type === 'CONFIRMATION' ? null : (ACTION_BADGE_LABEL[type] ?? type)
}

// 우측 "지금까지 정해진 것". 명세 collected에 있는 5가지만 그린다.
// (시안에 있는 "교통수단"·"활동 내용"은 명세에 자리가 없어 넣지 않는다.)
// 값이 없는 줄은 빈 점 + "아직"으로 그린다.
export function collectedRows(
  collected: PlanCollected,
): Array<[label: string, value: string | null]> {
  const period = collected.startDate ? periodLabel(collected.startDate, collected.endDate) : null

  return [
    ['행사 유형', collected.eventType && EVENT_TYPE_LABEL[collected.eventType]],
    ['일정', period || null],
    ['예상 인원', collected.headcount ? `${collected.headcount}명` : null],
    ['예산 상한', collected.budgetTotal ? formatCurrency(collected.budgetTotal) : null],
    ['장소 후보', collected.locationCandidates?.join(' · ') || null],
  ]
}

// 명세: RULE 경고는 서버가 문장을 주지 않는다. code + params로 FE가 조립하고,
// 모르는 code면 debugMessage를 그대로 쓴다.
const WARNING_MESSAGE: Record<string, (params: Record<string, string | number>) => string> = {
  SCHEDULE_GAP: (p) =>
    `${p.fromStep}(${formatMonthDay(String(p.fromDate))})과 ${p.toStep}(${formatMonthDay(String(p.toDate))}) 사이가 ${p.gapDays}일 비어 있습니다. 인원 변동이 생기면 반영할 단계가 없습니다.`,
  BUDGET_EXCEEDED: (p) =>
    `계획한 지출이 예산 상한을 ${formatCurrency(Number(p.excess ?? 0))} 넘습니다.`,
  PREP_TIME_SHORT: (p) => `준비 기간이 ${p.days}일뿐이라 일정이 밀리면 만회할 여유가 없습니다.`,
  SCHEDULE_CONFLICT: (p) => `${p.stepA}과 ${p.stepB}의 일정이 겹칩니다.`,
  MINIMUM_HEADCOUNT_VIOLATED: (p) =>
    `예상 인원 ${p.headcount}명은 최소 인원 ${p.minimum}명에 못 미칩니다.`,
}

export function warningMessage(warning: PlanWarning): string {
  if (warning.source === 'AI') return warning.message ?? ''
  const compose = warning.code ? WARNING_MESSAGE[warning.code] : undefined
  return compose ? compose(warning.params ?? {}) : (warning.debugMessage ?? '')
}

// 명세에 이름이 나온 건 ADD_CHECKPOINT 하나뿐이다. 모르는 값이면 버튼을 그리지 않는다.
const SUGGESTION_LABEL: Record<string, string> = {
  ADD_CHECKPOINT: '중간 점검 단계 넣기',
}

export function suggestionLabel(suggestion?: string): string | null {
  return suggestion ? (SUGGESTION_LABEL[suggestion] ?? null) : null
}
