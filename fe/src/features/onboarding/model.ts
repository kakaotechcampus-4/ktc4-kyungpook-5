export interface PreviewTask {
  id: string
  title: string
  assignee: string
  dueAt: string
  reminderAt: string
  recipient: string
  description: string
}

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
  candidates: [PreviewTask, PreviewTask]
  savedItems: PreviewTask[]
  selectedCandidateId: string
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
  candidates: [
    {
      id: 'preview-venue',
      title: '행사장 예약 확인',
      assignee: '김하늘',
      dueAt: '2026-10-23T16:00',
      reminderAt: '2026-10-23T15:30',
      recipient: '김하늘',
      description: '',
    },
    {
      id: 'preview-supplies',
      title: '행사 운영 물품 준비',
      assignee: '박지훈',
      dueAt: '2026-10-23T18:00',
      reminderAt: '2026-10-23T17:30',
      recipient: '박지훈',
      description: '',
    },
  ],
  savedItems: [],
  selectedCandidateId: 'preview-venue',
}

function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}
const text = (value: unknown, fallback: string) => (typeof value === 'string' ? value : fallback)
const flag = (value: unknown, fallback: boolean) => (typeof value === 'boolean' ? value : fallback)

function normalizeTask(value: unknown, fallback: PreviewTask): PreviewTask {
  const input = object(value)
  return {
    id: fallback.id,
    title: text(input.title, fallback.title),
    assignee: text(input.assignee, fallback.assignee),
    dueAt: text(input.dueAt, fallback.dueAt),
    reminderAt: text(input.reminderAt, fallback.reminderAt),
    recipient: text(input.recipient, fallback.recipient),
    // 빈 메모와 줄바꿈은 사용자가 입력한 그대로 보존한다.
    description: text(input.description, fallback.description),
  }
}

function normalize(value: unknown): OnboardingState {
  const input = object(value)
  const initial = INITIAL_ONBOARDING
  const drafts = new Map(
    (Array.isArray(input.candidates) ? input.candidates : []).map((item) => {
      const draft = object(item)
      return [draft.id, draft] as const
    }),
  )
  const candidates: OnboardingState['candidates'] = [
    normalizeTask(drafts.get(initial.candidates[0].id) ?? input.candidate, initial.candidates[0]),
    normalizeTask(drafts.get(initial.candidates[1].id), initial.candidates[1]),
  ]
  const snapshots = new Map<string, PreviewTask>()
  if (Array.isArray(input.savedItems)) {
    for (const item of input.savedItems) {
      const saved = object(item)
      const fallback = initial.candidates.find((candidate) => candidate.id === saved.id)
      if (fallback) snapshots.set(fallback.id, normalizeTask(saved, fallback))
    }
  } else if (input.saved === true) {
    // 이전 v2의 단일 후보 저장을 첫 항목의 독립된 저장본으로 이어받는다.
    snapshots.set(candidates[0].id, { ...candidates[0] })
  }
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
    candidates,
    savedItems: Array.from(snapshots.values()),
    selectedCandidateId: candidates.some((candidate) => candidate.id === input.selectedCandidateId)
      ? (input.selectedCandidateId as string)
      : initial.selectedCandidateId,
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

export function selectPreviewCandidate(state: OnboardingState, id: string): OnboardingState {
  return state.candidates.some((candidate) => candidate.id === id)
    ? { ...state, selectedCandidateId: id }
    : state
}

export function updatePreviewCandidate(
  state: OnboardingState,
  id: string,
  patch: Partial<Omit<PreviewTask, 'id'>>,
): OnboardingState {
  if (!state.candidates.some((candidate) => candidate.id === id)) return state
  return {
    ...state,
    candidates: state.candidates.map((candidate) =>
      candidate.id === id ? normalizeTask({ ...candidate, ...patch }, candidate) : candidate,
    ) as OnboardingState['candidates'],
  }
}

export function savePreviewCandidate(state: OnboardingState, id: string): OnboardingState {
  const candidate = state.candidates.find((item) => item.id === id)
  if (!candidate) return state
  const snapshot = { ...candidate }
  return {
    ...state,
    savedItems: state.savedItems.some((item) => item.id === id)
      ? state.savedItems.map((item) => (item.id === id ? snapshot : item))
      : [...state.savedItems, snapshot],
  }
}
