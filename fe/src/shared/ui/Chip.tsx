// 승인 필요 / 읽음 같은 배지
import type { HTMLAttributes } from 'react'
import { cn } from '@/shared/lib/cn'

type Variant = 'dark' | 'outline' | 'subtle'

interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant
}

const VARIANT_CLASS: Record<Variant, string> = {
  dark: 'bg-[#333] text-[#fafafa] border border-[#e3e3e3]',
  outline: 'bg-white text-[#808080] border border-[#e3e3e3]',
  subtle: 'bg-[#f9f9f9] text-[#6b6b6b] border border-[#e3e3e3]',
}

export function Chip({ variant = 'dark', className, ...props }: ChipProps) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center rounded-[6px] px-[8px] py-[4px] text-[10.5px] font-medium whitespace-nowrap',
        VARIANT_CLASS[variant],
        className,
      )}
      {...props}
    />
  )
}
