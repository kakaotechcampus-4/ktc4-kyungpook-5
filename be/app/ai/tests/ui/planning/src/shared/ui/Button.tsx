// 공용 버튼
import type { ButtonHTMLAttributes } from 'react'
import { cn } from '@/shared/lib/cn'

// danger: 되돌릴 수 없는 일(행사 취소 등)에만 쓴다.
// soft: primary 옆에 두는 보조 강조(예: 다른 동아리 찾기)
type Variant = 'primary' | 'soft' | 'secondary' | 'danger' | 'ghost'
type Size = 'lg' | 'md' | 'sm'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary: 'bg-blue-600 font-bold text-white hover:bg-blue-700',
  soft: 'bg-blue-100 font-bold text-blue-700 hover:bg-blue-200',
  secondary: 'border border-soft bg-card font-medium text-ink2 hover:bg-bg',
  danger: 'bg-failed-bg font-bold text-failed hover:brightness-95',
  ghost: 'font-medium text-ink2 hover:bg-bg',
}

const SIZE_CLASS: Record<Size, string> = {
  lg: 'px-[17px] py-[11px] text-[12.5px] rounded-[10px]',
  md: 'px-[16px] py-[10px] text-[12.5px] rounded-[10px]',
  sm: 'px-[12px] py-[7px] text-[12px] rounded-[8px]',
}

export function Button({
  variant = 'primary',
  size = 'md',
  type = 'button',
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        'inline-flex items-center justify-center gap-[6px] whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        VARIANT_CLASS[variant],
        SIZE_CLASS[size],
        className,
      )}
      {...props}
    />
  )
}
