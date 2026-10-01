// 메인 / 행사 계획 / 행사 목록 / 동아리 기록 / 마이 페이지 네비게이션
import { NavLink } from 'react-router-dom'
import { cn } from '@/shared/lib/cn'

const NAV_ITEMS = [
  { to: '/', label: '메인' },
  { to: '/planning', label: '행사 계획' },
  { to: '/events', label: '행사 목록' },
  { to: '/records', label: '동아리 기록' },
  { to: '/mypage', label: '마이 페이지' },
]

export function Sidebar() {
  return (
    <nav className="flex w-[188px] shrink-0 flex-col gap-[4px] self-stretch border-r border-[#e8e8e8] bg-white px-[12px] py-[18px]">
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === '/'}
          className={({ isActive }) =>
            cn(
              'flex w-full items-center gap-[10px] rounded-[10px] px-[12px] py-[11px] text-[13px]',
              isActive ? 'bg-[#262626] font-semibold text-[#fafafa]' : 'text-[#666] hover:bg-[#f5f5f5]',
            )
          }
        >
          {({ isActive }) => (
            <>
              <span className={cn('size-[18px] shrink-0 rounded-[6px]', isActive ? 'bg-[#fafafa]' : 'bg-[#999]')} />
              {item.label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
