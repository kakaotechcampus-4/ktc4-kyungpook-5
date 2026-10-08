// 로그인·회원가입 공통 틀: 가운데 정렬 · 토리 · 서비스 이름 · 한 줄 소개 + 흰 카드.
// 두 화면 다 AppLayout(상단바) 밖에 있어서 틀을 각자 그린다.
import type { ReactNode } from 'react'
import { cn } from '@/shared/lib/cn'
import { Tori } from '@/shared/ui/Tori'

interface AuthShellProps {
  tagline: string
  children: ReactNode
  // 회원가입은 입력이 많아 카드가 더 넓다.
  width?: number
}

export function AuthShell({ tagline, children, width = 296 }: AuthShellProps) {
  return (
    <div className="flex min-h-screen flex-col items-center bg-bg px-[20px] py-[56px]">
      <Tori size={76} />
      <h1 className="mt-[14px] text-display text-ink">운영해</h1>
      <p className="mt-[6px] text-[12px] text-mute">{tagline}</p>
      <div
        className={cn('mt-[26px] rounded-[18px] border border-line bg-card px-[32px] py-[28px]')}
        style={{ width: width + 64 }}
      >
        {children}
      </div>
    </div>
  )
}

// 오류 배너. 왜 막혔는지 + 다음에 어떻게 하면 되는지(남은 시도 횟수 등) 두 줄.
export function ErrorBanner({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex items-start gap-[9px] rounded-[11px] border border-failed-line bg-failed-bg px-[14px] py-[12px]">
      <span className="text-[12px] font-bold text-failed" aria-hidden>
        !
      </span>
      <span className="flex flex-col gap-[3px]">
        <span className="text-[12px] font-bold text-failed">{title}</span>
        {hint && <span className="text-[11px] text-failed">{hint}</span>}
      </span>
    </div>
  )
}
