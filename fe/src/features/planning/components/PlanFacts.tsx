// P1 오른쪽: 대화에서 정해진 것이 쌓이는 자리. 여섯 항목으로 고정이라 화면이 흔들리지 않는다.
import type { PlanFacts as Facts } from '@/features/planning/types'
import { PLAN_FACT_KEYS } from '@/features/planning/types'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { ToriNote } from '@/shared/ui/ToriNote'

// 네 가지 이상 정하면 2단계로 넘어갈 수 있다. 일정·장소는 2단계에서 정해도 된다.
const REQUIRED = 4

interface PlanFactsProps {
  facts: Facts
  // 과거 기록을 봤을 때만 준다.
  reference?: string
  onNext: () => void
}

export function PlanFacts({ facts, reference, onNext }: PlanFactsProps) {
  const decidedCount = PLAN_FACT_KEYS.filter((key) => facts[key]?.decided).length
  const canGoNext = decidedCount >= REQUIRED

  return (
    <div className="flex w-[320px] shrink-0 flex-col gap-[16px]">
      <Card className="flex flex-col gap-[16px] px-[22px] pt-[20px] pb-[22px]">
        <div className="flex items-center justify-between">
          <h2 className="text-h2 text-ink">지금까지 정한 것</h2>
          <Chip tone={canGoNext ? 'approved' : 'neutral'} size="sm">
            {decidedCount} / {PLAN_FACT_KEYS.length}
          </Chip>
        </div>

        {PLAN_FACT_KEYS.map((key) => {
          const fact = facts[key]
          return (
            <div key={key} className="flex items-center justify-between gap-[12px]">
              <span className="flex items-center gap-[9px]">
                <span
                  className={cn(
                    'flex size-[18px] shrink-0 items-center justify-center rounded-full text-[9px] font-bold',
                    fact?.decided ? 'bg-blue-600 text-white' : 'bg-track',
                  )}
                >
                  {fact?.decided ? '✓' : null}
                </span>
                <span className="text-[12px] text-ink2">{key}</span>
              </span>
              <span
                className={cn(
                  'truncate text-[12.5px]',
                  fact?.decided ? 'font-bold text-ink' : 'text-mute',
                )}
              >
                {fact?.value ?? '아직이에요'}
              </span>
            </div>
          )
        })}
      </Card>

      {reference && <ToriNote title="참고한 과거 기록">{reference}</ToriNote>}

      <Card className="flex flex-col gap-[12px] px-[22px] pt-[20px] pb-[22px]">
        <Button size="lg" className="w-full" disabled={!canGoNext} onClick={onNext}>
          다음: 흐름 만들기 →
        </Button>
        <p className="text-[11px] leading-[16px] text-mute">
          {canGoNext
            ? '일정과 장소는 2단계에서 정해도 괜찮아요.'
            : `네 가지 이상 정하면 다음으로 넘어갈 수 있어요.`}
        </p>
      </Card>
    </div>
  )
}
