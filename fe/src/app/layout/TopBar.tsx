// 로고 + 우측 영역
import type { ReactNode } from 'react'
import { useAuthStore } from '@/shared/auth/store'

const ROLE_LABEL: Record<string, string> = {
  OWNER: '대표',
  MANAGER: '임원',
  MEMBER: '동아리원',
}

interface TopBarProps {
  right?: ReactNode
}

export function TopBar({ right }: TopBarProps) {
  const user = useAuthStore((state) => state.user)

  return (
    <header className="flex w-full shrink-0 items-center gap-[12px] border-b border-[#e8e8e8] bg-white px-[24px] py-[14px]">
      <div className="size-[28px] shrink-0 rounded-[9px] bg-[#262626]" />
      <p className="text-[16px] font-bold text-[#212121]">운영해</p>
      <div className="h-px flex-1" />
      {user && (
        <p className="text-[12px] text-[#737373]">
          {ROLE_LABEL[user.role] ?? user.role} · {user.name}
        </p>
      )}
      {right}
    </header>
  )
}
