import { Card } from '@/shared/ui/Card'
import type { ClubInfo } from '@/features/mypage/types'

export function ClubInfoCard({ clubInfo }: { clubInfo: ClubInfo }) {
  const rows = [
    { label: '동아리 이름', value: clubInfo.name },
    { label: '분과', value: clubInfo.division },
    { label: '내 역할', value: clubInfo.myRole },
    { label: '운영진', value: `${clubInfo.officerCount}명` },
  ]

  return (
    <Card className="flex w-full flex-col items-start">
      <div className="flex w-full items-center gap-[8px] px-[22px] py-[16px]">
        <p className="text-[13.5px] font-semibold text-[#242424]">소속 동아리</p>
        <div className="h-px flex-1" />
        <button type="button" className="text-[11.5px] font-medium text-[#6b6b6b] hover:underline">
          전환
        </button>
      </div>
      <div className="h-px w-full bg-[#ededed]" />
      <div className="flex w-full flex-col gap-[9px] px-[22px] py-[16px]">
        {rows.map((row) => (
          <div key={row.label} className="flex w-full items-center gap-[10px]">
            <p className="w-[72px] text-[11.5px] text-[#737373]">{row.label}</p>
            <p className="text-[12px] font-medium text-[#333]">{row.value}</p>
          </div>
        ))}
      </div>
      <div className="h-px w-full bg-[#ededed]" />
      <button type="button" className="flex w-full items-center px-[22px] py-[14px] text-left hover:bg-[#fafafa]">
        <p className="text-[12px] font-medium text-[#4d4d4d]">동아리 정보 수정</p>
        <div className="h-px flex-1" />
        <p className="text-[13px] font-medium text-[#8c8c8c]">›</p>
      </button>
    </Card>
  )
}
