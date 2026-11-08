// 메인 토리 데스크 시안(?demo)의 예시 데이터와 예시 답.
// 행사·단계는 행사 화면 시연 데이터(DEMO_EVENTS, DEMO_STEPS)를 그대로 써서 화면끼리 숫자가 맞게 한다.
// 서버가 붙으면 이 파일은 시연에만 남고, 실제 답은 토리 API가 준다.
import { DEMO_EVENTS, DEMO_STEPS } from '@/features/events/mock'
import type { EventSummary } from '@/features/events/types'
import type {
  Briefing,
  EventStatusData,
  RelatedRow,
  TaskRow,
  ToriDeskReply,
} from '@/features/dashboard/desk'
import { shortDay } from '@/features/dashboard/desk'

// 오늘에서 n일 뒤 "YYYY-MM-DD"(행사 시연 데이터와 같은 기준)
function day(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return d.toLocaleDateString('en-CA')
}

const MT = DEMO_EVENTS.find((event) => event.id === 'evt_9f2c8a')!
const HACKATHON = DEMO_EVENTS.find((event) => event.id === 'evt_c41d07')!
const ACTIVE_EVENTS = DEMO_EVENTS.filter(
  (event) => event.status === 'ON_GOING' || event.status === 'PLANNING',
)
const MEETING = `${shortDay(day(-3))} 정기 회의`
const eventHref = (event: EventSummary) => `/events/${event.id}?demo`

function stepsOf(event: EventSummary) {
  const steps = DEMO_STEPS[event.id] ?? []
  const index = steps.findIndex((step) => step.state === 'CURRENT')
  const toStep = (step: (typeof steps)[number]) => ({
    name: step.name,
    dueDate: step.deadline?.slice(0, 10) ?? null,
  })
  const current = index >= 0 ? steps[index] : undefined
  return {
    current: current ? toStep(current) : null,
    next: steps.slice(index + 1, index + 3).map(toStep),
    approvals: (current?.remainingActions ?? [])
      .filter((action) => action.approveNeeded && action.status === 'PENDING')
      .slice(0, event.pendingApprovalCount)
      .map((action) => action.title),
  }
}

const STATUS: Record<string, EventStatusData> = {
  [MT.id]: { event: MT, ...stepsOf(MT), budget: 1_440_000, spent: 612_000 },
  [HACKATHON.id]: { event: HACKATHON, ...stepsOf(HACKATHON), budget: 800_000, spent: 150_000 },
}

const MY_TASKS: TaskRow[] = [
  { id: 'tsk_1', title: '10월 회계 장부 정리', assignee: '나', dueDate: day(0) },
  { id: 'tsk_2', title: 'MT 버스 견적 2곳 받기', assignee: '나', dueDate: day(1) },
  { id: 'tsk_3', title: '해커톤 후원사 연락처 정리', assignee: '나', dueDate: day(5) },
]

const MEETING_TASKS: TaskRow[] = [
  { id: 'tsk_1', title: '10월 회계 장부 정리', assignee: '나', dueDate: day(0) },
  { id: 'tsk_2', title: 'MT 버스 견적 2곳 받기', assignee: '나', dueDate: day(1) },
  { id: 'tsk_4', title: 'MT 숙소 환불 규정 확인', assignee: '김민지', dueDate: day(-1) },
  { id: 'tsk_5', title: '해커톤 심사위원 후보 3명 추리기', assignee: '이도현', dueDate: day(6) },
]

const mtSteps = stepsOf(MT)
const hackathonSteps = stepsOf(HACKATHON)

