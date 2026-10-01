// P2 우측 아래 세 장 — 경고 / 묶거나 뺀 단계 / 시작 버튼.
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { suggestionLabel, warningMessage } from '@/features/planning/labels'
import type { ExcludedStep, PlanWarning } from '@/features/planning/types'

export function PlanWarningsCard({
  warnings,
  onSuggestion,
}: {
  warnings: PlanWarning[]
  onSuggestion: (index: number) => void
}) {
  if (warnings.length === 0) return null

  return (
    <Card className="flex w-full flex-col gap-[8px] rounded-[16px] p-[20px]">
      <p className="text-[12.5px] font-semibold text-[#262626]">시작 전에 확인하세요</p>
      {warnings.map((warning, index) => {
        const action = suggestionLabel(warning.suggestion)
        return (
          <div key={index} className="flex w-full flex-col items-start gap-[8px]">
            <p className="text-[12px] text-[#4d4d4d]">{warningMessage(warning)}</p>
            {action && (
              <Button variant="secondary" size="pill" onClick={() => onSuggestion(index)}>
                {action}
              </Button>
            )}
          </div>
        )
      })}
    </Card>
  )
}

export function PlanExcludedCard({ steps }: { steps: ExcludedStep[] }) {
  if (steps.length === 0) return null

  return (
    <Card className="flex w-full flex-col gap-[8px] rounded-[16px] p-[20px]">
      {/* 🔸 "13단계"는 묶기 전 단계 수다. 명세 응답에 없어 시안 문구를 그대로 뒀다. */}
      <p className="text-[12.5px] font-semibold text-[#262626]">13단계에서 어디로 갔나</p>
      <div className="flex w-full flex-col">
        {steps.map((step) => (
          <p key={step.name} className="text-[12px] text-[#4d4d4d]">
            {step.name} → {step.reason}
          </p>
        ))}
      </div>
    </Card>
  )
}

export function PlanConfirmCard({ onConfirm }: { onConfirm: () => void }) {
  return (
    <Card className="flex w-full flex-col gap-[10px] rounded-[16px] p-[20px]">
      <Button className="w-full rounded-[20px] px-[13px] py-[12px] text-[12px]" onClick={onConfirm}>
        이 계획으로 행사 시작하기
      </Button>
      <p className="text-[11px] text-[#808080]">
        시작하면 행사 목록에 올라가고, 1번 단계부터 AI가 진행합니다. 계획은 진행 중에도 고칠 수
        있습니다.
      </p>
    </Card>
  )
}
