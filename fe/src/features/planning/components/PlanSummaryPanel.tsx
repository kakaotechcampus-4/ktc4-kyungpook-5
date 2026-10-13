// P2 오른쪽: 이 계획이 어떤 모양인지 한눈에. 일곱 줄로 고정이라 계획이 바뀌어도 자리가 안 흔들린다.
import type { PlanSummary, PlanWarning } from '@/features/planning/types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ToriNote } from '@/shared/ui/ToriNote'

interface PlanSummaryPanelProps {
  summary: PlanSummary
  // 일정이 비었거나 단계가 겹칠 때만 온다.
  warning?: PlanWarning
  onFixSteps: () => void
  onStart: () => void
}

export function PlanSummaryPanel({ summary, warning, onFixSteps, onStart }: PlanSummaryPanelProps) {
  // 승인 필요만 파랗게 둔다. 운영진이 직접 손대야 하는 횟수라 제일 먼저 보여야 한다.
  const rows: Array<[string, string, boolean?]> = [
    ['전체 단계', `${summary.totalSteps}개`],
    ['AI 실행', `${summary.aiSteps}개`],
    ['승인 필요', `${summary.approvalSteps}곳`, true],
    ['직접 수행', `${summary.manualSteps}개`],
    ['수금', summary.collect],
    ['공지', summary.notice],
    ['기간', summary.period],
  ]

  return (
    <div className="flex w-[300px] shrink-0 flex-col gap-[16px]">
      <Card className="flex flex-col gap-[14px] px-[22px] pt-[20px] pb-[22px]">
        <h2 className="text-h2 text-ink">이 계획 요약</h2>
        {rows.map(([label, value, highlight]) => (
          <div key={label} className="flex items-center justify-between gap-[12px]">
            <span className="text-[12px] text-ink2">{label}</span>
            <span
              className={
                highlight ? 'text-[13px] font-bold text-blue-700' : 'text-[13px] font-bold text-ink'
              }
            >
              {value}
            </span>
          </div>
        ))}
      </Card>

      {warning && (
        <ToriNote title={warning.title}>
          <span className="flex flex-col gap-[12px]">
            <span>{warning.body}</span>
            <Button variant="secondary" size="sm" className="w-full" onClick={onFixSteps}>
              {warning.actionLabel}
            </Button>
          </span>
        </ToriNote>
      )}

      <Card className="flex flex-col gap-[12px] px-[22px] pt-[20px] pb-[22px]">
        <Button size="lg" className="w-full" onClick={onStart}>
          이 계획으로 행사 시작하기
        </Button>
        <p className="text-[11px] leading-[16px] text-mute">
          시작하면 행사 목록에 올라가고, 1번 단계부터 토리가 진행합니다. 계획은 진행 중에도 고칠 수
          있어요.
        </p>
      </Card>
    </div>
  )
}
