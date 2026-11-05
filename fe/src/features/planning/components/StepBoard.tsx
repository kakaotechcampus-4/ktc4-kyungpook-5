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
import { Button } from '@/shared/ui/Button'

interface StepBoardProps {
  included: CatalogueStep[]
  schedule: Record<string, string>
  onReorder: (phase: StepPhase, from: number, to: number) => void
  onRemove: (code: string) => void
  dates?: Record<string, { startsAt: string | null; deadline: string | null }>
  onEditDetail?: (code: string) => void
  detailsDisabled?: boolean
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

export function StepBoard({
  included,
  schedule,
  onReorder,
  onRemove,
  dates,
  onEditDetail,
  detailsDisabled = false,
}: StepBoardProps) {
  const helpId = useId()
  const boardRef = useRef<HTMLDivElement>(null)
  const [sort, setSort] = useState<Sort | null>(null)
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
      <div className="mb-5">
        <h2 className="text-h2">포함된 단계 · {included.length}개</h2>
        <p id={helpId} className="mt-2 text-label text-mute">
          왼쪽 손잡이로 같은 묶음 안에서 이동해요. 키보드: Space/Enter로 선택 → 위아래 방향키 →
          Space/Enter로 놓기, Escape로 취소.
        </p>
      </div>
      <p role="status" className="sr-only">
        {announcement}
      </p>
      <div className="space-y-6">
        {PHASES.map((phase) => {
          const rows = included.filter((step) => step.phase === phase)
          const preview = [...rows]
          if (sort?.phase === phase) preview.splice(sort.to, 0, ...preview.splice(sort.from, 1))
          return (
            <section
              key={phase}
              aria-label={phase}
              data-phase-group={phase}
              className={`overflow-hidden rounded-xl border bg-card ${sort?.phase === phase ? 'border-blue-400' : 'border-line'}`}
            >
              <header className="flex items-center justify-between gap-3 border-b border-line bg-blue-50 px-4 py-4">
                <h3 className="text-h3">{phase}</h3>
                <span className="text-label text-ink2">{rows.length}개 단계</span>
              </header>
              <div className="px-3 sm:px-4">
                {!rows.length && (
                  <p className="py-6 text-caption text-mute">
                    포함된 단계가 없어요. 미포함 목록에서 다시 포함할 수 있어요.
                  </p>
                )}
                {preview.map((step, index) => {
                  const active = sort?.code === step.code
                  return (
                    <div
                      key={step.code}
                      data-sort-code={step.code}
                      className={`flex items-center gap-2 border-b border-line py-3 last:border-b-0 sm:gap-3 ${active ? 'rounded-lg bg-blue-50 outline-1 outline-dashed outline-blue-400' : ''}`}
                    >
                      <button
                        type="button"
                        aria-label={`${step.name} 순서 변경`}
                        aria-describedby={helpId}
                        aria-pressed={active}
                        disabled={rows.length < 2}
                        onKeyDown={(event) =>
                          keyboard(
                            event,
                            step,
                            rows.findIndex((row) => row.code === step.code),
                            rows.length,
                          )
                        }
                        onPointerDown={(event) => {
                          if (event.button !== 0 || rows.length < 2 || sort) return
                          event.preventDefault()
                          event.currentTarget.focus()
                          boardRef.current?.setPointerCapture(event.pointerId)
                          const rect = event.currentTarget.parentElement!.getBoundingClientRect()
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
                        className="flex min-h-11 min-w-11 shrink-0 touch-none items-center justify-center self-stretch rounded-lg text-mute select-none hover:bg-blue-100 focus-visible:bg-blue-100 disabled:opacity-30 [cursor:grab] active:[cursor:grabbing]"
                      >
                        <svg
                          aria-hidden
                          viewBox="0 0 20 24"
                          width="18"
                          height="22"
                          fill="currentColor"
                        >
                          {[6, 12, 18].flatMap((y) =>
                            [7, 13].map((x) => <circle key={`${x}:${y}`} cx={x} cy={y} r="1.5" />),
                          )}
                        </svg>
                      </button>
                      <div
                        className={`min-w-0 flex-1 ${active && sort.pointer ? 'opacity-40' : ''}`}
                      >
                        <h4 className="text-body-strong [overflow-wrap:anywhere]">{step.name}</h4>
                        <p className="mt-1 text-label text-mute">
                          {step.actor} ·{' '}
                          {dates ? dateRange(dates[step.code]) : schedule[step.code] || '일정 미정'}
                        </p>
                        {dates && !dates[step.code] && (
                          <p className="mt-1 text-label text-blue-700">
                            새 단계 · 저장 후 일정과 기본 작업을 확인해 주세요.
                          </p>
                        )}
                        {onEditDetail && dates?.[step.code] && (
                          <button
                            type="button"
                            disabled={detailsDisabled || !!sort}
                            onClick={() => onEditDetail(step.code)}
                            className="mt-1 min-h-8 rounded px-1 text-label text-blue-700 underline underline-offset-4 disabled:opacity-40"
                          >
                            일정·내용 수정
                          </button>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={!!sort}
                        aria-label={`${step.name} 제외`}
                        onClick={() => onRemove(step.code)}
                      >
                        제외
                      </Button>
                    </div>
                  )
                })}
              </div>
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
