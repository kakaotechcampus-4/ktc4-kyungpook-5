import { Card } from '@/shared/ui/Card'
import { formatCurrency, formatSignedCurrency } from '@/shared/lib/format'
import { BudgetChart } from '@/features/dashboard/components/BudgetChart'
import type { BudgetForecast } from '@/features/dashboard/types'

const STATUS_LABEL: Record<string, string> = {
  confirmed: '확정',
  pending: '승인 대기',
  expected: '예상',
}

function lastActualIndex(values: (number | null)[]): number {
  let last = 0
  values.forEach((v, i) => {
    if (v != null) last = i
  })
  return last
}

export function BudgetForecastCard({ forecast }: { forecast: BudgetForecast }) {
  return (
    <Card className="flex w-full flex-col gap-[20px] p-[26px]">
      <div className="flex w-full items-center gap-[10px]">
        <div className="flex flex-col gap-[2px]">
          <p className="text-[17px] font-bold text-[#212121]">예산 전망</p>
          <p className="text-[12px] text-[#737373]">확정된 잔고는 막대로, 예측은 선으로 나눠 표시합니다</p>
        </div>
        <div className="h-px flex-1" />
        <span className="rounded-[6px] border border-[#e3e3e3] bg-[#f9f9f9] px-[8px] py-[4px] text-[10.5px] font-medium text-[#666]">
          예측 기준 · 과거 행사 평균
        </span>
        <button
          type="button"
          className="rounded-[20px] border border-[#dbdbdb] bg-white px-[12px] py-[7px] text-[12px] font-medium text-[#525252] hover:bg-[#f7f7f7]"
        >
          기준 바꾸기
        </button>
      </div>

      <div className="flex w-full items-start gap-[26px]">
        <div className="flex w-[300px] shrink-0 flex-col gap-[14px]">
          <div className="flex flex-col gap-[4px]">
            <p className="text-[11.5px] font-medium text-[#6b6b6b]">오늘 기준 확정 잔고</p>
            <p className="text-[30px] font-bold text-[#1c1c1c]">{formatCurrency(forecast.confirmedBalance)}</p>
            <p className="w-[280px] text-[11px] text-[#808080]">{forecast.confirmedBalanceNote}</p>
          </div>
          <div className="h-px w-full bg-[#ebebeb]" />
          <div className="flex w-full flex-col gap-[10px]">
            <p className="text-[11.5px] font-medium text-[#6b6b6b]">행사가 끝났을 때 (예측)</p>
            <div className="flex w-full items-center gap-[9px]">
              <span className="h-[3px] w-[18px] bg-[#383838]" />
              <span className="text-[11.5px] text-[#4d4d4d]">현재 계획대로 진행하면</span>
              <div className="h-px flex-1" />
              <span className="text-[13.5px] font-semibold text-[#262626]">{formatCurrency(forecast.planExpected)}</span>
            </div>
            <div className="flex w-full items-center gap-[9px]">
              <span className="h-[3px] w-[18px] bg-[#949494]" />
              <span className="text-[11.5px] text-[#4d4d4d]">과거 행사 평균대로라면</span>
              <div className="h-px flex-1" />
              <span className="text-[13.5px] font-semibold text-[#262626]">{formatCurrency(forecast.historicalExpected)}</span>
            </div>
            <div className="w-full rounded-[10px] bg-[#f8f8f8] px-[12px] py-[10px] text-[11px] text-[#595959]">
              {forecast.diffNote}
            </div>
          </div>
          <div className="h-px w-full bg-[#ebebeb]" />
          <div className="flex w-full flex-col gap-[8px]">
            <p className="text-[11.5px] font-semibold text-[#666]">예정된 입출금</p>
            {forecast.upcomingTransactions.map((tx) => (
              <div key={tx.id} className="flex w-full items-center gap-[8px]">
                <span className="w-[34px] text-[11px] text-[#808080]">{tx.date}</span>
                <div className="flex flex-col">
                  <span className="text-[12px] text-[#404040]">{tx.label}</span>
                  <span className="text-[10px] text-[#8c8c8c]">{STATUS_LABEL[tx.statusLabel]}</span>
                </div>
                <div className="h-px flex-1" />
                <span className={tx.statusLabel === 'expected' ? 'text-[12px] font-medium text-[#737373]' : 'text-[12px] font-medium text-[#2e2e2e]'}>
                  {formatSignedCurrency(tx.amount)}
                </span>
              </div>
            ))}
          </div>
        </div>

        <BudgetChart data={forecast.chart} todayIndex={lastActualIndex(forecast.chart.actualBalances)} />
      </div>
    </Card>
  )
}
