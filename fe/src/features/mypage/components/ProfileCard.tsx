import { Avatar } from '@/shared/ui/Avatar'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import type { MyProfile } from '@/features/mypage/types'

export function ProfileCard({ profile }: { profile: MyProfile }) {
  return (
    <Card className="flex w-full items-center gap-[20px] p-[26px]">
      <Avatar name={profile.name} size="lg" />
      <div className="flex min-w-0 flex-1 flex-col gap-[5px]">
        <div className="flex items-center gap-[9px]">
          <p className="text-[22px] font-bold text-[#1f1f1f]">{profile.name}</p>
          <Chip>{profile.role}</Chip>
        </div>
        <p className="text-[12.5px] text-[#6b6b6b]">{profile.email}</p>
        <p className="text-[12px] text-[#808080]">
          {profile.clubName} · {profile.memberSince}
        </p>
      </div>
      <Button variant="secondary" size="pill">
        프로필 수정
      </Button>
    </Card>
  )
}
