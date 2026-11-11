// 메인 토리 데스크 시안(?demo)의 예시 데이터와 예시 답. 모양은 서버 응답(브리핑 API, 토리 답의 card)과 같다.
// 행사·단계는 행사 화면 시연 데이터(DEMO_EVENTS, DEMO_STEPS)를 그대로 써서 화면끼리 숫자가 맞게 한다.
import { DEMO_EVENTS, DEMO_STEPS } from '@/features/events/mock'
import type { EventSummary } from '@/features/events/types'
import type {
  Briefing,
  BriefingItem,
  MyTaskItem,
  ServerCard,
  ToriDeskReply,
} from '@/features/dashboard/desk'
import { shortDay } from '@/features/dashboard/desk'
import type { components } from '@/shared/api/schema'

type S = components['schemas']
type CardOf<T extends ServerCard['type']> = Extract<ServerCard, { type: T }>

// 오늘에서 n일 뒤 "YYYY-MM-DD"(행사 시연 데이터와 같은 기준)
function day(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return d.toLocaleDateString('en-CA')
}

// 시연 행사에는 서버 행사 카드의 결제·예산 칸이 없다.
const asEventOut = (event: EventSummary): S['EventOut'] => ({ ...event, payment: null, budget: null })

const MT = DEMO_EVENTS.find((event) => event.id === 'evt_9f2c8a')!
const HACKATHON = DEMO_EVENTS.find((event) => event.id === 'evt_c41d07')!
const ACTIVE_EVENTS = DEMO_EVENTS.filter(
  (event) => event.status === 'ON_GOING' || event.status === 'PLANNING',
)
const MEETING_ID = 'mtg_demo'
const MEETING = `${shortDay(day(-3))} 정기 회의`

function stepsOf(event: EventSummary) {
  const steps = DEMO_STEPS[event.id] ?? []
  const index = steps.findIndex((step) => step.state === 'CURRENT')
  const toStep = (step: (typeof steps)[number]) => ({
    name: step.name,
    dueDate: step.deadline?.slice(0, 10) ?? null,
  })
  const current = index >= 0 ? steps[index] : undefined
  const approvals = (current?.remainingActions ?? [])
    .filter((action) => action.approveNeeded && action.status === 'PENDING')
    .slice(0, event.pendingApprovalCount)
  return {
    current: current ? toStep(current) : null,
    next: steps.slice(index + 1, index + 3).map(toStep),
    approvals: approvals.map((action) => ({
      id: action.id,
      title: action.title,
      stepName: current?.name ?? null,
      dueDate: current?.deadline?.slice(0, 10) ?? null,
    })),
  }
}

const mtSteps = stepsOf(MT)
const hackathonSteps = stepsOf(HACKATHON)

function statusCard(
  event: EventSummary,
  steps: ReturnType<typeof stepsOf>,
  budget: number,
  spent: number,
): CardOf<'event_status'> {
  return {
    type: 'event_status',
    event: asEventOut(event),
    currentStep: steps.current,
    nextSteps: steps.next,
    approvals: steps.approvals.map((action) => action.title),
    approvalCount: steps.approvals.length,
    budget,
    spent,
  }
}

const STATUS: Record<string, CardOf<'event_status'>> = {
  [MT.id]: statusCard(MT, mtSteps, 1_440_000, 612_000),
  [HACKATHON.id]: statusCard(HACKATHON, hackathonSteps, 800_000, 150_000),
}

const APPROVALS: CardOf<'approvals'> = {
  type: 'approvals',
  groups: [
    { event: MT, steps: mtSteps },
    { event: HACKATHON, steps: hackathonSteps },
  ]
    .filter(({ steps }) => steps.approvals.length > 0)
    .map(({ event, steps }) => ({
      eventId: event.id,
      eventTitle: event.title,
      actions: steps.approvals,
    })),
}

const task = (id: string, title: string, assigneeName: string, due: number): MyTaskItem => ({
  id,
  title,
  kind: 'TASK',
  assigneeName,
  // 마감 시각은 한국 시간 그날 밤 11시 59분으로 둔다.
  dueAt: `${day(due)}T23:59:00+09:00`,
  scheduledAt: null,
})

const MY_TASKS: MyTaskItem[] = [
  task('tsk_1', '10월 회계 장부 정리', '나', 0),
  task('tsk_2', 'MT 버스 견적 2곳 받기', '나', 1),
  task('tsk_3', '해커톤 후원사 연락처 정리', '나', 5),
]

