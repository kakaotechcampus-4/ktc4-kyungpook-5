import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useMe, useLogout } from '@/features/auth/hooks'
import { useAuthStore } from '@/shared/auth/store'
import { useRecordingLock } from '@/shared/lib/recordingLock'
import { Avatar } from '@/shared/ui/Avatar'
import { Button } from '@/shared/ui/Button'
import { Modal } from '@/shared/ui/Modal'
import { Tori } from '@/shared/ui/Tori'
import { WorkspaceNavigation } from './AppNavigation'

// select의 특별 항목. 소속 id와 겹치지 않는 값이면 된다.
const NEW_CLUB = '__new_club__'
const JOIN_CLUB = '__join_club__'

export function AppLayout() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  useMe()
  const { me, clubId, selectClub } = useAuthStore()
  const recording = useRecordingLock((state) => state.recording)
  const logout = useLogout()
  const [desktop, setDesktop] = useState(() => window.matchMedia('(min-width: 1024px)').matches)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)

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
    <div className="mt-auto space-y-3 border-t border-[#40516a] pt-4">
      <label className="block text-caption font-bold text-[#c2cddd]">
        <span className="mb-2 block">선택 소속</span>
        <select
          aria-label="선택 소속"
          aria-describedby={recording ? 'club-locked' : undefined}
          disabled={recording}
          value={clubId ?? ''}
          onChange={(event) => {
            // 소속을 더하는 두 길. 소속 id 와 겹치지 않는 값이라 같은 select 에 둔다.
            if (event.target.value === NEW_CLUB || event.target.value === JOIN_CLUB) {
              setDrawerOpen(false)
              navigate(event.target.value === NEW_CLUB ? '/clubs/new' : '/clubs/join')
              return
            }
            selectClub(event.target.value)
            setDrawerOpen(false)
            navigate(pathname === '/records' || pathname === '/accounting' ? pathname : '/dashboard')
          }}
          className="w-full min-w-0 rounded-lg border border-line bg-card px-2 py-2 text-ink2 disabled:opacity-60"
        >
          <option value="" disabled>소속 선택</option>
          {me.clubs.map((club) => <option key={club.id} value={club.id}>{club.name}</option>)}
          <option value={NEW_CLUB}>+ 새 동아리 만들기</option>
          <option value={JOIN_CLUB}>+ 초대 코드로 참여</option>
        </select>
        {recording && (
          <span id="club-locked" className="mt-2 block text-[12px] font-medium text-[#aebbd0]">
            녹음을 끝낸 뒤 바꿀 수 있어요
          </span>
        )}
      </label>
      <Link to="/mypage" onClick={() => setDrawerOpen(false)} className="flex min-w-0 items-center gap-2 rounded-lg px-1 py-1 text-[#e1e8f1] focus-visible:outline-2 focus-visible:outline-white">
        <Avatar name={me.email} size={30} />
        <span className="min-w-0 truncate text-caption">{me.email}</span>
      </Link>
      <Button size="sm" variant="ghost" className="w-full justify-start !border-0 !bg-transparent !text-[#d5deea] hover:!bg-[#263b54] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white" disabled={logout.isPending} onClick={() => logout.mutate()}>
        로그아웃
      </Button>
    </div>
  ) : (
    <Link to="/login" className="mt-auto rounded-xl bg-blue-50 px-3 py-3 text-center font-bold text-blue-700" onClick={() => setDrawerOpen(false)}>로그인</Link>
  )

  const menuToggle = (
    <button
      ref={menuButton}
      type="button"
      aria-label={desktop && sidebarOpen ? '메뉴 접기' : '메뉴 열기'}
      aria-expanded={desktop ? sidebarOpen : drawerOpen}
      aria-controls={desktop ? 'workspace-sidebar' : 'mobile-navigation'}
      onClick={() => (desktop ? setSidebarOpen((open) => !open) : setDrawerOpen(true))}
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-white hover:bg-[#263b54] focus-visible:outline-2 focus-visible:outline-white"
    >
      <svg aria-hidden width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
        <path d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    </button>
  )

  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="sr-only fixed left-4 top-3 z-50 rounded-lg bg-card p-3 focus:not-sr-only"
      >
        본문으로 건너뛰기
      </a>
      <div className="flex min-h-screen">
        <aside
          id="workspace-sidebar"
          aria-label="사이드 메뉴"
          className={`workspace-sidebar sticky top-0 hidden h-dvh shrink-0 flex-col overflow-y-auto bg-[#172333] px-4 py-5 lg:flex ${sidebarOpen ? 'w-[240px]' : 'w-[72px]'}`}
        >
          <div className="flex items-center gap-2">
            {desktop && menuToggle}
            {sidebarOpen && (
              <NavLink to="/dashboard" className="flex min-w-0 items-center gap-2 text-white">
                <Tori size={30} />
                <span className="text-[15px] font-bold">운영해</span>
              </NavLink>
            )}
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-6 pt-8">
              <WorkspaceNavigation dark collapsed={!sidebarOpen} />
              {sidebarOpen && <>
              <Button size="sm" variant="secondary" onClick={() => navigate('/onboarding')}>
                처음 사용 가이드 (임시)
              </Button>
              {account}
              </>}
          </div>
        </aside>
        {!desktop && (
          <div className="fixed left-3 top-3 z-30 rounded-lg bg-[#172333] shadow-md lg:hidden">
            {menuToggle}
          </div>
        )}
        <main
          id="main-content"
          tabIndex={-1}
          className="min-w-0 flex-1 bg-white px-4 pt-16 pb-11 outline-none sm:px-7 lg:px-10 lg:pt-7"
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
          <NavLink to="/dashboard" onClick={() => setDrawerOpen(false)} className="flex items-center gap-2 font-bold"><Tori size={30} />운영해</NavLink>
          <WorkspaceNavigation onNavigate={() => setDrawerOpen(false)} />
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setDrawerOpen(false)
              navigate('/onboarding')
            }}
          >
            처음 사용 가이드 (임시)
          </Button>
          <div className="mt-auto rounded-lg bg-[#172333] p-4">{account}</div>
        </div>
      </Modal>
    </div>
  )
}
