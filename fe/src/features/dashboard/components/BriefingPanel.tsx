// 메인 첫 화면의 브리핑. 질문하기 전에 「지금 챙길 것」과 진행 중인 행사를 한 번에 보인다.
// 숫자와 목록은 서버가 모은 값을 그대로 쓰고, 토리 문장도 그 값으로만 만든다(모델이 쓰지 않는다).
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cardStepText, showsProgress } from '@/features/events/cardModel'
import { SegmentBar } from '@/features/events/components/SegmentBar'
import type { EventSummary } from '@/features/events/types'
import type { BriefingItem, BriefingKind, BriefingState } from '@/features/dashboard/desk'
import {
  briefingPath,
  daysUntil,
  dueLabel,
  eventPath,
  useDeskPath,
} from '@/features/dashboard/desk'
import { cn } from '@/shared/lib/cn'
import { EVENT_STATUS_LABEL, EVENT_STATUS_TONE } from '@/shared/lib/labels'
import { staggerDelay } from '@/shared/lib/stagger'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import { Skeleton } from '@/shared/ui/Skeleton'
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

function headline(briefing: BriefingState): string {
  if (briefing.status === 'loading') return '오늘 확인할 일을 모으고 있어요'
  if (briefing.status === 'error') return '무엇을 도와드릴까요?'
  const count = briefing.data.items.length
  return count === 0 ? '오늘은 확인할 일이 없어요' : `오늘 확인할 일이 ${count}개 있어요`
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

export function ItemRow({
  item,
  index,
  onAsk,
  className,
}: {
  item: BriefingItem
  index: number
  onAsk?: (text: string) => void
  // 카드 안에서는 카드 여백에 맞춘다.
  className?: string
}) {
  const kind = KIND[item.kind]
  const path = useDeskPath()
  return (
    <li
      className="group relative animate-turn-in motion-reduce:animate-none"
      style={{ animationDelay: staggerDelay(index) }}
    >
      {/* 오른쪽 칸은 「토리에게 묻기」가 올라오는 자리라 너비를 늘 잡아 둔다. 올라와도 제목이 밀리지 않는다. */}
      <Link
        to={path(briefingPath(item))}
        className={cn(
          'grid grid-cols-[52px_minmax(0,1fr)_auto] items-center gap-x-[14px] px-[23px] py-[14px] transition-colors group-hover:bg-bg focus-visible:bg-bg focus-visible:outline-none sm:grid-cols-[52px_76px_minmax(0,1fr)_112px]',
          className,
        )}
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
  const path = useDeskPath()
  const states = event.stepProgress.map((step) => step.state)
  const planning = event.status === 'PLANNING'
  return (
    <Link
      to={path(eventPath(event.id))}
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

// 브리핑을 받아오는 동안 목록 자리를 미리 잡아 둔다. 다 오면 같은 높이에 줄이 들어온다.
function ItemsLoading() {
  return (
    <div role="status" className="overflow-hidden rounded-[24px] border border-line bg-card">
      <span className="sr-only">확인할 일을 불러오고 있어요</span>
      <div className="border-b border-line px-[23px] pt-[18px] pb-[14px]">
        <Skeleton className="h-[20px] w-[96px]" />
      </div>
      <ul className="divide-y divide-line">
        {[0, 1, 2].map((row) => (
          <li
            key={row}
            className="grid grid-cols-[52px_minmax(0,1fr)] items-center gap-x-[14px] px-[23px] py-[14px]"
          >
            <Skeleton className="h-[16px] w-[36px]" />
            <span className="flex flex-col gap-[6px]">
              <Skeleton className="h-[16px] w-[58%]" />
              <Skeleton className="h-[13px] w-[34%]" />
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function BriefingPanel({
  briefing,
  children,
  onAsk,
}: {
  briefing: BriefingState
  // 토리 문장 바로 아래 자리. 대화 전에는 여기에 입력 상자를 둬서 「물어볼 수 있다」가 먼저 보이게 한다.
  children?: ReactNode
  onAsk?: (text: string) => void
}) {
  const path = useDeskPath()
  const items = briefing.status === 'ready' ? briefing.data.items : []
  const events = briefing.status === 'ready' ? briefing.data.events : []
  const shown = items.slice(0, VISIBLE_ITEMS)
  const hidden = items.length - shown.length
  return (
    <section aria-labelledby="briefing-title" className="flex flex-col gap-[32px]">
      {/* 토리 문장 → 입력 상자 → 확인할 일 → 행사. 입력 상자와 아래 목록은 같은 폭·같은 글 시작선을 쓴다. */}
      <div className="flex flex-col gap-[20px]">
        <div className="flex items-center gap-[14px] pl-[2px]">
          <Tori size={44} thinking={briefing.status === 'loading'} />
          <div className="min-w-0">
            <h1 id="briefing-title" className="text-h1 text-ink">
              {headline(briefing)}
            </h1>
            <p className="mt-[4px] break-keep text-ink2">{INTRO}</p>
          </div>
        </div>
        {children}
      </div>

      {briefing.status === 'loading' && <ItemsLoading />}

      {/* 브리핑을 못 받아도 질문은 할 수 있다. 무엇이 안 됐는지와 다시 받는 방법만 알린다. */}
      {briefing.status === 'error' && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-line bg-card px-[23px] py-[16px]"
        >
          <p className="break-keep text-caption text-ink2">
            <span className="font-bold text-ink">확인할 일과 행사를 불러오지 못했어요.</span> 질문은
            그대로 할 수 있어요.
          </p>
          <Button size="sm" variant="secondary" onClick={briefing.retry}>
            다시 불러오기
          </Button>
        </div>
      )}

      {items.length > 0 && (
        <div className="overflow-hidden rounded-[24px] border border-line bg-card">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line px-[23px] pt-[18px] pb-[14px]">
            <h2 className="text-h3 text-ink">
              확인할 일 <span className="tabular-nums text-blue-700">{items.length}</span>
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

      {events.length > 0 && (
        <div className="flex flex-col gap-[12px]">
          <div className="flex items-baseline justify-between gap-3 px-[2px]">
            <h2 className="text-h3 text-ink">진행 중인 행사</h2>
            <Link
              to={path('/events')}
              className="text-caption font-semibold text-blue-700 underline-offset-4 hover:underline"
            >
              행사 목록
            </Link>
          </div>
          <div className="grid gap-[12px] sm:grid-cols-2 lg:grid-cols-3">
            {events.map((event) => (
              <EventTile key={event.id} event={event} />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
