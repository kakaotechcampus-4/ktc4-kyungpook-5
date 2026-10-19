import { Link, NavLink, useLocation } from 'react-router-dom'
import { cn } from '@/shared/lib/cn'

type NavigationIcon =
  'home' | 'event' | 'meeting' | 'planning' | 'profile' | 'records' | 'accounting'
function Icon({ name }: { name: NavigationIcon }) {
  const paths: Record<NavigationIcon, string> = {
    records: 'M3 7h7l2-3h9v16H3V7Zm0 4h18',
    accounting: 'M4 4h16v16H4V4Zm4 4h8m-8 4h3m4 0h1m-8 4h3m4 0h1',
    home: 'm3 10 9-7 9 7M5 9v11h5v-6h4v6h5V9',
    event: 'M7 3v4m10-4v4M4 10h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z',
    meeting:
      'M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-8l-6 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Zm3 5h8m-8 4h5',
    planning: 'M14 3H5v18h14V10M14 3v7h5m-4-6 5 5M8 14h7m-7 3h5',
    profile: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 8 0 0 1 16 0v2',
  }
  return (
    <svg
      aria-hidden
      width="19"
      height="19"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
    >
      <path d={paths[name]} />
    </svg>
  )
}

export function PrimaryNavigation({ onNavigate }: { onNavigate?: () => void }) {
  const { pathname } = useLocation()
  const inSection = (base: string) => pathname === base || pathname.startsWith(`${base}/`)
  const items = [
    { to: '/', label: '메인', active: pathname === '/' },
    { to: '/events', label: '행사', active: inSection('/events') || inSection('/planning') },
    { to: '/meetings', label: '회의', active: inSection('/meetings') },
  ]
  return (
    <nav aria-label="주요 기능" className="flex items-center gap-1 rounded-xl bg-bg p-1">
      {items.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          onClick={onNavigate}
          aria-current={item.active ? 'page' : undefined}
          className={cn(
            'min-w-[68px] rounded-lg border px-4 py-2 text-[13px] text-center transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600',
            item.active
              ? 'border-soft bg-card font-bold text-blue-700 shadow-sm'
              : 'border-transparent text-ink2 hover:bg-card',
          )}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  )
}

const GROUPS: { label: string; items: { to: string; label: string; icon: NavigationIcon }[] }[] = [
  {
    label: '워크스페이스',
    items: [
      { to: '/', label: '메인', icon: 'home' },
      { to: '/meetings', label: '회의', icon: 'meeting' },
      { to: '/records', label: '자료함', icon: 'records' },
      { to: '/accounting', label: '회계', icon: 'accounting' },
    ],
  },
  {
    label: '행사',
    items: [
      { to: '/events', label: '행사 목록', icon: 'event' },
      { to: '/planning', label: '행사 계획', icon: 'planning' },
    ],
  },
  { label: '내 공간', items: [{ to: '/mypage', label: '마이페이지', icon: 'profile' }] },
]

export function WorkspaceNavigation({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="전체 메뉴" className="space-y-7">
      {GROUPS.map((group) => (
        <section key={group.label}>
          <h2 className="mb-2 px-3 text-[10.5px] font-bold tracking-wide text-mute">
            {group.label}
          </h2>
          <div className="space-y-1">
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-xl px-3 py-3 text-[13px] transition-colors focus-visible:outline-2 focus-visible:outline-blue-600',
                    isActive ? 'bg-blue-100 font-bold text-blue-700' : 'text-ink2 hover:bg-bg',
                  )
                }
              >
                <Icon name={item.icon} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </section>
      ))}
    </nav>
  )
}
