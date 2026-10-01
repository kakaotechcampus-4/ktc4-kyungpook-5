import { Link } from 'react-router-dom'
import { Card } from '@/shared/ui/Card'
import type { ClubRecordSummary } from '@/features/mypage/types'

export function ClubRecordsCard({ summary }: { summary: ClubRecordSummary }) {
  const rows = [
    { label: '장부', value: `${summary.ledgerCount}건` },
    { label: '행사 기록', value: `${summary.eventRecordCount}건` },
    { label: '회칙 문서', value: summary.hasBylaws ? '있음' : '없음' },
  ]

  return (
    <Card className="flex w-full flex-col gap-[12px] p-[22px]">
      <p className="text-[13.5px] font-semibold text-[#242424]">동아리 자료</p>
      <p className="w-[290px] text-[12px] text-[#595959]">
        회칙, 판단 기준, 지난 장부와 행사 기록은 동아리 기록에서 관리합니다.
      </p>
      <div className="flex w-full flex-col gap-[7px]">
        {rows.map((row) => (
          <div key={row.label} className="flex w-full items-center gap-[8px]">
            <p className="text-[11.5px] text-[#737373]">{row.label}</p>
            <div className="h-px flex-1" />
            <p className="text-[11.5px] font-medium text-[#4d4d4d]">{row.value}</p>
          </div>
        ))}
      </div>
      <Link
        to="/records"
        className="w-full rounded-[20px] border border-[#262626] bg-[#262626] px-[13px] py-[11px] text-center text-[12px] font-medium text-[#fafafa] hover:bg-[#1a1a1a]"
      >
        동아리 기록으로 이동
      </Link>
    </Card>
  )
}
