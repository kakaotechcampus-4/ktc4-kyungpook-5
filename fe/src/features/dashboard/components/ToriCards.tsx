// 토리 답 아래에 붙는 카드. 줄글로 늘어놓던 목록을 화면에서 바로 읽고 눌러 이동할 수 있게 한다.
// 모든 카드는 같은 틀(머리 | 본문 줄 | 이동 링크)을 쓰고, 행사 화면의 칩과 진행 바를 그대로 쓴다.
// 카드의 숫자와 목록은 서버가 DB에서 읽은 값이다. 화면은 모양만 바꾼다.
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { cardStepText, showsProgress } from '@/features/events/cardModel'
import { SegmentBar } from '@/features/events/components/SegmentBar'
import type { EventSummary } from '@/features/events/types'
import { Chevron, ItemRow } from '@/features/dashboard/components/BriefingPanel'
import type { MyTasks, ServerCard, ToriCard } from '@/features/dashboard/desk'
import {
  daysUntil,
  dueLabel,
  eventPath,
  kstDay,
  meetingPath,
  shortDay,
  useDeskPath,
} from '@/features/dashboard/desk'
import { cn } from '@/shared/lib/cn'
import { formatCurrency, formatDateRange } from '@/shared/lib/format'
import { EVENT_STATUS_LABEL, EVENT_STATUS_TONE } from '@/shared/lib/labels'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'

type CardOf<T extends ServerCard['type']> = Extract<ServerCard, { type: T }>

function Frame({
  title,
  aside,
  footer,
  children,
}: {
  title: ReactNode
  aside?: ReactNode
  footer?: { label: string; href: string }
  children: ReactNode
}) {
  const path = useDeskPath()
  return (
    <div className="w-full overflow-hidden rounded-[20px] border border-line bg-card">
      <div className="flex items-center justify-between gap-3 px-[20px] pt-[14px] pb-[12px]">
        <div className="flex min-w-0 flex-wrap items-center gap-[8px]">{title}</div>
        {aside}
      </div>
      {children}
      {footer && (
        <Link
          to={path(footer.href)}
          className="flex items-center justify-between border-t border-line px-[20px] py-[11px] text-caption font-bold text-blue-700 transition-colors hover:bg-blue-50"
        >
          {footer.label}
          <Chevron />
        </Link>
      )}
    </div>
  )
}

function Due({ date }: { date: string | null | undefined }) {
  const late = !!date && daysUntil(date) < 0
  const today = !!date && daysUntil(date) === 0
  return (
    <span
      className={cn(
        'text-caption font-bold tabular-nums',
        late ? 'text-failed' : today ? 'text-pending' : 'text-ink2',
      )}
    >
      {date ? `${shortDay(date)} ${late ? '지남' : `(${dueLabel(date)})`}` : '기한 없음'}
    </span>
  )
}

function Dot() {
  return <span aria-hidden className="mt-[8px] size-[5px] shrink-0 rounded-full bg-pending" />
}

function EventsCard({ card }: { card: CardOf<'events'> }) {
  const path = useDeskPath()
  const events: EventSummary[] = card.events
  return (
    <Frame
      title={<h3 className="text-h3 text-ink">행사 {card.total}개</h3>}
      aside={
        card.total > events.length && (
          <span className="shrink-0 text-caption text-mute">앞의 {events.length}개</span>
        )
      }
      footer={{ label: '행사 목록에서 전체 보기', href: '/events' }}
    >
      <ul className="divide-y divide-line border-t border-line">
        {events.map((event) => {
          const meta = [
            formatDateRange(event.startDate, event.endDate),
            event.location,
            event.status === 'PLANNING'
              ? `초안 ${cardStepText(event)}`
              : event.currentStepName && `지금 ${event.currentStepName}`,
          ].filter(Boolean)
          return (
            <li key={event.id}>
              <Link
                to={path(eventPath(event.id))}
                className="group flex flex-col gap-[9px] px-[20px] py-[13px] transition-colors hover:bg-bg"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 flex-wrap items-center gap-[7px]">
                    <span className="truncate text-[15px] font-bold text-ink">{event.title}</span>
                    <Chip tone={EVENT_STATUS_TONE[event.status]} size="sm">
                      {EVENT_STATUS_LABEL[event.status]}
                    </Chip>
                    {event.pendingApprovalCount > 0 && (
                      <Chip tone="pending" size="sm">
                        승인 대기 {event.pendingApprovalCount}건
                      </Chip>
                    )}
                  </div>
                  <span className="flex shrink-0 items-center gap-[6px] text-caption font-bold tabular-nums text-blue-700">
                    {event.dday !== null ? (
                      `D-${event.dday}`
                    ) : (
                      <span className="text-mute">일정 미정</span>
                    )}
                    <Chevron className="text-soft group-hover:text-blue-600" />
                  </span>
                </div>
                <p className="truncate text-caption text-mute">{meta.join(' | ')}</p>
                {showsProgress(event.status) && (
                  <SegmentBar states={event.stepProgress.map((step) => step.state)} />
                )}
              </Link>
            </li>
          )
        })}
      </ul>
    </Frame>
  )
}

