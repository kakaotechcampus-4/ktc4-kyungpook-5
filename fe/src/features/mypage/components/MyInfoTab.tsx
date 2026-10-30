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
// onClick이 없으면 서버 경로가 없는 줄이라 「준비 중」으로 막는다.
function LinkRow({
  label,
  value,
  danger,
  onClick,
}: {
  label: string
  value?: string
  danger?: boolean
  onClick?: () => void
}) {
  const note = value ?? (onClick ? undefined : '준비 중')
  return (
    <button
      type="button"
      disabled={!onClick}
      onClick={onClick}
      className="flex items-center justify-between border-t border-line px-[26px] py-[15px] text-left first:border-t-0 enabled:hover:bg-bg disabled:cursor-not-allowed disabled:opacity-60"
    >
      <span className={danger ? 'text-[12.5px] text-mute' : 'text-[12.5px] font-medium text-ink'}>
        {label}
      </span>
      <span className="flex items-center gap-[10px]">
        {note && <span className="text-[11.5px] text-mute">{note}</span>}
        {/* 막힌 줄에 ›가 있으면 눌러지는 것처럼 보인다 */}
        {onClick && (
          <span className="text-[12px] text-mute" aria-hidden>
            ›
          </span>
        )}
      </span>
    </button>
  )
}

function Facts({ items }: { items: Array<[string, string]> }) {
  return (
    <div className="flex flex-wrap gap-x-[36px] gap-y-[12px]">
      {items
        .filter(([, value]) => value)
        .map(([label, value]) => (
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
  onLogout: () => void
}

// 프로필·동아리 수정, 나가기, 비밀번호, 탈퇴는 서버 경로가 없어 막아 둔다(#213).
export function MyInfoTab({ profile, club, linkedAccounts, onLogout }: MyInfoTabProps) {
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
    <div className="flex flex-col items-stretch gap-[20px] lg:flex-row lg:items-start">
      <div className="flex min-w-0 flex-1 flex-col gap-[20px]">
        {/* 좁은 화면에서는 버튼이 아래 줄로 내려간다(basis로 글자 칸 최소 폭을 잡는다) */}
        <Card className="flex flex-wrap items-center gap-[16px] px-[26px] py-[22px]">
          <Avatar name={profile.name} size={46} />
          <div className="flex min-w-0 flex-1 basis-[180px] flex-col gap-[4px]">
            <div className="flex items-center gap-[8px]">
              <span className="break-all text-h2 text-ink">{profile.name}</span>
              <Chip tone="approved" size="sm">
                {profile.role}
              </Chip>
            </div>
            <span className="break-all text-[11.5px] text-mute">{profile.email}</span>
          </div>
          <Button variant="secondary" disabled>
            프로필 수정 (준비 중)
          </Button>
        </Card>

        <Card className="flex flex-col gap-[18px] px-[26px] pt-[22px] pb-[24px]">
          <h2 className="text-h2 text-ink">동아리</h2>
          <Facts
            items={[
              ['이름', club.name],
              ['명단 인원', club.memberCount === null ? '' : `${club.memberCount}명`],
              ['내 권한', club.myRole],
              ['가입일', club.joinedAt],
            ]}
          />
          <div className="flex items-center gap-[9px] border-t border-line pt-[18px]">
            <Button variant="soft" disabled>
              동아리 정보 수정
            </Button>
            <Button variant="secondary" disabled>
              동아리 나가기
            </Button>
            <span className="text-[11.5px] text-mute">준비 중이에요</span>
          </div>
        </Card>

        <Card className="flex flex-col pt-[4px]">
          <h2 className="px-[26px] pt-[18px] pb-[14px] text-h2 text-ink">계정</h2>
          <LinkRow label="비밀번호 변경" />
          <LinkRow label="연결된 계정" value={linkedAccounts ?? '없음'} />
          <LinkRow label="로그아웃" onClick={onLogout} />
          <LinkRow label="탈퇴" danger />
        </Card>
      </div>

      <div className="flex w-full shrink-0 flex-col gap-[16px] lg:w-[300px]">
        <Card className="flex flex-col gap-[16px] px-[22px] pt-[20px] pb-[22px]">
          <div className="flex flex-col gap-[4px]">
            <h2 className="text-h2 text-ink">알림</h2>
            {/* TODO(연동): PATCH /me/notifications 가 생기면 이 안내를 지운다 */}
            <p className="text-[10.5px] text-mute">
              저장은 준비 중이라 새로고침하면 처음으로 돌아가요.
            </p>
          </div>
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
