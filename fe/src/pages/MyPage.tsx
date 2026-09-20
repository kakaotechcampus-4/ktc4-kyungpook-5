// MyPage — 조립만 한다. 로직은 features/ 로.
import { AccountCard } from '@/features/mypage/components/AccountCard'
import { ActivityCard } from '@/features/mypage/components/ActivityCard'
import { ClubInfoCard } from '@/features/mypage/components/ClubInfoCard'
import { ClubRecordsCard } from '@/features/mypage/components/ClubRecordsCard'
import { MemberManagementCard } from '@/features/mypage/components/MemberManagementCard'
import { NotificationCard } from '@/features/mypage/components/NotificationCard'
import { ProfileCard } from '@/features/mypage/components/ProfileCard'
import { useMyPage } from '@/features/mypage/hooks'

export default function MyPage() {
  const mypage = useMyPage()

  return (
    <div className="flex w-full flex-col gap-[16px] px-[26px] pt-[22px] pb-[30px]">
      <p className="text-[20px] font-bold text-[#212121]">마이 페이지</p>
      <div className="flex w-full items-start gap-[16px]">
        <div className="flex min-w-0 flex-1 flex-col gap-[14px]">
          <ProfileCard profile={mypage.profile} />
          <ActivityCard stats={mypage.stats} log={mypage.activityLog} />
          <NotificationCard
            settings={mypage.notifications}
            contactLabel={`카카오톡 · ${mypage.profile.email}`}
            onToggle={mypage.toggleNotification}
          />
          <AccountCard />
        </div>
        <div className="flex w-[330px] shrink-0 flex-col gap-[14px]">
          <ClubInfoCard clubInfo={mypage.clubInfo} />
          <MemberManagementCard
            joinRequests={mypage.joinRequests}
            officers={mypage.officers}
            onResolveJoinRequest={mypage.resolveJoinRequest}
          />
          <ClubRecordsCard summary={mypage.recordSummary} />
        </div>
      </div>
    </div>
  )
}
