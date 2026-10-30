// S2 마이 페이지. 내 정보 · 동아리원 · 동아리 자료 세 탭을 한 화면에서 바꿔 본다.
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useLogout } from '@/features/auth/hooks'
import { AddMemberModal } from '@/features/mypage/components/AddMemberModal'
import { MembersTab } from '@/features/mypage/components/MembersTab'
import { MyInfoTab } from '@/features/mypage/components/MyInfoTab'
import { RecordsTab } from '@/features/mypage/components/RecordsTab'
import {
  DEMO_CLUB,
  DEMO_JOIN_REQUESTS,
  DEMO_MEMBERS,
  DEMO_MEMBER_TOTAL,
  DEMO_PROFILE,
  DEMO_RECORDS,
  EMPTY_CLUB,
} from '@/features/mypage/mock'
import { useMembers } from '@/features/mypage/hooks'
import type { JoinRequest, Member } from '@/features/mypage/types'
import { cn } from '@/shared/lib/cn'
import { ErrorBanner } from '@/shared/ui/AuthShell'
import { Button } from '@/shared/ui/Button'
import { useAuthStore } from '@/shared/auth/store'
import { MEMBER_ROLE_LABEL } from '@/shared/lib/labels'

const TABS = ['내 정보', '동아리원', '동아리 자료'] as const
type Tab = (typeof TABS)[number]

export default function MyPage() {
  // 다른 화면과 같은 방식. ?demo면 예시가 채워진 상태를, 없으면 가입 직후 상태를 보인다.
  const demo = useSearchParams()[0].has('demo')
  const { user, me, clubId } = useAuthStore()
  const [tab, setTab] = useState<Tab>('내 정보')
  const [addOpen, setAddOpen] = useState(false)

  const navigate = useNavigate()
  const logout = useLogout()
  // 명단은 서버에서 받는다. 추가·참여 요청은 서버 경로가 없어 ?demo에서만 화면으로 보여준다.
  const membersQuery = useMembers(demo)
  const [demoMembers, setDemoMembers] = useState<Member[]>(DEMO_MEMBERS)
  const members = demo ? demoMembers : (membersQuery.data ?? [])
  const [requests, setRequests] = useState<JoinRequest[]>(demo ? DEMO_JOIN_REQUESTS : [])

  // 선택한 서비스 역할은 공유 세션을 사용한다. 동아리 상세 API는 아직 없어 이름만 /me 소속에서 가져온다.
  const profile = demo
    ? DEMO_PROFILE
    : {
        name: user?.name ?? '내 이름',
        role: user ? (MEMBER_ROLE_LABEL[user.role] ?? '역할 확인 필요') : '역할 확인 전',
        email: user?.email ?? '내 이메일',
      }
  const club = demo
    ? DEMO_CLUB
    : {
        ...EMPTY_CLUB,
        name: me?.clubs.find((item) => item.id === clubId)?.name ?? EMPTY_CLUB.name,
        memberCount: membersQuery.data?.length ?? null,
        myRole: profile.role,
      }

  return (
    <div className="flex flex-col gap-[20px]">
      <header className="flex flex-col gap-[4px]">
        <h1 className="text-h1">마이 페이지</h1>
        <p className="text-mute">내 정보와 동아리 설정을 관리합니다</p>
      </header>

      <nav className="flex w-fit gap-[4px] rounded-[12px] border border-line bg-card p-[4px]">
        {TABS.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setTab(item)}
            aria-current={item === tab}
            className={cn(
              'rounded-[9px] px-[18px] py-[10px] text-[13px]',
              item === tab
                ? 'bg-blue-600 font-bold text-white'
                : 'font-medium text-ink2 hover:bg-bg',
            )}
          >
            {item}
          </button>
        ))}
      </nav>

      {tab === '내 정보' && (
        <MyInfoTab
          profile={profile}
          club={club}
          linkedAccounts={demo ? 'Google · 카카오' : undefined}
          onLogout={() => {
            // 두 번 눌러도 요청은 한 번만 보낸다
            if (logout.isPending) return
            logout.mutate(undefined, { onSettled: () => navigate('/login') })
          }}
        />
      )}

      {/* 받기 전이나 실패를 빈 명단으로 그리면 「아직 없어요」처럼 보여 오류인지 알 수 없다 */}
      {tab === '동아리원' &&
        (!demo && membersQuery.isError ? (
          <ErrorBanner
            title="동아리원 명단을 불러오지 못했어요."
            hint="잠시 뒤 다시 시도해 주세요."
            action={
              <Button size="sm" variant="secondary" onClick={() => void membersQuery.refetch()}>
                다시 시도
              </Button>
            }
          />
        ) : !demo && membersQuery.isPending ? null : (
          <MembersTab
            members={members}
            requests={requests}
            total={demo ? DEMO_MEMBER_TOTAL : members.length}
            onAddClick={demo ? () => setAddOpen(true) : undefined}
            onResolveRequest={(id) => setRequests((list) => list.filter((r) => r.id !== id))}
          />
        ))}

      {tab === '동아리 자료' && <RecordsTab records={demo ? DEMO_RECORDS : []} />}

      <AddMemberModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onAdd={(member) =>
          setDemoMembers((list) => [
            ...list,
            { ...member, id: `mem_${list.length + 1}`, account: 'NONE' },
          ])
        }
      />
    </div>
  )
}
