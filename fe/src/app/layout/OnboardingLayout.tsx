import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { MEMBER_ROLE_LABEL } from '@/shared/lib/labels'
import { Avatar } from '@/shared/ui/Avatar'
import { Modal } from '@/shared/ui/Modal'
import { Tori } from '@/shared/ui/Tori'
import { WorkspaceNavigation } from './AppNavigation'

/** 서버 세션과 분리한 화면 체험의 공통 틀. 실제 API와 인증 훅을 호출하지 않는다. */
export function OnboardingLayout({
  children,
  teamName = '온빛 캠퍼스 운영팀',
  role = 'MANAGER',
}: {
  children: ReactNode
  teamName?: string
  role?: 'OWNER' | 'MANAGER'
}) {
  const { pathname } = useLocation()
  const roleLabel = MEMBER_ROLE_LABEL[role]
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
        !document.querySelector('dialog[open]') &&
        !document.querySelector('[data-onboarding-spotlight]')
      ) {
        setSidebarOpen(false)
        menuButton.current?.focus()
      }
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [desktop, sidebarOpen])

  const account = (
    <div className="mt-auto space-y-3 border-t border-[#40516a] pt-4 text-caption text-[#c2cddd]">
      <div>
        <p className="mb-2 font-bold">선택 소속</p>
        <p className="break-words rounded-lg border border-line bg-card px-2 py-2 text-ink2">{teamName}</p>
      </div>
      <Link to="/onboarding/mypage" onClick={() => setDrawerOpen(false)} aria-label="목업 마이페이지" className="flex items-center gap-2 rounded-lg text-white focus-visible:outline-2 focus-visible:outline-white">
        <Avatar name={roleLabel} size={30} />
        <span>{roleLabel} · 목업 계정</span>
      </Link>
    </div>
  )

  const menuToggle = (
    <button ref={menuButton} type="button" data-onboarding="menu-toggle"
      aria-label={desktop && sidebarOpen ? '메뉴 접기' : '메뉴 열기'}
      aria-expanded={desktop ? sidebarOpen : drawerOpen}
      aria-controls={desktop ? 'onboarding-sidebar' : 'onboarding-mobile-navigation'}
      onClick={() => (desktop ? setSidebarOpen((open) => !open) : setDrawerOpen(true))}
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-white hover:bg-[#263b54] focus-visible:outline-2 focus-visible:outline-white">
      <svg aria-hidden width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
        <path d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    </button>
  )

  return (
    <div className="min-h-screen">
      <a
        href="#onboarding-main"
        className="sr-only fixed left-4 top-3 z-50 rounded-lg bg-card p-3 focus:not-sr-only"
      >
        본문으로 건너뛰기
      </a>
      <div className="flex min-h-screen">
        <aside id="onboarding-sidebar" aria-label="체험 사이드 메뉴"
          className={`sticky top-0 hidden h-dvh shrink-0 flex-col overflow-y-auto bg-[#172333] px-4 py-5 lg:flex ${sidebarOpen ? 'w-[240px]' : 'w-[72px]'}`}>
          <div className="flex items-center gap-2">
            {desktop && menuToggle}
            {sidebarOpen && <Link to="/onboarding" className="flex items-center gap-2 text-white"><Tori size={30} /><span className="text-[15px] font-bold">운영해</span></Link>}
          </div>
          {sidebarOpen && <div className="flex min-h-0 flex-1 flex-col gap-6 pt-8"><WorkspaceNavigation preview dark />{account}</div>}
        </aside>
        {!desktop && <div className="fixed left-3 top-3 z-30 rounded-lg bg-[#172333] shadow-md lg:hidden">{menuToggle}</div>}
        <main
          id="onboarding-main"
          tabIndex={-1}
          className="min-w-0 flex-1 px-4 pt-16 pb-11 outline-none sm:px-7 lg:px-10 lg:pt-7"
        >
          {children}
        </main>
      </div>
      <Modal
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="체험 전체 메뉴"
        width={280}
        placement="left"
        className="border-r border-line"
      >
        <div
          id="onboarding-mobile-navigation"
          className="flex min-h-[calc(100dvh-140px)] flex-col gap-8"
        >
          <Link to="/onboarding" onClick={() => setDrawerOpen(false)} className="flex items-center gap-2 font-bold"><Tori size={30} />운영해</Link>
          <WorkspaceNavigation preview onNavigate={() => setDrawerOpen(false)} />
          <div className="mt-auto rounded-lg bg-[#172333] p-4">{account}</div>
        </div>
      </Modal>
    </div>
  )
}
