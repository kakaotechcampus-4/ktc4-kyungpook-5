import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { MEMBER_ROLE_LABEL } from '@/shared/lib/labels'
import { Avatar } from '@/shared/ui/Avatar'
import { Modal } from '@/shared/ui/Modal'
import { Tori } from '@/shared/ui/Tori'
import { PrimaryNavigation, WorkspaceNavigation } from './AppNavigation'

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
    <div className="mt-auto border-t border-line px-3 pt-4 text-caption leading-5 text-ink2">
      <p className="break-words font-bold">{teamName}</p>
      <p className="text-mute">{roleLabel} · 목업 계정</p>
    </div>
  )

  return (
    <div className="min-h-screen">
      <a
        href="#onboarding-main"
        className="sr-only fixed left-4 top-3 z-50 rounded-lg bg-card p-3 focus:not-sr-only"
      >
        본문으로 건너뛰기
      </a>
      <header className="sticky top-0 z-30 grid min-h-[72px] grid-cols-[1fr_auto] items-center gap-x-3 gap-y-3 border-b border-line bg-card px-4 py-3 sm:grid-cols-[1fr_auto_1fr] sm:px-6">
        <div className="flex items-center gap-3">
          <button
            ref={menuButton}
            type="button"
            data-onboarding="menu-toggle"
            aria-label={desktop && sidebarOpen ? '메뉴 접기' : '메뉴 열기'}
            aria-expanded={desktop ? sidebarOpen : drawerOpen}
            aria-controls={desktop ? 'onboarding-sidebar' : 'onboarding-mobile-navigation'}
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
          <Link to="/onboarding" className="flex items-center gap-2">
            <Tori size={30} />
            <span className="text-[15px] font-bold">운영해</span>
          </Link>
        </div>
        <div className="col-span-2 row-start-2 flex justify-center sm:col-span-1 sm:col-start-2 sm:row-start-1">
          <PrimaryNavigation preview onNavigate={() => setDrawerOpen(false)} />
        </div>
        <div className="col-start-2 row-start-1 flex min-w-0 items-center justify-end gap-3 sm:col-start-3">
          <span className="max-w-[130px] break-words text-right text-[11px] leading-4 text-ink2 sm:max-w-[190px] sm:text-caption">
            {teamName} · {roleLabel}
          </span>
          <Link
            to="/onboarding/mypage"
            aria-label="목업 마이페이지"
            className="shrink-0 rounded-full focus-visible:outline-2 focus-visible:outline-blue-600"
          >
            <Avatar name={roleLabel} size={30} />
          </Link>
        </div>
      </header>
      <div className="flex">
        {desktop && sidebarOpen && (
          <aside
            id="onboarding-sidebar"
            aria-label="체험 사이드 메뉴"
            className="sticky top-[72px] flex h-[calc(100dvh-72px)] w-[224px] shrink-0 flex-col gap-6 border-r border-line bg-card px-4 py-6"
          >
            <WorkspaceNavigation preview />
            {account}
          </aside>
        )}
        <main
          id="onboarding-main"
          tabIndex={-1}
          className="min-w-0 flex-1 px-4 pt-5 pb-11 outline-none sm:px-7 lg:px-8"
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
          <WorkspaceNavigation preview onNavigate={() => setDrawerOpen(false)} />
          {account}
        </div>
      </Modal>
    </div>
  )
}
