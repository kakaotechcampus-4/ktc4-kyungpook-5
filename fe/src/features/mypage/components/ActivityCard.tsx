import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import type { ActivityLogItem, ActivityStats } from '@/features/mypage/types'

const STAT_ITEMS = (stats: ActivityStats) => [
  { label: '내가 승인한 건', value: `${stats.approvedCount}건` },
  { label: '확인 요청 처리', value: `${stats.confirmationCount}건` },
  { label: '참여 중인 행사', value: `${stats.activeEventCount}건` },
  { label: '내가 만든 계획', value: `${stats.createdPlanCount}건` },
]

export function ActivityCard({ stats, log }: { stats: ActivityStats; log: ActivityLogItem[] }) {
  return (
    <Card className="flex w-full flex-col gap-[16px] p-[24px]">
      <div className="flex w-full items-center gap-[8px]">
        <p className="text-[14.5px] font-semibold text-[#242424]">내 활동</p>
        <div className="h-px flex-1" />
        <p className="text-[11.5px] text-[#737373]">{stats.periodLabel}</p>
      </div>

      <div className="flex w-full gap-[14px]">
        {STAT_ITEMS(stats).map((item) => (
          <div key={item.label} className="flex flex-1 flex-col gap-[4px] rounded-[12px] bg-[#f8f8f8] px-[16px] py-[14px]">
            <p className="text-[11px] text-[#737373]">{item.label}</p>
            <p className="text-[19px] font-bold text-[#212121]">{item.value}</p>
          </div>
        ))}
      </div>

      <div className="flex w-full flex-col">
        {log.map((item) => (
          <div key={item.id}>
            <div className="h-px w-full bg-[#ededed]" />
            <div className="flex w-full items-center gap-[12px] py-[12px]">
              <p className="text-[12.5px] text-[#404040]">{item.description}</p>
              <div className="h-px flex-1" />
              <Chip variant="subtle">{item.statusLabel}</Chip>
              <p className="text-[11px] text-[#808080]">{item.timestamp}</p>
            </div>
          </div>
        ))}
        <div className="h-px w-full bg-[#ededed]" />
        <button
          type="button"
          className="flex w-full items-center justify-center py-[12px] text-[11.5px] font-medium text-[#6b6b6b] hover:underline"
        >
          내 승인 기록 전체 보기 ›
        </button>
      </div>
    </Card>
  )
}
