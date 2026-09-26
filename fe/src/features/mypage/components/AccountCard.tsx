import { Card } from '@/shared/ui/Card'

const ROWS = [
  { label: '비밀번호 변경' },
  { label: '연결된 계정', detail: 'Google · 카카오' },
  { label: '로그아웃' },
  { label: '탈퇴', muted: true },
]

export function AccountCard() {
  return (
    <Card className="flex w-full flex-col items-start">
      <div className="flex w-full items-start px-[24px] py-[16px]">
        <p className="text-[14.5px] font-semibold text-[#242424]">계정</p>
      </div>
      {ROWS.map((row) => (
        <div key={row.label} className="w-full">
          <div className="h-px w-full bg-[#ededed]" />
          <button type="button" className="flex w-full items-center gap-[12px] px-[24px] py-[14px] text-left hover:bg-[#fafafa]">
            <p className={`text-[12.5px] ${row.muted ? 'text-[#808080]' : 'text-[#383838]'}`}>{row.label}</p>
            <div className="h-px flex-1" />
            {row.detail && <p className="text-[11.5px] text-[#808080]">{row.detail}</p>}
            <p className="text-[13px] font-medium text-[#8c8c8c]">›</p>
          </button>
        </div>
      ))}
    </Card>
  )
}
