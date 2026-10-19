export interface OnboardingState {
  signedIn: boolean
  clubSelected: boolean
  guideEnabled: boolean
  teamName: string
  operatorName: string
  role: 'OWNER' | 'MANAGER'
  setupDone: boolean
  recordsAdded: boolean
  meetingCreated: boolean
  meetingTitle: string
  meetingPlayed: boolean
  saved: boolean
  candidate: {
    title: string
    assignee: string
    dueAt: string
    reminderAt: string
    recipient: string
  }
}

export const ONBOARDING_STORAGE_KEY = 'unyounghae_onboarding_preview_v2'
export const INITIAL_ONBOARDING: OnboardingState = {
  signedIn: false,
  clubSelected: false,
  guideEnabled: true,
  teamName: '온빛 캠퍼스 운영팀',
  operatorName: '김하늘',
  role: 'MANAGER',
  setupDone: false,
  recordsAdded: false,
  meetingCreated: false,
  meetingTitle: '가을 행사 준비 회의',
  meetingPlayed: false,
  saved: false,
  candidate: {
    title: '행사장 예약 확인',
    assignee: '김하늘',
    dueAt: '2026-10-23T16:00',
    reminderAt: '2026-10-23T15:30',
    recipient: '김하늘',
  },
}

function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}
const text = (value: unknown, fallback: string) => (typeof value === 'string' ? value : fallback)
const flag = (value: unknown, fallback: boolean) => (typeof value === 'boolean' ? value : fallback)

function normalize(value: unknown): OnboardingState {
  const input = object(value)
  const candidate = object(input.candidate)
  const initial = INITIAL_ONBOARDING
  return {
    signedIn: flag(input.signedIn, initial.signedIn),
    clubSelected: flag(input.clubSelected, initial.clubSelected),
    guideEnabled: flag(input.guideEnabled, initial.guideEnabled),
    teamName: text(input.teamName, initial.teamName),
    operatorName: text(input.operatorName, initial.operatorName),
    role: input.role === 'OWNER' || input.role === 'MANAGER' ? input.role : initial.role,
    setupDone: flag(input.setupDone, initial.setupDone),
    recordsAdded: flag(input.recordsAdded, initial.recordsAdded),
    meetingCreated: flag(input.meetingCreated, initial.meetingCreated),
    meetingTitle: text(input.meetingTitle, initial.meetingTitle),
    meetingPlayed: flag(input.meetingPlayed, initial.meetingPlayed),
    saved: flag(input.saved, initial.saved),
    candidate: {
      title: text(candidate.title, initial.candidate.title),
      assignee: text(candidate.assignee, initial.candidate.assignee),
      dueAt: text(candidate.dueAt, initial.candidate.dueAt),
      reminderAt: text(candidate.reminderAt, initial.candidate.reminderAt),
      recipient: text(candidate.recipient, initial.candidate.recipient),
    },
  }
}

export function loadOnboarding(): OnboardingState {
  try {
    const raw = localStorage.getItem(ONBOARDING_STORAGE_KEY)
    return normalize(raw === null ? null : JSON.parse(raw))
  } catch {
    return normalize(null)
  }
}

export function saveOnboarding(state: OnboardingState): OnboardingState {
  const next = normalize(state)
  try {
    localStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(next))
  } catch {
    // 저장소 권한이 없어도 현재 화면의 목업 진행은 계속할 수 있다.
  }
  return next
}

export function resetOnboarding(): OnboardingState {
  try {
    localStorage.removeItem(ONBOARDING_STORAGE_KEY)
  } catch {
    // 다른 앱/인증 키는 건드리지 않고 화면 상태만 초기화한다.
  }
  return normalize(null)
}
