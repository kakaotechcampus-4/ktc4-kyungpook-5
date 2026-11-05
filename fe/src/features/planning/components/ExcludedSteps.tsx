// P2-b 오른쪽: 포함하지 않은 단계가 모이는 곳. 묶음별로 나뉘어 쌓이고 + 로 다시 넣는다.
import type { CatalogueStep } from '@/features/planning/catalogue'
import { PHASES } from '@/features/planning/catalogue'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { ToriNote } from '@/shared/ui/ToriNote'

interface ExcludedStepsProps {
  excluded: CatalogueStep[]
  onInclude: (code: string) => void
}

export function ExcludedSteps({ excluded, onInclude }: ExcludedStepsProps) {
  return (
    <div className="flex w-full shrink-0 flex-col gap-[16px] lg:w-[300px]">
      <Card className="flex flex-col">
        <div className="flex flex-col gap-[9px] px-[22px] pt-[22px] pb-[16px]">
          <span className="flex items-center gap-[9px]">
            <h2 className="text-h3 text-ink">포함하지 않은 단계</h2>
            <Chip size="sm">{excluded.length}개</Chip>
          </span>
          <p className="text-[11px] leading-[16px] text-mute">
            단계 목록은 13개로 고정돼 있어요. 포함하지 않은 단계가 여기 모입니다.
          </p>
        </div>

        {PHASES.map((phase) => {
          const rows = excluded.filter((s) => s.phase === phase)
          if (rows.length === 0) return null
          return (
            <div key={phase} className="flex flex-col">
              <span className="border-t border-line bg-bg px-[22px] pt-[12px] pb-[9px] text-[11.5px] font-bold text-ink2">
                {phase}
              </span>
              {rows.map((step) => (
                <div
                  key={step.code}
                  className="flex items-center gap-[12px] border-t border-line px-[22px] py-[13px]"
                >
                  <button
                    type="button"
                    aria-label={`${step.name} 다시 포함`}
                    onClick={() => onInclude(step.code)}
                    className="min-h-11 shrink-0 rounded-[7px] bg-blue-100 px-[8px] py-[7px] text-[12px] font-bold text-blue-700 hover:bg-blue-200"
                  >
                    다시 포함
                  </button>
                  <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                    <span className="text-[13px] font-bold text-ink">{step.name}</span>
                    <span className="text-[10.5px] text-mute">
                      {step.actor} · {step.actions}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          )
        })}
      </Card>

      <ToriNote title="다시 포함하면 새 단계로 만들어요">
        기본 작업이 새로 만들어져요. 이전 일정과 입력은 복원되지 않으니 구성 저장 후 확인해 주세요.
      </ToriNote>
    </div>
  )
}