// 서버가 급한 순서로 정렬해 준다고 본다. 오늘 마감 → 승인 대기 → 내일 → 그 뒤.
export const DEMO_BRIEFING: Briefing = {
  items: [
    {
      id: 'b1',
      kind: 'task',
      title: MY_TASKS[0].title,
      source: MEETING,
      dueDate: MY_TASKS[0].dueDate,
      href: '/meetings',
      ask: `${MEETING}에서 정한 할 일`,
    },
    {
      id: 'b2',
      kind: 'approval',
      title: mtSteps.approvals[0],
      source: `${MT.title} | ${MT.currentStepName} 단계`,
      dueDate: null,
      moreCount: mtSteps.approvals.length - 1,
      href: eventHref(MT),
      ask: '승인 기다리는 거 보여줘',
    },
    {
      id: 'b3',
      kind: 'approval',
      title: hackathonSteps.approvals[0],
      source: `${HACKATHON.title} | ${HACKATHON.currentStepName} 단계`,
      dueDate: null,
      href: eventHref(HACKATHON),
      ask: '승인 기다리는 거 보여줘',
    },
    {
      id: 'b4',
      kind: 'task',
      title: MY_TASKS[1].title,
      source: MEETING,
      dueDate: MY_TASKS[1].dueDate,
      href: '/meetings',
      ask: '이번 주 내 할 일',
    },
    {
      id: 'b5',
      kind: 'deadline',
      title: `${mtSteps.current!.name} 단계 마감`,
      source: MT.title,
      dueDate: mtSteps.current!.dueDate,
      href: eventHref(MT),
      ask: `${MT.title} 어디까지 됐어?`,
    },
    {
      id: 'b6',
      kind: 'deadline',
      title: `${hackathonSteps.current!.name} 단계 마감`,
      source: HACKATHON.title,
      dueDate: hackathonSteps.current!.dueDate,
      href: eventHref(HACKATHON),
      ask: `${HACKATHON.title} 어디까지 됐어?`,
    },
  ],
  events: ACTIVE_EVENTS,
}

export const DEMO_STARTERS = [
  `${MT.title} 어디까지 됐어?`,
  '승인 기다리는 거 보여줘',
  `${MEETING}에서 정한 할 일`,
  '진행 중인 행사 뭐 있어?',
]

const PENDING_SENDS: RelatedRow[] = mtSteps.approvals.slice(0, 2).map((title) => ({
  title,
  source: MT.title,
  status: '승인 대기',
  href: eventHref(MT),
  action: '승인하러 가기',
}))

function findEvent(text: string): EventSummary | undefined {
  if (/해커톤/.test(text)) return HACKATHON
  if (/mt|엠티/i.test(text)) return MT
  return undefined
}

// 계획을 시작하자는 말에서 넘겨줄 조건을 뽑는다. 시안이라 단순한 규칙만 쓴다.
function handoffConditions(message: string) {
  const name = message.match(
    /([가-힣0-9]+\s?(?:MT|엠티|해커톤|축제|워크샵|체육대회|개강총회))/i,
  )?.[1]
  const people = message.match(/(\d+)\s?명/)?.[1]
  const when = message.match(/(\d+월\s?(?:초|중순|말)?|다음\s?달|이번\s?달)/)?.[1]
  return [
    { label: '행사', value: name ?? '이름 미정' },
    { label: '시기', value: when ?? '미정' },
    { label: '인원', value: people ? `${people}명` : '미정' },
  ]
}

