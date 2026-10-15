// P2-b 왼쪽: 포함한 단계를 묶음별로 쌓는다. 묶음 셋은 비어 있어도 늘 그린다 —
// 그래야 끌어다 놓을 자리가 있다. 카탈로그가 묶음을 정하므로 묶음 사이로는 못 옮기고,
// 바꿀 수 있는 건 묶음 안의 순서뿐이다.
import { useState } from 'react'
import type { CatalogueStep } from '@/features/planning/catalogue'
import { PHASES, PHASE_HINT } from '@/features/planning/catalogue'
import type { StepPhase } from '@/features/planning/types'
import { cn } from '@/shared/lib/cn'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'

interface StepBoardProps {
  // 포함한 단계. 묶음 안의 순서가 곧 배열 순서다.
  included: CatalogueStep[]
  schedule: Record<string, string>
  onReorder: (phase: StepPhase, from: number, to: number) => void
  onRemove: (code: string) => void
}

export function StepBoard({ included, schedule, onReorder, onRemove }: StepBoardProps) {
  // 끌고 있는 카드. 묶음이 다르면 받지 않는다.
  const [dragging, setDragging] = useState<{ phase: StepPhase; index: number }>()

  return (
    <Card className="flex min-w-0 flex-1 flex-col">
      <div className="flex items-center justify-between px-[26px] pt-[24px] pb-[18px]">
        <span className="flex items-center gap-[9px]">
          <h2 className="text-h2 text-ink">포함된 단계</h2>
          <Chip tone="approved">{included.length}개</Chip>
        </span>
        <span className="text-[11.5px] text-mute">
          카드를 끌어 순서를 바꿉니다 · 묶음은 못 옮겨요
        </span>
      </div>

      <div className="flex flex-col gap-[14px] px-[26px] pb-[20px]">
        {PHASES.map((phase) => {
          const rows = included.filter((s) => s.phase === phase)
          return (
            <section
              key={phase}
              className="flex flex-col gap-[10px] rounded-[15px] border border-line bg-bg px-[16px] pt-[15px] pb-[16px]"
            >
              <div className="flex items-center justify-between gap-[9px]">
                <span className="flex items-center gap-[8px]">
                  <span className="text-[13.5px] font-bold text-ink">{phase}</span>
                  <Chip size="sm">{rows.length}개</Chip>
                </span>
                <span className="text-[11px] text-mute">{PHASE_HINT[phase]}</span>
              </div>

              {rows.length === 0 ? (
                <div className="flex flex-col items-center gap-[5px] rounded-[12px] border-[1.5px] border-dashed border-soft bg-card px-[18px] py-[22px]">
                  <span className="text-[12.5px] font-bold text-mute">여기로 끌어다 놓기</span>
                  <span className="text-[11px] text-mute">
                    오른쪽 목록에서 + 를 눌러도 들어옵니다
                  </span>
                </div>
              ) : (
                rows.map((step, index) => (
                  <div
                    key={step.code}
                    draggable
                    onDragStart={() => setDragging({ phase, index })}
                    onDragEnd={() => setDragging(undefined)}
                    onDragOver={(e) => {
                      // 같은 묶음일 때만 받는다.
                      if (dragging?.phase === phase) e.preventDefault()
                    }}
                    onDrop={() => {
                      if (dragging?.phase !== phase || dragging.index === index) return
                      onReorder(phase, dragging.index, index)
                      setDragging(undefined)
                    }}
                    className={cn(
                      'flex items-center gap-[13px] rounded-[12px] border bg-card px-[14px] py-[13px]',
                      dragging?.phase === phase && dragging.index === index
                        ? 'border-blue-400 opacity-60'
                        : 'border-line',
                    )}
                  >
                    <span className="cursor-grab text-[15px] text-soft" aria-hidden>
                      ⠿
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                      <span className="truncate text-[13.5px] font-bold text-ink">{step.name}</span>
                      <span className="text-[11px] text-mute">
                        {step.actor} · {step.actions}
                      </span>
                    </span>
                    <span className="shrink-0 text-[12px] text-ink2">{schedule[step.code]}</span>
                    <button
                      type="button"
                      aria-label={`${step.name} 빼기`}
                      onClick={() => onRemove(step.code)}
                      className="shrink-0 text-[13px] text-mute hover:text-ink2"
                    >
                      ⋯
                    </button>
                  </div>
                ))
              )}
            </section>
          )
        })}

        {included.length === 0 && (
          <div className="flex items-center gap-[10px] rounded-[12px] bg-pending-bg px-[16px] pt-[12px] pb-[13px]">
            <span className="text-[12px] font-bold text-pending" aria-hidden>
              !
            </span>
            <span className="text-[12px] font-bold text-pending">
              하나 이상 넣어야 저장할 수 있어요
            </span>
          </div>
        )}
      </div>
    </Card>
  )
}
