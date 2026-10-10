// S2 · 동아리원 탭. 명단은 역할(임원/동아리원)로만 나누고, 계정이 있는지는 행의 칸으로 보인다.
// 그래서 계정이 없는 사람도 임원에 넣을 수 있다.
import type { AccountStatus, JoinRequest, Member, MemberGroup } from '@/features/mypage/types'
import { Avatar } from '@/shared/ui/Avatar'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { EmptyState } from '@/shared/ui/EmptyState'
import { Tori } from '@/shared/ui/Tori'

const ACCOUNT: Record<AccountStatus, { label: string; tone: 'done' | 'pending' | 'neutral' }> = {
  JOINED: { label: '계정 있음', tone: 'done' },
  INVITED: { label: '가입 대기', tone: 'pending' },
  NONE: { label: '계정 없음', tone: 'neutral' },
}

const GROUP_NOTE: Record<MemberGroup, string> = {
  임원: '승인과 계획을 맡습니다',
  동아리원: '행사 참가·미납 집계에 쓰입니다',
}

function MemberRow({ member }: { member: Member }) {
  const account = ACCOUNT[member.account]
  return (
    <div className="flex items-center gap-[16px] border-t border-line px-[26px] py-[14px]">
      <Avatar name={member.name} size={30} />
      <div className="flex w-[190px] shrink-0 flex-col gap-[2px]">
        <span className="text-[13.5px] font-bold text-ink">{member.name}</span>
        <span className="text-[11px] text-mute">{member.subtitle}</span>
      </div>
      <span
        className={
          member.contact ? 'flex-1 text-[12.5px] text-ink2' : 'flex-1 text-[12.5px] text-mute'
        }
      >
        {member.contact ?? '연락처 없음'}
      </span>
      <span className="flex w-[210px] shrink-0 items-center gap-[9px]">
        <Chip tone={account.tone} size="sm">
          {account.label}
        </Chip>
        <span className="text-[11.5px] text-mute">
          {member.accountNote ?? (member.account === 'NONE' ? '명단에만 있음' : '')}
        </span>
      </span>
      <button type="button" aria-label="더 보기" className="text-[13px] text-mute hover:text-ink2">
        ⋯
      </button>
    </div>
  )
}

function GroupHead({ group, count }: { group: MemberGroup; count: number }) {
  return (
    <div className="flex items-center justify-between gap-[9px] border-t border-line bg-bg px-[26px] pt-[15px] pb-[11px]">
      <span className="flex items-center gap-[8px]">
        <span className="text-[13.5px] font-bold text-ink">{group}</span>
        <Chip size="sm">{count}명</Chip>
      </span>
      <span className="text-[11px] text-mute">{GROUP_NOTE[group]}</span>
    </div>
  )
}

interface MembersTabProps {
  members: Member[]
  requests: JoinRequest[]
  // 명단 전체 수. 목록에는 앞 몇 명만 보인다.
  total: number
  onAddClick: () => void
  onResolveRequest: (id: string) => void
}

export function MembersTab({
  members,
  requests,
  total,
  onAddClick,
  onResolveRequest,
}: MembersTabProps) {
  const groups: MemberGroup[] = ['임원', '동아리원']
  const hidden = total - members.length

  return (
    <div className="flex flex-col gap-[20px]">
      {requests.map((request) => (
        <Card key={request.id} className="border-blue-200 bg-blue-50 px-[26px] py-[20px]">
          <div className="flex items-center justify-between gap-[14px]">
            <div className="flex items-center gap-[13px]">
              <Tori size={38} />
              <div className="flex flex-col gap-[3px]">
                <span className="text-[14.5px] font-bold text-blue-700">
                  참여 요청 {requests.length}건
                </span>
                <span className="text-[12px] text-blue-700">
                  {request.name} 님이 {request.role}으로 참여를 요청했어요 · {request.requestedAt}
                </span>
              </div>
            </div>
            {/* TODO(연동): POST /join-requests/{id}/approve · /deny */}
            <div className="flex gap-[8px]">
              <Button variant="secondary" onClick={() => onResolveRequest(request.id)}>
                거절
              </Button>
              <Button onClick={() => onResolveRequest(request.id)}>허가하기</Button>
            </div>
          </div>
        </Card>
      ))}

      <Card className="flex flex-col">
        <div className="flex flex-col gap-[10px] px-[26px] pt-[24px] pb-[18px]">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-[9px]">
              <h2 className="text-h2 text-ink">동아리원</h2>
              <Chip tone="approved">{total}명</Chip>
            </span>
            <Button onClick={onAddClick}>+ 직접 추가</Button>
          </div>
          <p className="text-[12px] leading-[18px] text-mute">
            계정이 없어도 명단에 넣을 수 있어요. 계정이 있어야 로그인해서 승인과 계획을 할 수
            있습니다.
          </p>
        </div>

        {groups.map((group) => {
          const rows = members.filter((m) => m.group === group)
          return (
            <div key={group} className="flex flex-col">
              <GroupHead group={group} count={rows.length} />
              {rows.length > 0 ? (
                rows.map((member) => <MemberRow key={member.id} member={member} />)
              ) : (
                <div className="border-t border-line px-[26px] pt-[18px] pb-[24px]">
                  <EmptyState
                    variant="inline"
                    title="아직 등록한 동아리원이 없어요"
                    desc="명단이 있어야 행사 참가와 미납을 집계해 드릴 수 있어요."
                  />
                </div>
              )}
            </div>
          )
        })}

        {hidden > 0 && (
          <button
            type="button"
            className="border-t border-line py-[15px] text-[12px] font-medium text-blue-700 hover:bg-bg"
          >
            {hidden}명 더 보기 ▾
          </button>
        )}
      </Card>
    </div>
  )
}