export function demoReply(message: string): ToriDeskReply {
  const text = message.replace(/\s/g, '')
  const event = findEvent(text)

  if (/챙길|확인할일/.test(text)) {
    const label = { deadline: '단계 마감', approval: '승인 대기', task: '내 할 일' }
    return {
      reply: `오늘 확인할 일 ${DEMO_BRIEFING.items.length}개를 급한 순서로 모았어요.`,
      card: {
        type: 'tasks',
        title: '확인할 일',
        tasks: DEMO_BRIEFING.items.map((item) => ({
          id: item.id,
          title: item.moreCount ? `${item.title} 외 ${item.moreCount}건` : item.title,
          assignee: label[item.kind],
          dueDate: item.dueDate,
        })),
        footer: { label: '행사 목록에서 보기', href: '/events?demo' },
      },
      suggestions: ['승인 기다리는 거 보여줘', `${MT.title} 어디까지 됐어?`],
    }
  }

  if (/계획.*(짜|시작|만들|세우|잡)|(짜|만들|세우|잡).*계획|계획하/.test(text)) {
    const conditions = handoffConditions(message)
    return {
      reply:
        '행사 계획은 계획 화면에서 토리와 이어서 정해요. 지금 말씀하신 내용을 들고 넘어갈게요.',
      card: {
        type: 'handoff',
        title: `${conditions[0].value === '이름 미정' ? '새 행사' : conditions[0].value} 계획`,
        conditions,
        href: '/planning?demo',
      },
    }
  }

  if (/보내|발송|문자|이체|송금|올려줘|승인해/.test(text)) {
    return {
      reply:
        '발송과 이체는 제가 바로 하지 않아요. 행사 상세에서 운영진이 승인하면 그때 나가요. 지금 승인을 기다리는 발송이 있어요.',
      card: { type: 'related', title: '승인을 기다리는 발송', rows: PENDING_SENDS },
      suggestions: ['승인 기다리는 거 전부 보여줘', `${MT.title} 어디까지 됐어?`],
    }
  }

  if (/승인/.test(text)) {
    const groups = [MT, HACKATHON]
      .map((item) => ({
        eventTitle: item.title,
        href: eventHref(item),
        titles: STATUS[item.id].approvals,
      }))
      .filter((group) => group.titles.length > 0)
    const total = groups.reduce((sum, group) => sum + group.titles.length, 0)
    return {
      reply: `승인을 기다리는 일이 ${total}건 있어요. 행사 상세에서 내용을 보고 승인할 수 있어요.`,
      card: { type: 'approvals', groups },
      suggestions: [`${MT.title} 어디까지 됐어?`, '이번 주 내 할 일'],
    }
  }

  if (/회의/.test(text) && /할일|정한|결정|나온/.test(text)) {
    return {
      reply: `${MEETING}에서 확정한 할 일이 ${MEETING_TASKS.length}개예요. 마감이 지난 일이 1개 있어요.`,
      card: {
        type: 'tasks',
        title: `${MEETING}에서 정한 할 일`,
        tasks: MEETING_TASKS,
        footer: { label: '회의 기록 보기', href: '/meetings' },
      },
      suggestions: ['이번 주 내 할 일', '승인 기다리는 거 보여줘'],
    }
  }

  if (/어디까지|현황|상황|얼마나|남았|예산|썼/.test(text)) {
    if (!event)
      return {
        reply: '어떤 행사를 볼까요? 진행 중인 행사는 두 개예요.',
        suggestions: [`${MT.title} 어디까지 됐어?`, `${HACKATHON.title} 어디까지 됐어?`],
      }
    const status = STATUS[event.id]
    return {
      // 행사 이름 뒤 조사는 받침에 따라 바뀌어 쓰지 않는다.
      reply: `${event.title}, 지금 ${status.current?.name} 단계를 진행하고 있어요. 승인을 기다리는 일이 ${status.approvals.length}건 있어요.`,
      card: { type: 'event_status', status },
      suggestions: [
        '승인 기다리는 거 보여줘',
        event.id === MT.id ? `${HACKATHON.title} 어디까지 됐어?` : `${MT.title} 어디까지 됐어?`,
      ],
    }
  }

  if (/행사/.test(text) && /뭐|목록|진행|있어|알려|보여/.test(text)) {
    const ongoing = ACTIVE_EVENTS.filter((item) => item.status === 'ON_GOING').length
    return {
      reply: `진행 중인 행사 ${ongoing}개, 계획 중인 행사 ${ACTIVE_EVENTS.length - ongoing}개예요.`,
      card: { type: 'events', events: ACTIVE_EVENTS },
      suggestions: [`${MT.title} 어디까지 됐어?`, '승인 기다리는 거 보여줘'],
    }
  }

  if (/할일|마감|이번주|오늘/.test(text)) {
    return {
      reply: `이번 주에 내 계정으로 배정된 할 일이 ${MY_TASKS.length}개예요. 오늘 마감인 일이 1개 있어요.`,
      card: {
        type: 'tasks',
        title: '이번 주 내 할 일',
        tasks: MY_TASKS,
        footer: { label: '회의에서 전체 보기', href: '/meetings' },
      },
      suggestions: [`${MEETING}에서 정한 할 일`, '승인 기다리는 거 보여줘'],
    }
  }

  if (/너|토리|뭘할|뭐할|도와|할수있/.test(text)) {
    return {
      reply:
        '저는 행사 진행 상황, 승인을 기다리는 일, 확정된 할 일을 모아 보여 드려요. 동아리 자료에서 지난 기록도 찾아 드리고, 계획은 계획 화면으로 이어 드려요.',
      suggestions: DEMO_STARTERS.slice(0, 3),
    }
  }

  return {
    reply:
      '이 질문은 아직 제가 답하기 어려워요. 행사 진행 상황, 승인 대기, 할 일, 동아리 자료라면 바로 찾아 드릴 수 있어요.',
    suggestions: DEMO_STARTERS.slice(0, 3),
  }
}

// 시안에서도 답을 기다리는 모습이 보이도록 잠깐 늦춘다.
export function demoRespond(message: string): Promise<ToriDeskReply> {
  return new Promise((resolve) => setTimeout(() => resolve(demoReply(message)), 900))
}
