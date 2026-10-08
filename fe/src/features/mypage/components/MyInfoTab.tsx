// S2 · 내 정보 탭. 왼쪽에 프로필·동아리·계정, 오른쪽에 알림.
import { useState } from 'react'
import type { ClubInfo, NotificationSettings, Profile } from '@/features/mypage/types'
import { Avatar } from '@/shared/ui/Avatar'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Switch } from '@/shared/ui/Switch'
import { ToriNote } from '@/shared/ui/ToriNote'

// 누르면 다른 곳으로 가거나 창이 열리는 줄. 오른쪽에 현재 값을 덧붙일 수 있다.
function LinkRow({ label, value, danger }: { label: string; value?: string; danger?: boolean }) {
  return (
    <button
      type="button"
      className="flex items-center justify-between border-t border-line px-[26px] py-[15px] text-left first:border-t-0 hover:bg-bg"
    >
      <span className={danger ? 'text-[12.5px] text-mute' : 'text-[12.5px] font-medium text-ink'}>
        {label}
      </span>
      <span className="flex items-center gap-[10px]">
        {value && <span className="text-[11.5px] text-mute">{value}</span>}
        <span className="text-[12px] text-mute" aria-hidden>
          ›
        </span>
      </span>
    </button>
  )
}

function Facts({ items }: { items: Array<[string, string]> }) {
  return (
    <div className="flex flex-wrap gap-x-[36px] gap-y-[12px]">
      {items.map(([label, value]) => (
        <span key={label} className="flex flex-col gap-[4px]">
          <span className="text-[10.5px] font-medium text-mute">{label}</span>
          <span className="text-[13.5px] font-bold text-ink">{value}</span>
        </span>
      ))}
    </div>
  )
}

interface MyInfoTabProps {
  profile: Profile
  club: ClubInfo
  // 연결된 계정. 아직 없으면 비워 둔다.
  linkedAccounts?: string
}

export function MyInfoTab({ profile, club, linkedAccounts }: MyInfoTabProps) {
  // TODO(연동): PATCH /me/notifications. 지금은 화면에서만 바뀐다.
  const [notifications, setNotifications] = useState<NotificationSettings>({
    pendingApproval: true,
    stepDelayed: true,
  })

  const toggles: Array<[keyof NotificationSettings, string, string]> = [
    ['pendingApproval', '승인 대기 알림', '새 승인 요청이 생기면'],
    ['stepDelayed', '단계 지연 알림', '예정보다 늦어지면'],
  ]

  return (
    <div className="flex items-start gap-[20px]">
      <div className="flex min-w-0 flex-1 flex-col gap-[20px]">
        <Card className="flex items-center gap-[16px] px-[26px] py-[22px]">
          <Avatar name={profile.name} size={46} />
          <div className="flex min-w-0 flex-1 flex-col gap-[4px]">
            <div className="flex items-center gap-[8px]">
              <span className="text-h2 text-ink">{profile.name}</span>
              <Chip tone="approved" size="sm">
                {profile.role}
              </Chip>
            </div>
            <span className="text-[11.5px] text-mute">{profile.email}</span>
          </div>
          <Button variant="secondary">프로필 수정</Button>
        </Card>

        <Card className="flex flex-col gap-[18px] px-[26px] pt-[22px] pb-[24px]">
          <h2 className="text-h2 text-ink">동아리</h2>
          <Facts
            items={[
              ['이름', club.name],
              ['회원', `${club.memberCount}명`],
              ['내 권한', club.myRole],
              ['가입일', club.joinedAt],
            ]}
          />
          <div className="flex gap-[9px] border-t border-line pt-[18px]">
            <Button variant="soft">동아리 정보 수정</Button>
            <Button variant="secondary">동아리 나가기</Button>
          </div>
        </Card>

        <Card className="flex flex-col pt-[4px]">
          <h2 className="px-[26px] pt-[18px] pb-[14px] text-h2 text-ink">계정</h2>
          <LinkRow label="비밀번호 변경" />
          <LinkRow label="연결된 계정" value={linkedAccounts ?? '없음'} />
          <LinkRow label="로그아웃" />
          <LinkRow label="탈퇴" danger />
        </Card>
      </div>

      <div className="flex w-[300px] shrink-0 flex-col gap-[16px]">
        <Card className="flex flex-col gap-[16px] px-[22px] pt-[20px] pb-[22px]">
          <h2 className="text-h2 text-ink">알림</h2>
          {toggles.map(([key, label, desc]) => (
            <div key={key} className="flex items-center justify-between gap-[12px]">
              <span className="flex flex-col gap-[3px]">
                <span className="text-[12.5px] font-bold text-ink">{label}</span>
                <span className="text-[10.5px] text-mute">{desc}</span>
              </span>
              <Switch
                checked={notifications[key]}
                label={label}
                onChange={(checked) => setNotifications((s) => ({ ...s, [key]: checked }))}
              />
            </div>
          ))}
        </Card>

        <ToriNote title="토리가 도와드려요">
          승인 알림을 켜두면 되돌릴 수 없는 일만 골라서 알려드릴게요.
        </ToriNote>
      </div>
    </div>
  )
}