// 「확인할 일 전부 보여줘」. 브리핑 목록과 같은 줄을 전부 보인다.
function BriefingCard({ card }: { card: CardOf<'briefing'> }) {
  return (
    <Frame
      title={<h3 className="text-h3 text-ink">확인할 일</h3>}
      aside={<span className="shrink-0 text-caption text-mute">{card.items.length}개</span>}
    >
      <ul className="divide-y divide-line border-t border-line">
        {card.items.map((item, index) => (
          <ItemRow key={item.id} item={item} index={index} className="px-[20px] py-[12px]" />
        ))}
      </ul>
    </Frame>
  )
}

// 행사 현황. 단계 진행, 승인 대기, 다음 단계, 예산을 한 카드에 둔다. 줄 머리는 계획 조건 카드처럼 왼쪽에 둔다.
function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[72px_minmax(0,1fr)] gap-x-[14px] border-t border-line px-[20px] py-[13px]">
      <p className="pt-[1px] text-label text-mute">{label}</p>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

function EventStatusCard({ card }: { card: CardOf<'event_status'> }) {
  const { event, currentStep: current, nextSteps, approvals, approvalCount, spent } = card
  const budget = card.budget ?? null
  const ratio = budget ? Math.min(1, spent / budget) : 0
  const planning = event.status === 'PLANNING'
  return (
    <Frame
      title={
        <>
          <h3 className="text-h3 text-ink">{event.title}</h3>
          <Chip tone={EVENT_STATUS_TONE[event.status]} size="sm">
            {EVENT_STATUS_LABEL[event.status]}
          </Chip>
        </>
      }
      aside={
        event.dday !== null && (
          <span className="shrink-0 text-caption font-bold tabular-nums text-blue-700">
            D-{event.dday}
          </span>
        )
      }
      footer={
        planning
          ? {
              label: '계획 화면에서 보기',
              href: `/planning?${new URLSearchParams({ eventId: event.id })}`,
            }
          : { label: '행사 상세에서 보기', href: eventPath(event.id) }
      }
    >
      {showsProgress(event.status) && (
        <Section label="진행">
          <SegmentBar states={event.stepProgress.map((step) => step.state)} />
          <p className="mt-[9px] break-keep text-caption text-ink2">
            <span className="font-bold text-ink">{cardStepText(event)}단계</span>
            {current && (
              <>
                {' | 지금 '}
                <span className="font-bold text-ink">{current.name}</span>
                {current.dueDate && (
                  <span className="whitespace-nowrap"> | 마감 {dueLabel(current.dueDate)}</span>
                )}
              </>
            )}
          </p>
        </Section>
      )}
      {approvalCount > 0 && (
        <Section label={`승인 대기 ${approvalCount}`}>
          <ul className="flex flex-col gap-[6px]">
            {approvals.map((title, index) => (
              <li key={`${index}:${title}`} className="flex items-start gap-[8px] text-caption text-ink">
                <span aria-hidden className="mt-[7px] size-[5px] shrink-0 rounded-full bg-pending" />
                <span className="break-keep">{title}</span>
              </li>
            ))}
          </ul>
          {approvalCount > approvals.length && (
            <p className="mt-[6px] text-label text-mute">
              외 {approvalCount - approvals.length}건은 행사 상세에서 볼 수 있어요.
            </p>
          )}
        </Section>
      )}
      {nextSteps.length > 0 && (
        <Section label="다음 단계">
          <ul className="flex flex-col gap-[6px]">
            {nextSteps.map((step, index) => (
              <li key={`${index}:${step.name}`} className="flex justify-between gap-3 text-caption">
                <span className="text-ink">{step.name}</span>
                <span className="tabular-nums text-mute">
                  {step.dueDate ? shortDay(step.dueDate) : '미정'}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Section label="예산">
        {budget ? (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-[2px] text-caption whitespace-nowrap">
              <span>
                <span className="font-bold text-ink tabular-nums">{formatCurrency(spent)}</span>
                <span className="text-mute"> 썼어요</span>
              </span>
              <span className="tabular-nums text-mute">예산 {formatCurrency(budget)}</span>
            </div>
            <div className="mt-[8px] h-[7px] overflow-hidden rounded-[3px] bg-track">
              <div
                className={cn('h-full rounded-[3px]', spent > budget ? 'bg-failed' : 'bg-blue-600')}
                style={{ width: `${ratio * 100}%` }}
              />
            </div>
            <p
              className={cn(
                'mt-[7px] text-label tabular-nums',
                spent > budget ? 'font-semibold text-failed' : 'text-mute',
              )}
            >
              {spent > budget
                ? `예산보다 ${formatCurrency(spent - budget)} 더 썼어요`
                : `남은 금액 ${formatCurrency(budget - spent)}`}
            </p>
          </>
        ) : (
          <p className="text-caption text-mute">
            예산을 아직 정하지 않았어요.
            {spent > 0 && (
              <>
                {' '}
                지금까지 <span className="font-bold text-ink tabular-nums">{formatCurrency(spent)}</span>{' '}
                썼어요.
              </>
            )}
          </p>
        )}
      </Section>
    </Frame>
  )
}

function ApprovalsCard({ card }: { card: CardOf<'approvals'> }) {
  return (
    <div className="flex w-full flex-col gap-[10px]">
      {card.groups.map((group) => (
        <Frame
          key={group.eventId}
          title={
            <>
              <h3 className="text-h3 text-ink">{group.eventTitle}</h3>
              <Chip tone="pending" size="sm">
                승인 대기 {group.actions.length}건
              </Chip>
            </>
          }
          footer={{ label: '행사 상세에서 승인하기', href: eventPath(group.eventId) }}
        >
          <ul className="divide-y divide-line border-t border-line">
            {group.actions.map((action) => (
              <li
                key={action.id}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4 px-[20px] py-[11px]"
              >
                <span className="flex min-w-0 items-start gap-[10px]">
                  <Dot />
                  <span className="min-w-0">
                    <span className="block break-keep text-body text-ink">{action.title}</span>
                    {action.stepName && (
                      <span className="mt-[1px] block text-caption text-mute">
                        {action.stepName} 단계
                      </span>
                    )}
                  </span>
                </span>
                {action.dueDate && (
                  <span className="pt-[2px]">
                    <Due date={action.dueDate} />
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Frame>
      ))}
    </div>
  )
}

interface TaskRow {
  id: string
  title: string
  schedule: boolean
  assignee: string | null
  dueDate: string | null
}

function TaskRows({ rows, empty }: { rows: TaskRow[]; empty: string }) {
  if (rows.length === 0)
    return <p className="border-t border-line px-[20px] py-[13px] text-caption text-mute">{empty}</p>
  return (
    <ul className="divide-y divide-line border-t border-line">
      {rows.map((task) => (
        <li
          key={task.id}
          className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-[2px] px-[20px] py-[11px] sm:grid-cols-[minmax(0,1fr)_96px_112px]"
        >
          <span className="flex min-w-0 items-center gap-[7px]">
            {task.schedule && (
              <Chip tone="neutral" size="sm">
                일정
              </Chip>
            )}
            <span className="truncate text-body text-ink">{task.title}</span>
          </span>
          <span className="order-3 col-span-2 truncate text-caption text-mute sm:order-none sm:col-span-1">
            {task.assignee ?? '담당자 미정'}
          </span>
          <span className="text-right">
            {task.schedule && !task.dueDate ? (
              <span className="text-caption text-mute">날짜 미정</span>
            ) : (
              <Due date={task.dueDate} />
            )}
          </span>
        </li>
      ))}
    </ul>
  )
}

// 회의에서 확정한 할 일·일정.
function MeetingTasksCard({ card }: { card: CardOf<'tasks'> }) {
  return (
    <Frame
      title={<h3 className="text-h3 text-ink">{card.title}</h3>}
      aside={
        <span className="shrink-0 text-caption text-mute">
          {card.tasks.length}
          {card.hasMore ? '건 넘게' : '건'}
        </span>
      }
      footer={{ label: '회의 기록에서 보기', href: meetingPath(card.meetingId) }}
    >
      <TaskRows
        empty="확정한 할 일이 없어요."
        rows={card.tasks.map((task) => ({
          id: task.id,
          title: task.title,
          schedule: task.kind === 'SCHEDULE',
          assignee: task.assigneeName ?? null,
          dueDate: task.dueDate ?? null,
        }))}
      />
    </Frame>
  )
}

const TASK_KIND: Record<MyTasks['kind'], string> = {
  task: '할 일',
  schedule: '일정',
  all: '할 일과 일정',
}

// 「이번 주 내 할 일」처럼 기간과 사람으로 찾은 확정 할 일.
function MyTasksCard({ tasks }: { tasks: MyTasks }) {
  const range =
    tasks.dateFrom || tasks.dateTo
      ? `${tasks.dateFrom ? shortDay(tasks.dateFrom) : '처음'} ~ ${tasks.dateTo ? shortDay(tasks.dateTo) : ''}`
      : null
  return (
    <Frame
      title={
        <h3 className="text-h3 text-ink">
          {tasks.scope === 'self' ? '내' : '팀'} {TASK_KIND[tasks.kind]}
        </h3>
      }
      aside={
        <span className="shrink-0 text-caption text-mute tabular-nums">
          {range && `${range} | `}
          {tasks.items.length}
          {tasks.hasMore ? '건 넘게' : '건'}
        </span>
      }
      footer={{ label: '회의 화면에서 전체 보기', href: '/meetings' }}
    >
      <TaskRows
        empty="이 기간에 확정한 일이 없어요."
        rows={tasks.items.map((item) => ({
          id: item.id,
          title: item.title,
          schedule: item.kind === 'SCHEDULE',
          assignee: item.assigneeName,
          dueDate: kstDay(item.kind === 'SCHEDULE' ? item.scheduledAt : item.dueAt),
        }))}
      />
    </Frame>
  )
}

// 행사 계획 요청. 한 말을 그대로 들고 계획 화면으로 간다. 조건은 계획 화면에서 토리가 다시 정리한다.
function HandoffCard({ card }: { card: CardOf<'handoff'> }) {
  const navigate = useNavigate()
  const path = useDeskPath()
  return (
    <Frame title={<h3 className="text-h3 text-ink">새 행사 계획</h3>}>
      <div className="border-t border-line px-[20px] py-[13px]">
        <p className="text-label text-mute">말씀하신 내용</p>
        <p className="mt-[5px] break-keep break-words whitespace-pre-wrap text-body text-ink">
          {card.message}
        </p>
      </div>
      <div className="flex flex-col gap-[10px] border-t border-line px-[20px] pt-[13px] pb-[15px]">
        <p className="break-keep text-caption text-ink2">
          계획 화면 입력창에 이 내용을 넣어 둘게요. 보내면 토리가 조건을 정리하고, 빠진 조건은
          이어서 물어봐요.
        </p>
        <Button
          className="self-start"
          onClick={() => navigate(path('/planning'), { state: { handoffText: card.message } })}
        >
          계획 화면으로 가기
        </Button>
      </div>
    </Frame>
  )
}

export function ToriCardView({ card }: { card: ToriCard }) {
  switch (card.type) {
    case 'events':
      return <EventsCard card={card} />
    case 'briefing':
      return <BriefingCard card={card} />
    case 'event_status':
      return <EventStatusCard card={card} />
    case 'approvals':
      return <ApprovalsCard card={card} />
    case 'tasks':
      return <MeetingTasksCard card={card} />
    case 'my_tasks':
      return <MyTasksCard tasks={card.tasks} />
    case 'handoff':
      return <HandoffCard card={card} />
  }
}
