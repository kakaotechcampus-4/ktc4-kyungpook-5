// 메인 첫 화면의 브리핑. 질문하기 전에 「지금 챙길 것」과 진행 중인 행사를 한 번에 보인다.
// 숫자와 목록은 서버가 모은 값을 그대로 쓰고, 토리 문장도 그 값으로만 만든다(모델이 쓰지 않는다).
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cardStepText, showsProgress } from '@/features/events/cardModel'
import { SegmentBar } from '@/features/events/components/SegmentBar'
import type { EventSummary } from '@/features/events/types'
import type { Briefing, BriefingItem, BriefingKind } from '@/features/dashboard/desk'
import { daysUntil, dueLabel } from '@/features/dashboard/desk'
import { cn } from '@/shared/lib/cn'
import { EVENT_STATUS_LABEL, EVENT_STATUS_TONE } from '@/shared/lib/labels'
import { staggerDelay } from '@/shared/lib/stagger'
import { Chip } from '@/shared/ui/Chip'
import { Tori } from '@/shared/ui/Tori'

const KIND: Record<BriefingKind, { label: string; tone: 'approved' | 'pending' | 'neutral' }> = {
  deadline: { label: '단계 마감', tone: 'approved' },
  approval: { label: '승인 대기', tone: 'pending' },
  task: { label: '내 할 일', tone: 'neutral' },
}

// 목록이 길면 앞의 몇 줄만 두고 나머지는 질문으로 이어 보게 한다.
const VISIBLE_ITEMS = 3

