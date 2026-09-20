// 공용 버튼
import type { ButtonHTMLAttributes } from 'react'
import { cn } from '@/shared/lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost'
type Size = 'md' | 'sm' | 'pill'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary: 'bg-[#262626] text-[#fafafa] border border-[#262626] hover:bg-[#1a1a1a]',
  secondary: 'bg-white text-[#525252] border border-[#dbdbdb] hover:bg-[#f7f7f7]',
  ghost: 'bg-transparent text-[#525252] border border-transparent hover:bg-[#f5f5f5]',
}

const SIZE_CLASS: Record<Size, string> = {
  md: 'px-[14px] py-[13px] text-[13px] rounded-[10px]',
  sm: 'px-[13px] py-[8px] text-[12px] rounded-[10px]',
  pill: 'px-[13px] py-[7px] text-[11.5px] rounded-[18px]',
}

export function Button({ variant = 'primary', size = 'md', className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-[8px] font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        VARIANT_CLASS[variant],
        SIZE_CLASS[size],
        className,
      )}
      {...props}
    />
  )
}
