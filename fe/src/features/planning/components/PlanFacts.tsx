// P1 오른쪽: 대화에서 정해진 것이 쌓이는 자리. 여섯 항목으로 고정이라 화면이 흔들리지 않는다.
import { useEffect, useState } from 'react'
import { flashLeft, type FactFlash } from '@/features/planning/factFlash'
import type {
  GenerationBlockReason,
  GenerationReadiness,
  PlanFactStatus,
  PlanFacts as Facts,
} from '@/features/planning/types'
import { PLAN_FACT_KEYS } from '@/features/planning/types'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { ToriNote } from '@/shared/ui/ToriNote'

// 막힌 이유를 그대로 보여준다. 모르는 사유가 와도 버튼만 잠그고 문구는 비운다.
const BLOCK_TEXT: Record<GenerationBlockReason, string> = {
  event_type_missing: '행사 종류를 정하면 다음으로 넘어갈 수 있어요.',
  condition_change_pending: '아직 반영하지 못한 조건 변경이 있어요. 먼저 확인해 주세요.',
}

// 서버(generation_readiness)가 정할 값이다. 연동 전까지 쓰는 같은 규칙의 임시 계산으로,
// 행사 종류만 있으면 넘어갈 수 있다 — 날짜·인원이 미정이어도 괜찮다.
function localReadiness(facts: Facts): GenerationReadiness {
  const hasType = Boolean(facts['종류']?.value)
  return { canGenerate: hasType, reasons: hasType ? [] : ['event_type_missing'] }
}

function Mark({ status }: { status: PlanFactStatus }) {
  if (status === '확정') {
    return (
      <span className="flex size-[18px] shrink-0 items-center justify-center rounded-full bg-blue-600 text-[9px] font-bold text-white">
        ✓
      </span>
    )
  }
  if (status === '잠정') {
    return (
      <span className="flex size-[18px] shrink-0 items-center justify-center rounded-full border-[1.5px] border-blue-300 bg-card text-[9px] font-bold text-blue-600">
        ~
      </span>
    )
  }
  return <span className="size-[18px] shrink-0 rounded-full bg-track" />
}

interface PlanFactsProps {
  facts: Facts
  // 서버가 내려주는 생성 가능 여부. 없으면 같은 규칙으로 화면이 임시 계산한다.
  readiness?: GenerationReadiness
  // 과거 기록을 봤을 때만 준다.
  reference?: string
  unavailable?: boolean
  hideNext?: boolean
  onNext: () => void
  // 방금 저장된 대화로 바뀐 칸(#300). 그 칸만 옅은 파란 배경이 잠시 켜졌다 사라진다.
  flash?: FactFlash | null
}

// 강조가 켜져 있는 동안의 값. 남은 시간이 지나면 비워 다시 그릴 때 지난 강조가 켜지지 않게 한다.
function useActiveFlash(flash: FactFlash | null | undefined): FactFlash | null {
  const [active, setActive] = useState<FactFlash | null>(null)
  useEffect(() => {
    const left = flashLeft(flash, Date.now())
    if (!flash || !left) return
    setActive(flash)
    const timer = setTimeout(() => setActive((now) => (now === flash ? null : now)), left)
    return () => clearTimeout(timer)
  }, [flash])
  return active
}

export function PlanFacts({
  facts,
  readiness,
  reference,
  unavailable = false,
  hideNext = false,
  onNext,
  flash,
}: PlanFactsProps) {
  const { canGenerate, reasons } = readiness ?? localReadiness(facts)
  const active = useActiveFlash(flash)

  return (
    <div className="flex w-full min-w-0 shrink-0 flex-col gap-[16px]">
      <Card className="flex flex-col gap-[16px] px-[22px] pt-[20px] pb-[22px]">
        <h2 className="text-h2 text-ink">지금까지 정한 것</h2>

        {/* 줄마다 위아래 5px을 둬 강조 배경이 글자에 붙지 않게 하고, 그만큼 줄 간격과 바깥 여백을 줄여
            강조가 없을 때의 간격은 예전(16px)과 같다. */}
        <div className="-my-[5px] flex flex-col gap-[6px]">
          {PLAN_FACT_KEYS.map((key) => {
            const fact = facts[key]
            const status = fact?.status ?? '미정'
            const settled = status === '확정' || status === '잠정'
            const flashing = active?.keys.includes(key)
            return (
              <div key={key} className="relative flex flex-col gap-[4px] py-[5px]">
                {/* 바뀐 칸 강조. 카드 안쪽 여백까지 살짝 넓혀 줄 전체가 한 칸으로 보이게 한다.
                  at이 바뀌면 새로 그려 같은 칸이 연달아 바뀌어도 처음부터 다시 켜진다.
                  움직임 줄이기면 사라지는 움직임 없이 그 시간 동안 색만 두었다가 끈다. */}
                {flashing && (
                  <span
                    key={active!.at}
                    aria-hidden
                    className="pointer-events-none absolute inset-y-0 -inset-x-[10px] rounded-[8px] bg-blue-100 animate-fact-flash motion-reduce:animate-none"
                  />
                )}
                <div className="relative flex items-center justify-between gap-[12px]">
                  <span className="flex items-center gap-[9px]">
                    <Mark status={status} />
                    <span className="text-[12px] text-ink2">{key}</span>
                  </span>
                  <span className="flex min-w-0 items-center gap-[6px]">
                    <span
                      className={cn(
                        'truncate text-[12.5px]',
                        settled ? 'font-bold text-ink' : 'text-mute',
                      )}
                    >
                      {fact?.value ?? (status === '나중에' ? '나중에 정해요' : '아직이에요')}
                    </span>
                    {status === '잠정' && (
                      <Chip tone="approved" size="sm">
                        잠정
                      </Chip>
                    )}
                    {status === '나중에' && (
                      <Chip tone="neutral" size="sm">
                        나중에
                      </Chip>
                    )}
                  </span>
                </div>
                {/* 잠정으로 본 근거. 운영진이 「내가 그렇게 말했나」를 바로 확인할 수 있게 둔다. */}
                {status === '잠정' && fact?.quote && (
                  <p className="relative pl-[27px] text-[11px] leading-[16px] text-mute">
                    「{fact.quote}」
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </Card>

      {reference && <ToriNote title="참고한 과거 기록">{reference}</ToriNote>}

      {!hideNext && (
        <Card className="flex flex-col gap-[12px] px-[22px] pt-[20px] pb-[22px]">
          <Button size="lg" className="w-full" disabled={!canGenerate} onClick={onNext}>
            다음: 흐름 만들기 →
          </Button>
          <p className="text-[11px] leading-[16px] text-mute">
            {unavailable
              ? '대화로 조건을 확인할 수 있어요. 계획 생성 연결은 준비 중이에요.'
              : canGenerate
                ? '날짜와 인원은 미정이어도 괜찮아요. 2단계에서 정해도 돼요.'
                : reasons.map((reason) => BLOCK_TEXT[reason]).join(' ')}
          </p>
        </Card>
      )}
    </div>
  )
}
