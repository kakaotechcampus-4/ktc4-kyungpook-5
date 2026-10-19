// 로그인 뒤 모든 화면의 틀: 상단바 + 크림 배경 본문
import type { ReactNode } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useMe, useLogout } from '@/features/auth/hooks'
import { useAuthStore } from '@/shared/auth/store'
import { Button } from '@/shared/ui/Button'
import { cn } from '@/shared/lib/cn'
import { Avatar } from '@/shared/ui/Avatar'
import { Tori } from '@/shared/ui/Tori'

const NAV = [
  { to: '/meetings', label: '회의 베타' },
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
  const navigate = useNavigate()
  useMe()
  const { me, clubId, selectClub } = useAuthStore()
  const logout = useLogout()
  return (
    <div className="min-h-screen">
      <TopBar>
        <nav className="flex flex-wrap gap-[4px] rounded-[12px] bg-bg p-[4px]">
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

        <div className="flex items-center gap-[10px]">
          {me ? (
            <>
              <label className="text-caption">
                <span className="sr-only">선택 소속</span>
                <select
                  aria-label="선택 소속"
                  value={clubId ?? ''}
                  onChange={(event) => {
                    selectClub(event.target.value)
                    navigate('/meetings')
                  }}
                >
                  <option value="" disabled>
                    소속 선택
                  </option>
                  {me.clubs.map((club) => (
                    <option key={club.id} value={club.id}>
                      {club.name} · {club.role}
                    </option>
                  ))}
                </select>
              </label>
              <Button size="sm" variant="ghost" onClick={() => logout.mutate()}>
                로그아웃
              </Button>
            </>
          ) : (
            <NavLink to="/login" className="text-caption text-blue-700">
              로그인
            </NavLink>
          )}
          <Avatar />
        </div>
      </TopBar>
      <main className="px-[40px] pt-[28px] pb-[44px]">
        <Outlet />
      </main>
    </div>
  )
}
