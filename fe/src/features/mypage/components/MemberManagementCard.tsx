import { Avatar } from '@/shared/ui/Avatar'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import type { JoinRequest, OfficerRow } from '@/features/mypage/types'

interface MemberManagementCardProps {
  joinRequests: JoinRequest[]
  officers: OfficerRow[]
  onResolveJoinRequest: (id: string) => void
}

export function MemberManagementCard({ joinRequests, officers, onResolveJoinRequest }: MemberManagementCardProps) {
  return (
    <Card className="flex w-full flex-col items-start">
      <div className="flex w-full items-center gap-[8px] px-[22px] py-[15px]">
        <p className="text-[13.5px] font-semibold text-[#242424]">구성원 관리</p>
        <Chip variant="subtle">대표만 보임</Chip>
      </div>
      <div className="h-px w-full bg-[#ededed]" />

      {joinRequests.length > 0 && (
        <>
          <div className="flex w-full flex-col gap-[10px] bg-[#f9f9f9] px-[22px] py-[14px]">
            <p className="text-[12.5px] font-semibold text-[#262626]">참여 요청 {joinRequests.length}건</p>
            <p className="w-[280px] text-[11px] text-[#737373]">허가해야 동아리 자료와 행사에 접근할 수 있습니다.</p>
            {joinRequests.map((request) => (
              <div key={request.id} className="flex w-full flex-col gap-[8px] rounded-[10px] border border-[#e0e0e0] bg-white px-[12px] py-[11px]">
                <div className="flex w-full items-center gap-[9px]">
                  <Avatar name={request.name} />
                  <div className="flex flex-col gap-px">
                    <p className="text-[12px] font-medium text-[#333]">{request.name}</p>
                    <p className="text-[10.5px] text-[#808080]">{request.email}</p>
                  </div>
                </div>
                <div className="flex w-full items-start gap-[7px]">
                  <Button size="pill" onClick={() => onResolveJoinRequest(request.id)}>
                    허가
                  </Button>
                  <Button variant="secondary" size="pill" onClick={() => onResolveJoinRequest(request.id)}>
                    거절
                  </Button>
                  <div className="h-px flex-1" />
                  <p className="text-[10.5px] font-medium text-[#737373]">권한 선택 ▾</p>
                </div>
              </div>
            ))}
          </div>
          <div className="h-px w-full bg-[#ededed]" />
        </>
      )}

      <div className="flex w-full items-center gap-[8px] px-[22px] py-[13px]">
        <p className="text-[12px] font-semibold text-[#4d4d4d]">임원 {officers.length}명</p>
        <div className="h-px flex-1" />
        <button type="button" className="text-[11px] font-medium text-[#6b6b6b] hover:underline">
          + 초대
        </button>
      </div>

      {officers.map((officer) => (
        <div key={officer.id} className="w-full">
          <div className="h-px w-full bg-[#ededed]" />
          <div className="flex w-full items-center gap-[10px] px-[22px] py-[11px]">
            <Avatar name={officer.name} size="sm" emphasis={officer.isMe} />
            <div className="flex flex-col gap-px">
              <p className="text-[12px] font-medium text-[#333]">
                {officer.name}
                {officer.isMe && ' (나)'}
              </p>
              <p className="text-[10.5px] text-[#808080]">{officer.role}</p>
            </div>
            <div className="h-px flex-1" />
            <Chip variant={officer.canBulkApprove ? 'subtle' : 'outline'}>
              {officer.canBulkApprove ? '전체 승인' : '승인 불가'}
            </Chip>
          </div>
        </div>
      ))}
    </Card>
  )
}