const MEETING_TASKS: CardOf<'tasks'> = {
  type: 'tasks',
  title: `${MEETING}에서 정한 할 일`,
  meetingId: MEETING_ID,
  hasMore: false,
  tasks: [
    { id: 'tsk_1', title: '10월 회계 장부 정리', kind: 'TASK', assigneeName: '나', dueDate: day(0) },
    { id: 'tsk_2', title: 'MT 버스 견적 2곳 받기', kind: 'TASK', assigneeName: '나', dueDate: day(1) },
    { id: 'tsk_4', title: 'MT 숙소 환불 규정 확인', kind: 'TASK', assigneeName: '김민지', dueDate: day(-1) },
    { id: 'tsk_5', title: '해커톤 심사위원 후보 3명 추리기', kind: 'TASK', assigneeName: '이도현', dueDate: day(6) },
  ],
}

const statusAsk = (event: EventSummary) => `${event.title} 어디까지 됐어?`
const APPROVAL_ASK = '승인 기다리는 거 보여줘'

// 서버가 급한 순서로 정렬해 준다고 본다. 오늘 마감 → 승인 대기 → 내일 → 그 뒤.
type DemoItem = Omit<BriefingItem, 'moreCount'> & { moreCount?: number }

export const DEMO_BRIEFING: Briefing = {
  items: ([
    {
      id: 'b1',
      kind: 'task',
      title: MY_TASKS[0].title,
      source: MEETING,
      dueDate: day(0),
      taskId: MY_TASKS[0].id,
      meetingId: MEETING_ID,
      ask: `${MEETING}에서 정한 할 일`,
    },
    {
      id: 'b2',
      kind: 'approval',
      title: mtSteps.approvals[0].title,
      source: `${MT.title} | ${MT.currentStepName} 단계`,
      dueDate: null,
      moreCount: mtSteps.approvals.length - 1,
      eventId: MT.id,
      ask: APPROVAL_ASK,
    },
    {
      id: 'b3',
      kind: 'approval',
      title: hackathonSteps.approvals[0].title,
      source: `${HACKATHON.title} | ${HACKATHON.currentStepName} 단계`,
      dueDate: null,
      eventId: HACKATHON.id,
      ask: APPROVAL_ASK,
    },
    {
      id: 'b4',
      kind: 'task',
      title: MY_TASKS[1].title,
      source: MEETING,
      dueDate: day(1),
      taskId: MY_TASKS[1].id,
      meetingId: MEETING_ID,
      ask: '이번 주 내 할 일',
    },
    {
      id: 'b5',
      kind: 'deadline',
      title: `${mtSteps.current!.name} 단계 마감`,
      source: MT.title,
      dueDate: mtSteps.current!.dueDate,
      eventId: MT.id,
      ask: statusAsk(MT),
    },
    {
      id: 'b6',
      kind: 'deadline',
      title: `${hackathonSteps.current!.name} 단계 마감`,
      source: HACKATHON.title,
      dueDate: hackathonSteps.current!.dueDate,
      eventId: HACKATHON.id,
      ask: statusAsk(HACKATHON),
    },
  ] satisfies DemoItem[]).map((item) => ({ moreCount: 0, ...item })),
  events: ACTIVE_EVENTS,
}

export const DEMO_STARTERS = [
  statusAsk(MT),
  APPROVAL_ASK,
  `${MEETING}에서 정한 할 일`,
  '진행 중인 행사 뭐 있어?',
]

function findEvent(text: string): EventSummary | undefined {
  if (/해커톤/.test(text)) return HACKATHON
  if (/mt|엠티/i.test(text)) return MT
  return undefined
}

const approvalTotal = APPROVALS.groups.reduce((sum, group) => sum + group.actions.length, 0)

