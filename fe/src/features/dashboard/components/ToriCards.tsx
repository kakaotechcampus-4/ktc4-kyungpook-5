// 토리 답 아래에 붙는 카드. 줄글로 늘어놓던 목록을 화면에서 바로 읽고 눌러 이동할 수 있게 한다.
// 모든 카드는 같은 틀(머리 | 본문 줄 | 이동 링크)을 쓰고, 행사 화면의 칩과 진행 바를 그대로 쓴다.
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { cardStepText, showsProgress } from '@/features/events/cardModel'
import { SegmentBar } from '@/features/events/components/SegmentBar'
import type { EventSummary } from '@/features/events/types'
import { Chevron } from '@/features/dashboard/components/BriefingPanel'
import type {
  ApprovalGroup,
  EventStatusData,
  HandoffCondition,
  RelatedRow,
  TaskRow,
  ToriCard,
} from '@/features/dashboard/desk'
import { daysUntil, dueLabel, shortDay } from '@/features/dashboard/desk'
import { cn } from '@/shared/lib/cn'
import { formatCurrency, formatDateRange } from '@/shared/lib/format'
import { EVENT_STATUS_LABEL, EVENT_STATUS_TONE } from '@/shared/lib/labels'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'

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
  return (
    <div className="w-full overflow-hidden rounded-[20px] border border-line bg-card">
      <div className="flex items-center justify-between gap-3 px-[20px] pt-[14px] pb-[12px]">
        <div className="flex min-w-0 flex-wrap items-center gap-[8px]">{title}</div>
        {aside}
      </div>
      {children}
      {footer && (
        <Link
          to={footer.href}
          className="flex items-center justify-between border-t border-line px-[20px] py-[11px] text-caption font-bold text-blue-700 transition-colors hover:bg-blue-50"
        >
          {footer.label}
          <Chevron />
        </Link>
      )}
    </div>
  )
}