export function Chevron({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className={cn('size-[14px] shrink-0', className)}
      fill="none"
    >
      <path
        d="m6 3.5 4.5 4.5L6 12.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// 제목은 오늘 확인할 일의 수, 아래 문장은 이 화면에서 토리에게 맡길 수 있는 일을 짧게 알린다.
const INTRO = '토리가 행사 진행과 할 일을 정리하고, 지난 기록에서 답을 찾아 드려요.'

function headline(items: BriefingItem[]): string {
  return items.length === 0
    ? '오늘은 확인할 일이 없어요'
    : `오늘 확인할 일이 ${items.length}개 있어요`
}

function WhenLabel({ item }: { item: BriefingItem }) {
  if (item.kind === 'approval') return <span className="text-mute">지금</span>
  const left = item.dueDate ? daysUntil(item.dueDate) : null
  return (
    <span className={cn(left !== null && left <= 0 ? 'text-failed' : 'text-ink')}>
      {dueLabel(item.dueDate)}
    </span>
  )
}

function ItemRow({
  item,
  index,
  onAsk,
}: {
  item: BriefingItem
  index: number
  onAsk?: (text: string) => void
}) {
  const kind = KIND[item.kind]
  return (
    <li
      className="group relative animate-turn-in motion-reduce:animate-none"
      style={{ animationDelay: staggerDelay(index) }}
    >
      {/* 오른쪽 칸은 「토리에게 묻기」가 올라오는 자리라 너비를 늘 잡아 둔다. 올라와도 제목이 밀리지 않는다. */}
      <Link
        to={item.href}
        className="grid grid-cols-[52px_minmax(0,1fr)_auto] items-center gap-x-[14px] px-[23px] py-[14px] transition-colors group-hover:bg-bg focus-visible:bg-bg focus-visible:outline-none sm:grid-cols-[52px_76px_minmax(0,1fr)_112px]"
      >
        <span className="text-caption font-bold tabular-nums">
          <WhenLabel item={item} />
        </span>
        <span className="hidden sm:block">
          <Chip tone={kind.tone} size="sm">
            {kind.label}
          </Chip>
        </span>
        <span className="min-w-0">
          <span className="block truncate text-body-strong text-ink">
            {item.title}
            {!!item.moreCount && (
              <span className="font-normal text-mute"> 외 {item.moreCount}건</span>
            )}
          </span>
          <span className="mt-[2px] block truncate text-caption text-mute">
            <span className="sm:hidden">{kind.label} | </span>
            {item.source}
          </span>
        </span>
        <Chevron
          className={cn(
            'justify-self-end text-soft transition-opacity',
            item.ask && onAsk && 'sm:group-focus-within:opacity-0 sm:group-hover:opacity-0',
          )}
        />
      </Link>
      {/* 줄 자체는 해당 화면으로 가고, 이 버튼은 같은 내용을 토리에게 묻는다. 손가락 화면에서는 줄만 쓴다. */}
      {item.ask && onAsk && (
        <button
          type="button"
          onClick={() => onAsk(item.ask!)}
          className="absolute top-1/2 right-[18px] hidden -translate-y-1/2 items-center gap-[5px] rounded-[8px] border border-blue-200 bg-card px-[9px] py-[5px] text-label font-bold text-blue-700 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 hover:bg-blue-50 focus-visible:opacity-100 sm:flex"
        >
          <Tori size={14} />
          토리에게 묻기
        </button>
      )}
    </li>
  )
}

function EventTile({ event }: { event: EventSummary }) {
  const states = event.stepProgress.map((step) => step.state)
  const planning = event.status === 'PLANNING'
  return (
    <Link
      to={`/events/${event.id}?demo`}
      className={cn(
        'flex min-w-0 flex-col gap-[10px] rounded-[20px] border bg-card px-[22px] pt-[18px] pb-[19px] transition-colors',
        planning ? 'border-line hover:border-soft' : 'border-blue-200 hover:border-blue-300',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-[7px]">
          <h3 className="truncate text-[15px] font-bold text-ink">{event.title}</h3>
          <Chip tone={EVENT_STATUS_TONE[event.status]} size="sm">
            {EVENT_STATUS_LABEL[event.status]}
          </Chip>
        </div>
        {event.dday !== null && (
          <span className="shrink-0 text-caption font-bold tabular-nums text-blue-700">
            D-{event.dday}
          </span>
        )}
      </div>
      <p className="truncate text-caption text-ink2">
        {planning
          ? `계획 중 | 초안 ${cardStepText(event)}`
          : `지금 ${event.currentStepName ?? '진행 중'} | ${cardStepText(event)}단계`}
      </p>
      {showsProgress(event.status) && <SegmentBar states={states} />}
      {event.pendingApprovalCount > 0 && (
        <p className="text-caption font-semibold text-pending">
          승인 대기 {event.pendingApprovalCount}건
        </p>
      )}
    </Link>
  )
}

export function BriefingPanel({
  briefing,
  children,
  onAsk,
}: {
  briefing: Briefing
  // 토리 문장 바로 아래 자리. 대화 전에는 여기에 입력 상자를 둬서 「물어볼 수 있다」가 먼저 보이게 한다.
  children?: ReactNode
  onAsk?: (text: string) => void
}) {
  const title = headline(briefing.items)
  const shown = briefing.items.slice(0, VISIBLE_ITEMS)
  const hidden = briefing.items.length - shown.length
  return (
    <section aria-labelledby="briefing-title" className="flex flex-col gap-[32px]">
      {/* 토리 문장 → 입력 상자 → 확인할 일 → 행사. 입력 상자와 아래 목록은 같은 폭·같은 글 시작선을 쓴다. */}
      <div className="flex flex-col gap-[20px]">
        <div className="flex items-center gap-[14px] pl-[2px]">
          <Tori size={44} />
          <div className="min-w-0">
            <h1 id="briefing-title" className="text-h1 text-ink">
              {title}
            </h1>
            <p className="mt-[4px] break-keep text-ink2">{INTRO}</p>
          </div>
        </div>
        {children}
      </div>

      {briefing.items.length > 0 && (
        <div className="overflow-hidden rounded-[24px] border border-line bg-card">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line px-[23px] pt-[18px] pb-[14px]">
            <h2 className="text-h3 text-ink">
              확인할 일 <span className="tabular-nums text-blue-700">{briefing.items.length}</span>
            </h2>
            <p className="text-label text-mute">3일 안 마감 | 승인 대기 | 내 할 일</p>
          </div>
          <ul className="divide-y divide-line">
            {shown.map((item, index) => (
              <ItemRow key={item.id} item={item} index={index} onAsk={onAsk} />
            ))}
          </ul>
          {hidden > 0 &&
            (onAsk ? (
              <button
                type="button"
                onClick={() => onAsk('확인할 일 전부 보여줘')}
                className="flex w-full items-center gap-[8px] border-t border-line px-[23px] py-[13px] text-left text-caption font-semibold text-blue-700 transition-colors hover:bg-blue-50"
              >
                <Tori size={16} />
                나머지 {hidden}개도 토리에게 물어보기
              </button>
            ) : (
              <p className="border-t border-line px-[23px] py-[13px] text-caption text-mute">
                {hidden}개 더 있어요.
              </p>
            ))}
        </div>
      )}

      {briefing.events.length > 0 && (
        <div className="flex flex-col gap-[12px]">
          <div className="flex items-baseline justify-between gap-3 px-[2px]">
            <h2 className="text-h3 text-ink">진행 중인 행사</h2>
            <Link
              to="/events?demo"
              className="text-caption font-semibold text-blue-700 underline-offset-4 hover:underline"
            >
              행사 목록
            </Link>
          </div>
          <div className="grid gap-[12px] sm:grid-cols-2 lg:grid-cols-3">
            {briefing.events.map((event) => (
              <EventTile key={event.id} event={event} />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
