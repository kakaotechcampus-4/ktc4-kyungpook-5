// M1 메인 — 조립만 한다. 로직은 features/ 로.
import { ApprovalCarouselCard } from '@/features/dashboard/components/ApprovalCarouselCard'
import { BudgetForecastCard } from '@/features/dashboard/components/BudgetForecastCard'
import { EmptyBudgetForecastCard } from '@/features/dashboard/components/EmptyBudgetForecastCard'
import { useDashboard } from '@/features/dashboard/hooks'

export default function M1DashboardPage() {
  const dashboard = useDashboard()

  return (
    <div className="flex w-full flex-col gap-[18px] px-[26px] pt-[22px] pb-[30px]">
      <div className="flex w-full items-center gap-[10px]">
        <div className="flex flex-col gap-[2px]">
          <p className="text-[20px] font-bold text-[#212121]">AI 비서</p>
          <p className="text-[12.5px] text-[#737373]">행사는 알아서 굴러갑니다. 승인만 눌러주세요.</p>
        </div>
      </div>

      <ApprovalCarouselCard
        events={dashboard.events}
        index={dashboard.index}
        onPrev={dashboard.goPrev}
        onNext={dashboard.goNext}
        onApprove={dashboard.handleApprove}
        onDeny={dashboard.handleDeny}
        onApproveAll={dashboard.handleApproveAll}
      />

      {dashboard.forecast.hasHistory ? (
        <BudgetForecastCard forecast={dashboard.forecast} />
      ) : (
        <EmptyBudgetForecastCard />
      )}
    </div>
  )
}
