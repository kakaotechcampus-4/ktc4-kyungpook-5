// 공용 버튼
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '@/shared/lib/cn'

// danger: 되돌릴 수 없는 일(행사 취소 등)에만 쓴다.
// soft: primary 옆에 두는 보조 강조(예: 다른 동아리 찾기)
type Variant = 'primary' | 'soft' | 'secondary' | 'danger' | 'ghost'
type Size = 'lg' | 'md' | 'sm'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  // 눌러서 서버를 기다리는 중. 도는 표시를 띄우고 버튼을 잠근다.
  // AI 호출처럼 몇 초씩 걸리는 자리에 쓴다 — 글자만 바뀌면 멈춘 것처럼 보인다.
  loading?: boolean
}

// 글자 크기를 따라가는 원. 1.5바퀴 분량만 그려 어디가 도는지 보이게 한다.
function Spinner() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className="size-[1em] shrink-0 animate-spin motion-reduce:animate-none"
      fill="none"
    >
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.25" />
      <path
        d="M8 2a6 6 0 0 1 6 6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary: 'bg-blue-600 font-bold text-white hover:bg-blue-700',
  soft: 'bg-blue-100 font-bold text-blue-700 hover:bg-blue-200',
  secondary: 'border border-soft bg-card font-medium text-ink2 hover:bg-bg',
  danger: 'bg-failed-bg font-bold text-failed hover:brightness-95',
  ghost: 'font-medium text-ink2 hover:bg-bg',
}

const SIZE_CLASS: Record<Size, string> = {
  lg: 'px-[17px] py-[11px] text-[14px] rounded-[8px]',
  md: 'px-[16px] py-[10px] text-[14px] rounded-[8px]',
  sm: 'px-[12px] py-[7px] text-[13px] rounded-[8px]',
}

export function Button({
  variant = 'primary',
  size = 'md',
  type = 'button',
  loading = false,
  disabled,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      // 기다리는 동안 또 누르지 못하게 한다. 읽어 주는 기기에는 aria-busy로 알린다.
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center gap-[6px] whitespace-nowrap transition-colors duration-150 motion-reduce:transition-none disabled:cursor-not-allowed disabled:opacity-50',
        VARIANT_CLASS[variant],
        SIZE_CLASS[size],
        className,
      )}
      {...props}
    >
      {loading && <Spinner />}
      {children as ReactNode}
    </button>
  )
}
