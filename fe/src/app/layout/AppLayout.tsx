// 로그인 뒤 모든 화면의 틀: 상단바 + 크림 배경 본문
import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/shared/lib/cn'
import { Avatar } from '@/shared/ui/Avatar'
import { Tori } from '@/shared/ui/Tori'

const NAV = [
  { to: '/', label: '메인' },
  { to: '/planning', label: '행사 계획' },
  { to: '/events', label: '행사 목록' },
  { to: '/mypage', label: '마이 페이지' },
]

export function TopBar({ children }: { children?: ReactNode }) {
  return (
    <header className="flex items-center justify-between border-b border-line bg-card px-[28px] py-[13px]">
      <NavLink to="/" className="flex items-center gap-[9px]">
        <Tori size={30} />
        <span className="text-[15px] font-bold">운영해</span>
      </NavLink>
      {children}
    </header>
  )
}

export function AppLayout() {
  return (
    <div className="min-h-screen">
      <TopBar>
        <nav className="flex gap-[4px] rounded-[12px] bg-bg p-[4px]">
          {NAV.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'rounded-[9px] border px-[14px] py-[8px] text-[12.5px]',
                  isActive
                    ? 'border-soft bg-card font-bold text-blue-700'
                    : 'border-transparent font-medium text-ink2 hover:text-ink',
                )
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        {/* TODO: 로그인 연동 후 실제 동아리·역할로 바꾼다 */}
        <div className="flex items-center gap-[10px]">
          <span className="text-[12px] font-medium text-mute">큰나무 동아리 · 총무</span>
          <Avatar />
        </div>
      </TopBar>
      <main className="px-[40px] pt-[28px] pb-[44px]">
        <Outlet />
      </main>
    </div>
  )
}
