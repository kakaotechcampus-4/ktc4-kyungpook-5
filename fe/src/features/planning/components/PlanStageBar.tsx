// 1단계 → 2단계 인디케이터. P1·P2가 같은 것을 쓰고 stage만 다르다.
import { Fragment } from 'react'
import { Card } from '@/shared/ui/Card'
import { cn } from '@/shared/lib/cn'
import type { DraftStage } from '@/features/planning/types'

const STAGES = [
  { key: 'CHAT', title: '큰 틀 잡기', subtitle: '챗봇과 대화' },
  { key: 'FLOW', title: '흐름 만들기', subtitle: '단계 배열 · 일정 · 수금 · 공지' },
] as const

export function PlanStageBar({ stage }: { stage: DraftStage }) {
  return (
    <Card className="flex w-full items-center gap-[8px] rounded-[16px] p-[8px]">
      {STAGES.map((item, index) => {
        const active = item.key === stage
        // 2단계에 와 있으면 1단계는 지나온 칸이 된다(체크 표시).
        const done = !active && stage === 'FLOW'

        return (
          <Fragment key={item.key}>
            {index > 0 && (
              <span className="shrink-0 text-[14px] font-medium text-[#b3b3b3]">›</span>
            )}
            <div
              className={cn(
                'flex min-w-px flex-1 items-center gap-[10px] rounded-[12px] px-[18px] py-[12px]',
                active ? 'bg-[#262626]' : 'bg-white',
              )}
            >
              <span
                className={cn(
                  'flex size-[22px] shrink-0 items-center justify-center rounded-[11px] text-[11px] font-bold',
                  active
                    ? 'bg-[#fafafa] text-[#262626]'
                    : done
                      ? 'bg-[#404040] text-[#fafafa]'
                      : 'bg-[#ebebeb] text-[#808080]',
                )}
              >
                {done ? '✓' : index + 1}
              </span>
              <div className="flex flex-col gap-px">
                <p
                  className={cn(
                    'text-[13px] whitespace-nowrap',
                    active
                      ? 'font-semibold text-[#fafafa]'
                      : done
                        ? 'font-medium text-[#404040]'
                        : 'font-medium text-[#808080]',
                  )}
                >
                  {item.title}
                </p>
                <p
                  className={cn(
                    'text-[10.5px] whitespace-nowrap',
                    active ? 'text-[#ccc]' : 'text-[#8c8c8c]',
                  )}
                >
                  {item.subtitle}
                </p>
              </div>
            </div>
          </Fragment>
        )
      })}
    </Card>
  )
}
