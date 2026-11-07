// 구성은 이 화면에서만 미리 보며, 확정은 상위 화면의 구성 저장이 맡는다.
import {
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from 'react'
import type { CatalogueStep } from '../catalogue'
import { PHASES } from '../catalogue'
import type { StepPhase } from '../types'
import { formatMonthDay } from '@/shared/lib/format'
import { cn } from '@/shared/lib/cn'
import { Chip } from '@/shared/ui/Chip'

const ACTOR_TONE = {
  '승인 필요': 'pending',
  'AI 실행': 'approved',
  '직접 수행': 'neutral',
} as const

function Key({ children }: { children: string }) {
  return (
    <span className="mx-[1px] inline-block rounded-[4px] bg-white/15 px-[4px] font-semibold text-white">
      {children}
    </span>
  )
}

interface StepBoardProps {
  included: CatalogueStep[]
  schedule: Record<string, string>
  onReorder: (phase: StepPhase, from: number, to: number) => void
  onRemove: (code: string) => void
  dates?: Record<string, { startsAt: string | null; deadline: string | null }>
}
type Sort = {
  phase: StepPhase
  code: string
  from: number
  to: number
  pointer: boolean
  valid: boolean
  x: number
  y: number
  width: number
}

function dateRange(range?: { startsAt: string | null; deadline: string | null }) {
  const from = range?.startsAt ? formatMonthDay(range.startsAt) : ''
  const to = range?.deadline ? formatMonthDay(range.deadline) : ''
  return from && to ? `${from} – ${to}` : from || to || '일정 미정'
}

export function StepBoard({ included, schedule, onReorder, onRemove, dates }: StepBoardProps) {
  const helpId = useId()
  const boardRef = useRef<HTMLDivElement>(null)
  const [sort, setSort] = useState<Sort | null>(null)
  // 손잡이 말풍선을 Escape로 닫았는지. 손잡이를 떠나면 다시 뜰 수 있다.
  const [tipClosed, setTipClosed] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  useLayoutEffect(() => {
    if (sort && !sort.pointer)
      boardRef.current
        ?.querySelector<HTMLButtonElement>(`[data-sort-code="${sort.code}"] button`)
        ?.focus()
  }, [sort])
  const finish = (commit: boolean) => {
    if (!sort) return
    if (commit && sort.valid) onReorder(sort.phase, sort.from, sort.to)
    setAnnouncement(
      commit && sort.valid
        ? `${included.find((step) => step.code === sort.code)?.name} ${sort.to + 1}번째로 놓았어요. 구성 저장을 눌러 반영해 주세요.`
        : '순서 변경을 취소했어요.',
    )
    setSort(null)
  }
  const keyboard = (
    event: KeyboardEvent<HTMLButtonElement>,
    step: CatalogueStep,
    index: number,
    count: number,
  ) => {
    if (sort?.pointer) return
    if (!sort && event.key === 'Escape') {
      setTipClosed(true)
      return
    }
    if (event.key === ' ' || event.key === 'Enter') {
      event.preventDefault()
      if (sort) finish(true)
      else {
        setSort({
          phase: step.phase,
          code: step.code,
          from: index,
          to: index,
          pointer: false,
          valid: true,
          x: 0,
          y: 0,
          width: 0,
        })
        setAnnouncement(`${step.name} 선택. 위아래 방향키로 이동하고 Space 또는 Enter로 놓으세요.`)
      }
    } else if (
      sort?.code === step.code &&
      ['ArrowUp', 'ArrowDown', 'Escape', 'Tab'].includes(event.key)
    ) {
      if (event.key === 'Tab') {
        finish(false)
        return
      }
      event.preventDefault()
      if (event.key === 'Escape') finish(false)
      else {
        const to = Math.max(0, Math.min(count - 1, sort.to + (event.key === 'ArrowUp' ? -1 : 1)))
        setSort({ ...sort, to })
        setAnnouncement(`${step.name}, ${count}개 중 ${to + 1}번째`)
      }
    }
  }
  const pointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!sort?.pointer) return
    const target = document.elementFromPoint(event.clientX, event.clientY)
    const group = target?.closest<HTMLElement>('[data-phase-group]')
    const valid = group?.dataset.phaseGroup === sort.phase
    let to = sort.to
    if (valid && group) {
      const rows = [...group.querySelectorAll<HTMLElement>('[data-sort-code]')].filter(
        (row) => row.dataset.sortCode !== sort.code,
      )
      to = rows.filter(
        (row) =>
          event.clientY > row.getBoundingClientRect().top + row.getBoundingClientRect().height / 2,
      ).length
    }
    setSort({ ...sort, to, valid, x: event.clientX, y: event.clientY })
    if (event.clientY > window.innerHeight - 60) window.scrollBy(0, 16)
    else if (event.clientY < 60) window.scrollBy(0, -16)
  }
  return (
    <div
      ref={boardRef}
      className="min-w-0 flex-1"
      onPointerMove={pointerMove}
      onPointerUp={(event) => {
        if (!sort?.pointer) return
        const group = document
          .elementFromPoint(event.clientX, event.clientY)
          ?.closest<HTMLElement>('[data-phase-group]')
        finish(group?.dataset.phaseGroup === sort.phase)
      }}
      onPointerCancel={() => finish(false)}
      onLostPointerCapture={() => {
        if (sort?.pointer) finish(false)
      }}
      onKeyDown={(event) => {
        if (sort?.pointer && event.key === 'Escape') finish(false)
      }}
    >
      {/* 사용법은 손잡이 말풍선으로 보인다. 화면 낭독기는 손잡이마다 이 글을 설명으로 읽는다. */}
      <p id={helpId} className="sr-only">
        손잡이를 끌어 같은 묶음 안에서 순서를 바꿔요. 키보드로는 Space 또는 Enter로 집고, 위아래
        방향키로 옮긴 뒤 Space 또는 Enter로 놓아요. Escape로 취소해요.
      </p>
      <p role="status" className="sr-only">
        {announcement}
      </p>
      <div className="space-y-7">
        {PHASES.map((phase) => {
          const rows = included.filter((step) => step.phase === phase)
          const preview = [...rows]
          if (sort?.phase === phase) preview.splice(sort.to, 0, ...preview.splice(sort.from, 1))
          return (
            <section
              key={phase}
              aria-label={phase}
              data-phase-group={phase}
              className={cn(
                '-mx-3 rounded-2xl px-3 py-2 transition-colors duration-150 motion-reduce:transition-none',
                sort?.phase === phase && 'ring-1 ring-blue-200',
              )}
            >
              <header className="mb-3 flex items-center justify-between">
                <h3 className="text-h3">{phase}</h3>
                <span className="text-label font-normal text-mute">{rows.length}개 단계</span>
              </header>
              {!rows.length && (
                <p className="rounded-xl border border-dashed border-line px-4 py-5 text-caption text-mute">
                  포함된 단계가 없어요. 포함하지 않은 단계에서 다시 넣을 수 있어요.
                </p>
              )}
              <ol className="space-y-3">
                {preview.map((step, index) => {
                  const active = sort?.code === step.code
                  const movable = rows.length > 1
                  return (
                    <li
                      key={step.code}
                      data-sort-code={step.code}
                      className="grid grid-cols-[42px_minmax(0,1fr)] items-stretch gap-2 sm:grid-cols-[52px_minmax(0,1fr)] sm:gap-3"
                    >
                      {/* 계획 검토의 날짜 줄 자리에 손잡이가 온다. 칸 모양은 계획 검토와 같다. */}
                      <div
                        className="group/handle relative flex justify-center"
                        onPointerLeave={() => setTipClosed(false)}
                      >
                        <button
                          type="button"
                          aria-label={`${step.name} 순서 변경`}
                          aria-describedby={helpId}
                          aria-pressed={active}
                          disabled={!movable}
                          onBlur={() => setTipClosed(false)}
                          onKeyDown={(event) =>
                            keyboard(
                              event,
                              step,
                              rows.findIndex((row) => row.code === step.code),
                              rows.length,
                            )
                          }
                          onPointerDown={(event) => {
                            if (event.button !== 0 || !movable || sort) return
                            event.preventDefault()
                            event.currentTarget.focus()
                            boardRef.current?.setPointerCapture(event.pointerId)
                            const rect = event.currentTarget.closest('li')!.getBoundingClientRect()
                            setSort({
                              phase,
                              code: step.code,
                              from: index,
                              to: index,
                              pointer: true,
                              valid: true,
                              x: event.clientX,
                              y: event.clientY,
                              width: rect.width,
                            })
                          }}
                          className={cn(
                            'flex min-h-11 w-11 touch-none items-center justify-center self-stretch rounded-xl text-mute outline-none select-none [cursor:grab] hover:bg-blue-100 hover:text-blue-700 focus-visible:bg-blue-100 focus-visible:text-blue-700 focus-visible:outline-2 focus-visible:outline-blue-600 active:[cursor:grabbing] disabled:cursor-default disabled:opacity-30 disabled:hover:bg-transparent',
                            active && 'bg-blue-100 text-blue-700',
                          )}
                        >
                          <svg
                            aria-hidden
                            viewBox="0 0 20 24"
                            width="18"
                            height="22"
                            fill="currentColor"
                          >
                            {[6, 12, 18].flatMap((y) =>
                              [7, 13].map((x) => (
                                <circle key={`${x}:${y}`} cx={x} cy={y} r="1.5" />
                              )),
                            )}
                          </svg>
                        </button>
                        {movable && !sort && (
                          <span
                            aria-hidden
                            className={cn(
                              'invisible absolute bottom-full left-0 z-20 mb-1.5 w-max whitespace-nowrap rounded-[8px] bg-ink px-[10px] py-[7px] text-[11.5px] leading-[17px] text-white opacity-0 shadow-[0_6px_18px_rgba(32,43,56,0.18)] transition-opacity duration-150 motion-reduce:transition-none',
                              'group-hover/handle:visible group-hover/handle:opacity-100 group-hover/handle:delay-300 group-has-[:focus-visible]/handle:visible group-has-[:focus-visible]/handle:opacity-100',
                              tipClosed && '!invisible',
                            )}
                          >
                            <span className="block font-semibold">끌어서 순서 바꾸기</span>
                            <span className="block text-blue-100">
                              <Key>Space</Key> 집기 · <Key>↑</Key>
                              <Key>↓</Key> 옮기기 · <Key>Space</Key> 놓기 · <Key>Esc</Key> 취소
                            </span>
                          </span>
                        )}
                      </div>
                      <div
                        className={cn(
                          'flex min-w-0 items-start justify-between gap-2 rounded-xl border p-3 sm:p-4',
                          active
                            ? 'border-dashed border-blue-400 bg-blue-50'
                            : 'border-transparent bg-bg',
                          active && sort.pointer && 'opacity-50',
                        )}
                      >
                        <div className="min-w-0">
                          <h4 className="font-semibold [overflow-wrap:anywhere]">{step.name}</h4>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-label">
                            <Chip size="sm" tone={ACTOR_TONE[step.actor]}>
                              {step.actor}
                            </Chip>
                            <span className="text-mute">
                              {dates
                                ? dateRange(dates[step.code])
                                : schedule[step.code] || '일정 미정'}
                            </span>
                          </div>
                          {dates && !dates[step.code] && (
                            <p className="mt-2 text-label text-blue-700">
                              새 단계 · 저장 후 일정과 기본 작업을 확인해 주세요.
                            </p>
                          )}
                        </div>
                        <button
                          type="button"
                          disabled={!!sort}
                          aria-label={`${step.name} 제외`}
                          onClick={() => onRemove(step.code)}
                          className="min-h-9 shrink-0 rounded-[8px] px-[10px] text-[13px] font-medium text-ink2 hover:bg-card hover:text-ink focus-visible:bg-card disabled:opacity-40"
                        >
                          제외
                        </button>
                      </div>
                    </li>
                  )
                })}
              </ol>
            </section>
          )
        })}
      </div>
      {!included.length && (
        <p role="alert" className="mt-4 rounded-xl bg-pending-bg p-4 text-caption text-pending">
          한 개 이상의 단계를 포함해야 저장할 수 있어요.
        </p>
      )}
      {sort?.pointer && (
        <div
          aria-hidden
          style={{
            position: 'fixed',
            left: Math.max(
              8,
              Math.min(sort.x - 35, window.innerWidth - Math.min(sort.width, 380) - 8),
            ),
            top: sort.y - 24,
            width: Math.min(sort.width, 380),
            pointerEvents: 'none',
            zIndex: 50,
          }}
          className="rounded-xl bg-card px-4 py-4 text-body-strong shadow-[0_8px_26px_rgba(32,43,56,0.2)]"
        >
          <p>{included.find((step) => step.code === sort.code)?.name}</p>
          <p className="mt-1 text-label font-normal text-mute">
            {sort.valid
              ? `${sort.phase} · ${sort.to + 1}번째에 놓기`
              : '묶음 밖에 놓으면 변경을 취소해요'}
          </p>
        </div>
      )}
    </div>
  )
}
