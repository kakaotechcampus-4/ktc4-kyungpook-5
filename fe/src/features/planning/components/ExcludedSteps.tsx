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
    <div className="flex w-full shrink-0 flex-col gap-[16px]">
      <Card className="flex flex-col">
        <div className="flex items-center gap-[9px] px-[20px] pt-[18px] pb-[14px]">
          <h2 className="text-h3 text-ink">포함하지 않은 단계</h2>
          <Chip size="sm">{excluded.length}개</Chip>
        </div>
        {excluded.length === 0 && (
          <p className="border-t border-line px-[20px] py-[14px] text-caption text-mute">
            모든 단계를 포함했어요.
          </p>
        )}

        {PHASES.map((phase) => {
          const rows = excluded.filter((s) => s.phase === phase)
          if (rows.length === 0) return null
          return (
            <div key={phase} className="flex flex-col">
              <span className="border-t border-line bg-bg px-[20px] pt-[12px] pb-[9px] text-[11.5px] font-bold text-ink2">
                {phase}
              </span>
              {rows.map((step) => (
                <div
                  key={step.code}
                  className="flex items-center gap-[12px] border-t border-line px-[20px] py-[13px]"
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

      {excluded.length > 0 && (
        <ToriNote title="다시 넣으면 새 단계로 만들어져요">
          이전 일정과 입력은 돌아오지 않아요.
        </ToriNote>
      )}
    </div>
  )
}