function Due({ date }: { date: string | null }) {
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

function EventsCard({ events }: { events: EventSummary[] }) {
  return (
    <Frame
      title={<h3 className="text-h3 text-ink">행사 {events.length}개</h3>}
      footer={{ label: '행사 목록에서 전체 보기', href: '/events?demo' }}
    >
      <ul className="divide-y divide-line border-t border-line">
        {events.map((event) => {
          const meta = [
            formatDateRange(event.startDate, event.endDate),
            event.location,
            event.status === 'PLANNING'
              ? `초안 ${cardStepText(event)}`
              : `지금 ${event.currentStepName ?? '진행 중'}`,
          ].filter(Boolean)
          return (
            <li key={event.id}>
              <Link
                to={`/events/${event.id}?demo`}
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

// 행사 현황. 단계 진행, 승인 대기, 다음 단계, 예산을 한 카드에 둔다. 줄 머리는 계획 조건 카드처럼 왼쪽에 둔다.
function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[72px_minmax(0,1fr)] gap-x-[14px] border-t border-line px-[20px] py-[13px]">
      <p className="pt-[1px] text-label text-mute">{label}</p>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

function EventStatusCard({ status }: { status: EventStatusData }) {
  const { event, current, next, approvals, budget, spent } = status
  const ratio = budget ? Math.min(1, spent / budget) : 0
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
      footer={{ label: '행사 상세에서 보기', href: `/events/${event.id}?demo` }}
    >
      <Section label="진행">
        <SegmentBar states={event.stepProgress.map((step) => step.state)} />
        <p className="mt-[9px] text-caption text-ink2">
          <span className="font-bold text-ink">{cardStepText(event)}단계</span>
          {current && (
            <>
              {' | 지금 '}
              <span className="font-bold text-ink">{current.name}</span>
              {current.dueDate && <> | 마감 {dueLabel(current.dueDate)}</>}
            </>
          )}
        </p>
      </Section>
      {approvals.length > 0 && (
        <Section label={`승인 대기 ${approvals.length}`}>
          <ul className="flex flex-col gap-[6px]">
            {approvals.map((title) => (
              <li key={title} className="flex items-start gap-[8px] text-caption text-ink">
                <span
                  aria-hidden
                  className="mt-[7px] size-[5px] shrink-0 rounded-full bg-pending"
                />
                <span className="break-keep">{title}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      {next.length > 0 && (
        <Section label="다음 단계">
          <ul className="flex flex-col gap-[6px]">
            {next.map((step) => (
              <li key={step.name} className="flex justify-between gap-3 text-caption">
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
                className="h-full rounded-[3px] bg-blue-600"
                style={{ width: `${ratio * 100}%` }}
              />
            </div>
            <p className="mt-[7px] text-label text-mute tabular-nums">
              남은 금액 {formatCurrency(Math.max(0, budget - spent))}
            </p>
          </>
        ) : (
          <p className="text-caption text-mute">예산을 아직 정하지 않았어요.</p>
        )}
      </Section>
    </Frame>
  )
}

function ApprovalsCard({ groups }: { groups: ApprovalGroup[] }) {
  return (
    <div className="flex w-full flex-col gap-[10px]">
      {groups.map((group) => (
        <Frame
          key={group.eventTitle}
          title={
            <>
              <h3 className="text-h3 text-ink">{group.eventTitle}</h3>
              <Chip tone="pending" size="sm">
                승인 대기 {group.titles.length}건
              </Chip>
            </>
          }
          footer={{ label: '행사 상세에서 승인하기', href: group.href }}
        >
          <ul className="divide-y divide-line border-t border-line">
            {group.titles.map((title) => (
              <li
                key={title}
                className="flex items-start gap-[10px] px-[20px] py-[11px] text-body text-ink"
              >
                <span
                  aria-hidden
                  className="mt-[8px] size-[5px] shrink-0 rounded-full bg-pending"
                />
                <span className="break-keep">{title}</span>
              </li>
            ))}
          </ul>
        </Frame>
      ))}
    </div>
  )
}

function TasksCard({
  title,
  tasks,
  footer,
}: {
  title: string
  tasks: TaskRow[]
  footer: { label: string; href: string }
}) {
  return (
    <Frame
      title={<h3 className="text-h3 text-ink">{title}</h3>}
      aside={<span className="shrink-0 text-caption text-mute">{tasks.length}건</span>}
      footer={footer}
    >
      <ul className="divide-y divide-line border-t border-line">
        {tasks.map((task) => (
          <li
            key={task.id}
            className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-[2px] px-[20px] py-[11px] sm:grid-cols-[minmax(0,1fr)_88px_112px]"
          >
            <span className="truncate text-body text-ink">{task.title}</span>
            <span className="order-3 col-span-2 text-caption text-mute sm:order-none sm:col-span-1">
              {task.assignee ?? '담당자 미정'}
            </span>
            <span className="text-right">
              <Due date={task.dueDate} />
            </span>
          </li>
        ))}
      </ul>
    </Frame>
  )
}

function HandoffCard({
  title,
  conditions,
  href,
}: {
  title: string
  conditions: HandoffCondition[]
  href: string
}) {
  const navigate = useNavigate()
  return (
    <Frame title={<h3 className="text-h3 text-ink">{title}</h3>}>
      <dl className="flex flex-col gap-[7px] border-t border-line px-[20px] py-[13px]">
        {conditions.map(({ label, value }) => (
          <div key={label} className="flex justify-between gap-3 text-caption">
            <dt className="text-mute">{label}</dt>
            <dd
              className={cn(
                value === '미정' || value === '이름 미정' ? 'text-mute' : 'font-bold text-ink',
              )}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-col gap-[10px] border-t border-line px-[20px] pt-[13px] pb-[15px]">
        <p className="break-keep text-caption text-ink2">
          정해지지 않은 조건은 계획 화면에서 토리가 이어서 물어봐요.
        </p>
        <Button className="self-start" onClick={() => navigate(href)}>
          이 내용으로 계획 시작
        </Button>
      </div>
    </Frame>
  )
}

function RelatedCard({ title, rows }: { title: string; rows: RelatedRow[] }) {
  return (
    <Frame title={<h3 className="text-h3 text-ink">{title}</h3>}>
      <ul className="divide-y divide-line border-t border-line">
        {rows.map((row) => (
          <li key={row.title}>
            <Link
              to={row.href}
              className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 px-[20px] py-[12px] transition-colors hover:bg-bg"
            >
              <span className="min-w-0">
                <span className="block break-keep text-body text-ink">{row.title}</span>
                <span className="mt-[2px] block text-caption text-mute">
                  {row.source} | <span className="font-semibold text-pending">{row.status}</span>
                </span>
              </span>
              <span className="flex items-center gap-[4px] text-caption font-bold text-blue-700">
                {row.action}
                <Chevron />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Frame>
  )
}

export function ToriCardView({ card }: { card: ToriCard }) {
  switch (card.type) {
    case 'events':
      return <EventsCard events={card.events} />
    case 'event_status':
      return <EventStatusCard status={card.status} />
    case 'approvals':
      return <ApprovalsCard groups={card.groups} />
    case 'tasks':
      return <TasksCard title={card.title} tasks={card.tasks} footer={card.footer} />
    case 'handoff':
      return <HandoffCard title={card.title} conditions={card.conditions} href={card.href} />
    case 'related':
      return <RelatedCard title={card.title} rows={card.rows} />
  }
}
