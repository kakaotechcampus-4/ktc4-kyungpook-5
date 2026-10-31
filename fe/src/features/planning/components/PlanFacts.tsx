// P1 오른쪽: 대화에서 정해진 것이 쌓이는 자리. 여섯 항목으로 고정이라 화면이 흔들리지 않는다.
import type {
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
const BLOCK_TEXT: Record<string, string> = {
  event_type_missing: '행사 종류를 정하면 다음으로 넘어갈 수 있어요.',
  dates_unanswered: '일정을 알려 주거나 아직 미정이라고 말해 주세요.',
  headcount_unanswered: '예상 인원을 알려 주거나 아직 미정이라고 말해 주세요.',
  location_unanswered: '장소를 알려 주거나 아직 미정이라고 말해 주세요.',
  condition_change_pending: '아직 반영하지 못한 조건 변경이 있어요. 먼저 확인해 주세요.',
  // 아래 둘은 서버 사유가 아니라 화면이 붙인다.
  answering: '토리가 답하는 중이에요. 답이 오면 넘어갈 수 있어요.',
  readiness_unknown: '진행 가능 상태를 확인하지 못했어요. 대화를 이어가거나 다시 불러와 주세요.',
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
  // 이미 만든 흐름이 있으면 「다음」은 다시 만들기가 된다. 그때 문구를 바꾸고 흐름 보기를 따로 둔다.
  nextLabel?: string
  onView?: () => void
  onNext: () => void
}

export function PlanFacts({
  facts,
  readiness,
  reference,
  unavailable = false,
  hideNext = false,
  nextLabel = '다음: 흐름 만들기 →',
  onView,
  onNext,
}: PlanFactsProps) {
  const { canGenerate, reasons } = readiness ?? localReadiness(facts)

  return (
    <div className="flex w-full min-w-0 shrink-0 flex-col gap-[16px]">
      <Card className="flex flex-col gap-[16px] px-[22px] pt-[20px] pb-[22px]">
        <h2 className="text-h2 text-ink">지금까지 정한 것</h2>

        {PLAN_FACT_KEYS.map((key) => {
          const fact = facts[key]
          const status = fact?.status ?? '미정'
          const settled = status === '확정' || status === '잠정'
          return (
            <div key={key} className="flex flex-col gap-[4px]">
              <div className="flex items-center justify-between gap-[12px]">
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
                <p className="pl-[27px] text-[11px] leading-[16px] text-mute">「{fact.quote}」</p>
              )}
            </div>
          )
        })}
      </Card>

      {reference && <ToriNote title="참고한 과거 기록">{reference}</ToriNote>}

      {!hideNext && (
        <Card className="flex flex-col gap-[12px] px-[22px] pt-[20px] pb-[22px]">
          {onView && (
            <Button size="lg" className="w-full" onClick={onView}>
              만들어 둔 흐름 보기 →
            </Button>
          )}
          <Button
            size="lg"
            variant={onView ? 'secondary' : 'primary'}
            className="w-full"
            disabled={!canGenerate}
            onClick={onNext}
          >
            {nextLabel}
          </Button>
          <p className="text-[11px] leading-[16px] text-mute">
            {unavailable
              ? '대화로 조건을 확인할 수 있어요. 계획 생성 연결은 준비 중이에요.'
              : !canGenerate
                ? reasons
                    .map((reason) => BLOCK_TEXT[reason])
                    .filter(Boolean)
                    .join(' ') || '대화를 이어서 필요한 정보를 확인해 주세요.'
                : onView
                  ? '다시 만들면 지금 흐름과 고쳐 둔 세부 내용이 새 결과로 바뀌어요.'
                  : '날짜와 인원은 미정이어도 괜찮아요. 2단계에서 정해도 돼요.'}
          </p>
        </Card>
      )}
    </div>
  )
}
