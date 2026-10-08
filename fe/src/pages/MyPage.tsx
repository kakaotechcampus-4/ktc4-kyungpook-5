// S2 마이 페이지. 내 정보 · 동아리원 · 동아리 자료 세 탭을 한 화면에서 바꿔 본다.
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { MyInfoTab } from '@/features/mypage/components/MyInfoTab'
import { DEMO_CLUB, DEMO_PROFILE, EMPTY_CLUB } from '@/features/mypage/mock'
import { cn } from '@/shared/lib/cn'

const TABS = ['내 정보', '동아리원', '동아리 자료'] as const
type Tab = (typeof TABS)[number]

export default function MyPage() {
  // 다른 화면과 같은 방식. ?demo면 예시가 채워진 상태를, 없으면 가입 직후 상태를 보인다.
  const demo = useSearchParams()[0].has('demo')
  const [tab, setTab] = useState<Tab>('내 정보')

  // TODO(연동): GET /me · GET /clubs/{clubId}
  const profile = demo ? DEMO_PROFILE : { name: '내 이름', role: '대표', email: '내 이메일' }
  const club = demo ? DEMO_CLUB : EMPTY_CLUB

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
        />
      )}
    </div>
  )
}
