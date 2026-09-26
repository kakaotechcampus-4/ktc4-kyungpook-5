// usePlanning... 커스텀 훅. 컴포넌트는 반드시 이 훅을 거쳐 서버 상태에 접근한다.
//
// BE에 계획 API가 아직 하나도 없어서 M1·L2·R1과 같이 목업으로만 움직인다. 서버 호출은
// api.ts에 명세대로 준비해 뒀고, 엔드포인트가 생기는 것부터 아래 함수 안을
// 그 호출 + 재조회로 갈아끼우면 된다.
import { useState } from 'react'
import * as planningApi from '@/features/planning/api'
import type {
  DraftStage,
  EventPlan,
  PlanChatTurn,
  PlanCollected,
  PlanStep,
  StepPatch,
} from '@/features/planning/types'

interface PlanningState {
  eventId: string
  title: string
  // PATCH /events/{eventId} 가 갱신하는 saved_at. 없으면 "아직 저장되지 않음".
  savedAt: string | null
  stage: DraftStage
  turns: PlanChatTurn[]
  collected: PlanCollected
  readyToGenerate: boolean
  // 2단계 데이터. plan:generate 전까지는 없다.
  plan: EventPlan | null
}

function freshState(): PlanningState {
  return {
    eventId: planningApi.NEW_PLAN_ID,
    title: '새 행사',
    savedAt: null,
    stage: 'CHAT',
    turns: [planningApi.getGreetingMock()],
    collected: planningApi.getEmptyCollectedMock(),
    readyToGenerate: false,
    plan: null,
  }
}

// 시안이 그린 "대화가 어느 정도 진행된" 상태. 처음 들어오면 이 모습이다.
function seededState(): PlanningState {
  return {
    ...freshState(),
    turns: planningApi.getConversationMock(),
    collected: planningApi.getCollectedMock(),
    readyToGenerate: true,
  }
}

function draftState(draftId: string): PlanningState {
  const draft = planningApi.getDraftsMock().find((item) => item.id === draftId)
  if (!draft) return seededState()

  return {
    ...seededState(),
    eventId: draft.id,
    title: draft.title,
    savedAt: draft.savedAt,
    stage: draft.stage,
    // 목업 계획은 한 벌뿐이라 제목만 그 초안 것으로 바꿔 둔다.
    plan: draft.stage === 'FLOW' ? { ...planningApi.getPlanMock(), title: draft.title } : null,
  }
}

export function usePlanning(eventId?: string) {
  const [state, setState] = useState<PlanningState>(() =>
    eventId ? draftState(eventId) : seededState(),
  )
  // plan:generate는 수십 초 걸릴 수 있어 대기 화면이 필요하다(명세).
  const [generating, setGenerating] = useState(false)
  const [pending, setPending] = useState(false)

  // TODO: POST /conversations/{conversationId}/messages
  function ask(content: string) {
    const text = content.trim()
    if (!text || pending) return

    setState((prev) => ({
      ...prev,
      turns: [
        ...prev.turns,
        {
          id: `msg_${Date.now()}`,
          role: 'USER',
          content: text,
          createdAt: new Date().toISOString(),
        },
      ],
    }))
    setPending(true)

    // 답을 기다리는 상태도 화면에 있어야 해서 한 박자 뒤에 목업을 붙인다.
    window.setTimeout(() => {
      setState((prev) => ({
        ...prev,
        turns: [
          ...prev.turns,
          {
            id: `msg_${Date.now()}`,
            role: 'ASSISTANT',
            content: '반영했습니다. 더 고칠 게 없으면 다음 단계로 넘어갈게요.',
            createdAt: new Date().toISOString(),
          },
        ],
        // 실제로는 서버가 collected를 다시 채워 준다. 목업이라 여기서는 그대로 둔다.
        readyToGenerate: true,
      }))
      setPending(false)
    }, 400)
  }

  // TODO: POST /events/{eventId}/plan:generate
  function generate() {
    setGenerating(true)
    window.setTimeout(() => {
      setState((prev) => ({ ...prev, stage: 'FLOW', plan: planningApi.getPlanMock() }))
      setGenerating(false)
    }, 900)
  }

  function backToChat() {
    setState((prev) => ({ ...prev, stage: 'CHAT' }))
  }

  // TODO: PATCH /events/{eventId} — saved_at을 서버가 찍어 준다.
  function save() {
    setState((prev) => ({ ...prev, savedAt: new Date().toISOString() }))
  }

  // TODO: POST /events — 새 Event와 Conversation을 다시 만든다.
  function restart() {
    if (!window.confirm('지금 대화를 버리고 처음부터 다시 시작할까요?')) return
    setState(freshState())
  }

  // TODO: GET /conversations/{conversationId}/messages
  function resumeDraft(draftId: string) {
    if (!window.confirm('불러오면 지금 대화는 사라집니다. 계속할까요?')) return
    setState(draftState(draftId))
  }

  // TODO: PATCH /events/{eventId}/steps/{stepId}
  function updateStep(stepId: string, patch: StepPatch) {
    setState((prev) => ({ ...prev, plan: prev.plan && patchStep(prev.plan, stepId, patch) }))
  }

  // 🔸 경고의 suggestion(ADD_CHECKPOINT)을 받을 엔드포인트가 명세에 없다. 단계 추가 API가
  // 없어서 지금은 화면에서만 끼워 넣는다. **확인 필요**
  function addCheckpoint(warningIndex: number) {
    setState((prev) => ({ ...prev, plan: prev.plan && insertCheckpoint(prev.plan, warningIndex) }))
  }

  return {
    ...state,
    drafts: planningApi.getDraftsMock(),
    generating,
    pending,
    ask,
    generate,
    backToChat,
    save,
    restart,
    resumeDraft,
    updateStep,
    addCheckpoint,
  }
}

function patchStep(plan: EventPlan, stepId: string, patch: StepPatch): EventPlan {
  return {
    ...plan,
    phases: plan.phases.map((phase) => ({
      ...phase,
      steps: phase.steps.map((step) => (step.id === stepId ? { ...step, ...patch } : step)),
    })),
  }
}

// 비어 있는 구간 뒤쪽 묶음 끝에 점검 단계를 하나 붙이고, 그 경고를 지운다.
function insertCheckpoint(plan: EventPlan, warningIndex: number): EventPlan {
  const target = plan.phases.findIndex((phase) => phase.phase === 'RECRUITING')
  if (target < 0) return plan

  const steps = plan.phases[target].steps
  const last = steps[steps.length - 1]
  const checkpoint: PlanStep = {
    id: `stp_new_${Date.now()}`,
    // stepOrder는 서버가 10·20·30…으로 다시 부여한다(명세 steps:reorder).
    stepOrder: (last?.stepOrder ?? 0) + 5,
    phase: 'RECRUITING',
    name: '중간 점검',
    actor: 'MANUAL',
    startedTime: '2026-03-16T00:00:00Z',
    deadline: null,
    actions: [],
  }

  return {
    ...plan,
    phases: plan.phases.map((phase, index) =>
      index === target ? { ...phase, steps: [...phase.steps, checkpoint] } : phase,
    ),
    summary: {
      ...plan.summary,
      totalSteps: plan.summary.totalSteps + 1,
      countByActor: {
        ...plan.summary.countByActor,
        MANUAL: (plan.summary.countByActor.MANUAL ?? 0) + 1,
      },
    },
    warnings: plan.warnings.filter((_, index) => index !== warningIndex),
  }
}
