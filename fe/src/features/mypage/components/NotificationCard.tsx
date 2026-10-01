import { Card } from '@/shared/ui/Card'
import { Switch } from '@/shared/ui/Switch'
import type { NotificationSettings } from '@/features/mypage/types'

const ROWS: { key: keyof NotificationSettings; title: string; description: string }[] = [
  { key: 'onApprovalRequest', title: '승인 요청이 올라왔을 때', description: '되돌릴 수 없는 작업만 알립니다' },
  { key: 'onDeadlineApproaching', title: '마감이 다가올 때', description: '회비 납부·계약금 등 D-2에 한 번' },
  { key: 'onAgentAutoHandled', title: '에이전트가 알아서 처리했을 때', description: '하루치를 모아 저녁에 한 번' },
]

interface NotificationCardProps {
  settings: NotificationSettings
  contactLabel: string
  onToggle: (key: keyof NotificationSettings, value: boolean) => void
}

export function NotificationCard({ settings, contactLabel, onToggle }: NotificationCardProps) {
  return (
    <Card className="flex w-full flex-col items-start">
      <div className="flex w-full items-center gap-[8px] px-[24px] py-[16px]">
        <p className="text-[14.5px] font-semibold text-[#242424]">알림</p>
        <div className="h-px flex-1" />
        <p className="text-[11.5px] text-[#737373]">{contactLabel}</p>
      </div>
      {ROWS.map((row) => (
        <div key={row.key} className="w-full">
          <div className="h-px w-full bg-[#ededed]" />
          <div className="flex w-full items-center gap-[14px] px-[24px] py-[14px]">
            <div className="flex flex-col gap-[2px]">
              <p className="text-[12.5px] font-medium text-[#333]">{row.title}</p>
              <p className="text-[11px] text-[#7a7a7a]">{row.description}</p>
            </div>
            <div className="h-px flex-1" />
            <Switch checked={settings[row.key]} onChange={(value) => onToggle(row.key, value)} label={row.title} />
          </div>
        </div>
      ))}
    </Card>
  )
}
