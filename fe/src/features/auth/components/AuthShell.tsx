// 로그인·회원가입의 바깥 틀. 두 화면은 AppLayout(상단바) 밖이라 배경과 상단바를 각자 그린다.
// S0은 상단바 없이 가운데 토리를, S1은 상단바에 로그인 링크를 둔다.
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { Tori } from '@/shared/ui/Tori'

interface AuthShellProps {
  // 상단바 오른쪽에 둘 것. 없으면 상단바 자체를 그리지 않는다(S0).
  topRight?: ReactNode
  children: ReactNode
}

export function AuthShell({ topRight, children }: AuthShellProps) {
  return (
    <div className="min-h-screen bg-bg">
      {topRight && (
        <header className="flex items-center justify-between border-b border-line bg-card px-[28px] py-[13px]">
          <NavLink to="/login" className="flex items-center gap-[9px]">
            <Tori size={30} />
            <span className="text-[15px] font-bold">운영해</span>
          </NavLink>
          {topRight}
        </header>
      )}
      <div className="flex flex-col items-center px-[20px] py-[48px]">{children}</div>
    </div>
  )
}

// 오류 배너. 왜 막혔는지 + 다음에 어떻게 하면 되는지(남은 시도 횟수 등) 두 줄.
// action: 막다른 길이 되지 않게 갈 곳을 함께 준다(예: 이미 가입된 이메일 → 로그인하기).
interface ErrorBannerProps {
  title: string
  hint?: string
  action?: ReactNode
}

export function ErrorBanner({ title, hint, action }: ErrorBannerProps) {
  return (
    <div className="flex items-center gap-[11px] rounded-[11px] border border-failed-line bg-failed-bg px-[14px] py-[12px]">
      <span className="text-[12px] font-bold text-failed" aria-hidden>
        !
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
        <span className="text-[12px] font-bold text-failed">{title}</span>
        {hint && <span className="text-[11px] text-failed">{hint}</span>}
      </span>
      {action}
    </div>
  )
}

// 라벨 + 「필수」 + 오른쪽 도움말. Input의 label은 이 조합을 못 담아 여기서 그린다.
interface FieldProps {
  label: string
  required?: boolean
  hint?: string
  children: ReactNode
}

export function Field({ label, required, hint, children }: FieldProps) {
  return (
    <label className="flex w-full flex-col gap-[7px]">
      <span className="flex items-center justify-between">
        <span className="flex items-center gap-[6px]">
          <span className="text-[11.5px] font-bold text-ink2">{label}</span>
          {required && <span className="text-[10.5px] font-bold text-blue-700">필수</span>}
        </span>
        {hint && <span className="text-[10.5px] text-mute">{hint}</span>}
      </span>
      {children}
    </label>
  )
}
