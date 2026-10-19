import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useMe, useLogout } from '@/features/auth/hooks'
import { useAuthStore } from '@/shared/auth/store'
import { Avatar } from '@/shared/ui/Avatar'
import { Button } from '@/shared/ui/Button'
import { Modal } from '@/shared/ui/Modal'
import { Tori } from '@/shared/ui/Tori'
import { PrimaryNavigation, WorkspaceNavigation } from './AppNavigation'

export function AppLayout() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  useMe()
  const { me, clubId, selectClub } = useAuthStore()
  const logout = useLogout()
  const [desktop, setDesktop] = useState(() => window.matchMedia('(min-width: 1024px)').matches)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)
  const selectedClub = me?.clubs.find((club) => club.id === clubId)

  useEffect(() => {
    const media = window.matchMedia('(min-width: 1024px)')
    const change = () => {
      setDesktop(media.matches)
      if (media.matches) setDrawerOpen(false)
    }
    media.addEventListener('change', change)
    return () => media.removeEventListener('change', change)
  }, [])
  useEffect(() => {
    setDrawerOpen(false)
  }, [pathname])
  useEffect(() => {
    if (!desktop || !sidebarOpen) return
    const close = (event: KeyboardEvent) => {
      if (
        event.key === 'Escape' &&
        !event.defaultPrevented &&
        !document.querySelector('dialog[open]')
      ) {
        setSidebarOpen(false)
        menuButton.current?.focus()
      }
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [desktop, sidebarOpen])

  const account = me ? (
    <div className="mt-auto border-t border-line pt-4">
      <p className="truncate px-3 text-caption font-bold text-ink2">
        {selectedClub?.name || '소속 선택 전'}
      </p>
      <Button
        size="sm"
        variant="ghost"
        className="mt-2 w-full justify-start"
        disabled={logout.isPending}
        onClick={() => logout.mutate()}
      >
        로그아웃
      </Button>
    </div>
  ) : (
    <Link
      to="/login"
      className="mt-auto rounded-xl bg-blue-50 px-3 py-3 text-center font-bold text-blue-700"
      onClick={() => setDrawerOpen(false)}
    >
      로그인
    </Link>
  )

  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="sr-only fixed left-4 top-3 z-50 rounded-lg bg-card p-3 focus:not-sr-only"
      >
        본문으로 건너뛰기
      </a>
      <header className="sticky top-0 z-30 grid min-h-[72px] grid-cols-[1fr_auto] items-center gap-x-3 gap-y-3 border-b border-line bg-card px-4 py-3 sm:grid-cols-[1fr_auto_1fr] sm:px-6">
        <div className="flex items-center gap-3">
          <button
            ref={menuButton}
            type="button"
            aria-label={desktop && sidebarOpen ? '메뉴 접기' : '메뉴 열기'}
            aria-expanded={desktop ? sidebarOpen : drawerOpen}
            aria-controls={desktop ? 'workspace-sidebar' : 'mobile-navigation'}
            onClick={() => (desktop ? setSidebarOpen((open) => !open) : setDrawerOpen(true))}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-line text-ink2 transition-colors hover:bg-bg focus-visible:outline-2 focus-visible:outline-blue-600"
          >
            <svg
              aria-hidden
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
            >
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <NavLink to="/" className="flex items-center gap-2">
            <Tori size={30} />
            <span className="text-[15px] font-bold">운영해</span>
          </NavLink>
        </div>
        <div className="col-span-2 row-start-2 flex justify-center sm:col-span-1 sm:col-start-2 sm:row-start-1">
          <PrimaryNavigation onNavigate={() => setDrawerOpen(false)} />
        </div>
        <div className="col-start-2 row-start-1 flex min-w-0 items-center justify-end gap-3 sm:col-start-3">
          {me ? (
            <>
              <label className="min-w-0 text-caption">
                <span className="sr-only">선택 소속</span>
                <select
                  aria-label="선택 소속"
                  value={clubId ?? ''}
                  onChange={(event) => {
                    selectClub(event.target.value)
                    navigate('/meetings')
                  }}
                  className="max-w-[130px] truncate rounded-lg border border-line bg-card py-2 pl-2 pr-1 text-ink2 sm:max-w-[180px]"
                >
                  <option value="" disabled>
                    소속 선택
                  </option>
                  {me.clubs.map((club) => (
                    <option key={club.id} value={club.id}>
                      {club.name}
                    </option>
                  ))}
                </select>
              </label>
              <Link
                to="/mypage"
                aria-label="마이페이지"
                className="rounded-full focus-visible:outline-2 focus-visible:outline-blue-600"
              >
                <Avatar name={me.email} size={30} />
              </Link>
            </>
          ) : (
            <NavLink to="/login" className="text-caption text-blue-700">
              로그인
            </NavLink>
          )}
        </div>
      </header>
      <div className="flex">
        {sidebarOpen && (
          <aside
            id="workspace-sidebar"
            aria-label="사이드 메뉴"
            className="sticky top-[72px] hidden h-[calc(100dvh-72px)] w-[224px] shrink-0 flex-col gap-6 border-r border-line bg-card px-4 py-6 lg:flex"
          >
            <WorkspaceNavigation />
            {account}
          </aside>
        )}
        <main
          id="main-content"
          tabIndex={-1}
          className="min-w-0 flex-1 px-4 pt-7 pb-11 outline-none sm:px-7 lg:px-8"
        >
          <Outlet />
        </main>
      </div>
      <Modal
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="전체 메뉴"
        width={280}
        placement="left"
        className="border-r border-line"
      >
        <div id="mobile-navigation" className="flex min-h-[calc(100dvh-140px)] flex-col gap-8">
          <WorkspaceNavigation onNavigate={() => setDrawerOpen(false)} />
          {account}
        </div>
      </Modal>
    </div>
  )
}