// 시안이라 단순한 규칙으로 서버 답과 같은 모양을 만든다.
export function demoReply(message: string): ToriDeskReply {
  const text = message.replace(/\s/g, '')
  const event = findEvent(text)

  if (/챙길|확인할일/.test(text)) {
    return {
      reply: `오늘 확인할 일 ${DEMO_BRIEFING.items.length}개를 급한 순서로 모았어요.`,
      card: { type: 'briefing', items: DEMO_BRIEFING.items },
      suggestions: [APPROVAL_ASK],
    }
  }

  if (/계획.*(짜|시작|만들|세우|잡)|(짜|만들|세우|잡).*계획|계획하/.test(text)) {
    return {
      reply:
        '행사 계획은 계획 화면에서 토리와 이어서 정해요. 지금 말씀하신 내용을 들고 넘어갈게요.',
      card: { type: 'handoff', message },
    }
  }

  if (/보내|발송|문자|이체|송금|올려줘|승인해/.test(text)) {
    return {
      reply: `발송, 승인, 이체는 제가 바로 하지 않아요. 행사 상세에서 운영진이 승인하면 그때 진행돼요. 지금 승인을 기다리는 일이 ${approvalTotal}건 있어요.`,
      card: APPROVALS,
      suggestions: [statusAsk(MT), statusAsk(HACKATHON)],
    }
  }

  if (/지출|장부|회계/.test(text) && /기록|적어|남겨|올려/.test(text)) {
    return {
      reply: '지출 기록은 제가 바로 하지 않아요. 회계 화면에서 남길 수 있어요.',
      navigation: '/accounting',
    }
  }

  if (/승인/.test(text)) {
    return {
      reply: `승인을 기다리는 일이 ${approvalTotal}건 있어요. 행사 상세에서 내용을 보고 승인할 수 있어요.`,
      card: APPROVALS,
      suggestions: [statusAsk(MT), statusAsk(HACKATHON)],
    }
  }

  if (/회의/.test(text) && /할일|정한|결정|나온/.test(text)) {
    return {
      reply: `${MEETING}에서 확정한 할 일이 ${MEETING_TASKS.tasks.length}개 있어요. 마감이 지난 일이 1개 있어요.`,
      card: MEETING_TASKS,
    }
  }

  if (/어디까지|현황|상황|얼마나|남았|예산|썼/.test(text)) {
    if (!event)
      return {
        reply: '어느 행사요? 맞는 행사가 2개 있어요.',
        suggestions: [statusAsk(MT), statusAsk(HACKATHON)],
      }
    const card = STATUS[event.id]
    return {
      reply: `${event.title}, 지금 ${card.currentStep?.name} 단계를 진행하고 있어요. 승인을 기다리는 일이 ${card.approvalCount}건 있어요.`,
      card,
      suggestions: [APPROVAL_ASK, statusAsk(event.id === MT.id ? HACKATHON : MT)],
    }
  }

  if (/행사/.test(text) && /뭐|목록|진행|있어|알려|보여/.test(text)) {
    return {
      reply: `행사 ${ACTIVE_EVENTS.length}개예요.`,
      card: { type: 'events', events: ACTIVE_EVENTS.map(asEventOut), total: ACTIVE_EVENTS.length },
    }
  }

  if (/할일|마감|이번주|오늘/.test(text)) {
    return {
      reply: `내 할 일이 ${MY_TASKS.length}개 있어요. 오늘 마감인 일이 1개 있어요.`,
      card: {
        type: 'my_tasks',
        tasks: {
          items: MY_TASKS,
          hasMore: false,
          scope: 'self',
          kind: 'task',
          dateFrom: day(0),
          dateTo: day(6),
          timezone: 'Asia/Seoul',
        },
      },
    }
  }

  if (/너|토리|뭘할|뭐할|도와|할수있/.test(text)) {
    return {
      reply:
        '저는 동아리 운영진과 함께 일하는 친근한 도우미 토리예요. 행사 진행 상황, 승인을 기다리는 일, 확정된 할 일을 모아 보여 드리고, 동아리 자료에서 지난 기록도 찾아 드려요. 행사 계획은 계획 화면으로 이어 드려요.',
      suggestions: ['확인할 일 전부 보여줘', APPROVAL_ASK, statusAsk(MT)],
    }
  }

  return {
    reply:
      '이 질문은 아직 제가 답하기 어려워요. 행사 진행 상황, 승인 대기, 할 일, 동아리 자료라면 바로 찾아 드릴 수 있어요.',
    suggestions: ['확인할 일 전부 보여줘', APPROVAL_ASK, statusAsk(MT)],
  }
}

// 시안에서도 답을 기다리는 모습이 보이도록 잠깐 늦춘다.
export function demoRespond(message: string): Promise<ToriDeskReply> {
  return new Promise((resolve) => setTimeout(() => resolve(demoReply(message)), 900))
}
