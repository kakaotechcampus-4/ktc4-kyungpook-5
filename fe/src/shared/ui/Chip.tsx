// 승인 필요 / 읽음 같은 배지
import type { HTMLAttributes } from 'react'
import { cn } from '@/shared/lib/cn'

type Variant = 'dark' | 'outline' | 'subtle' | 'attention' | 'notice'

interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant
}

const VARIANT_CLASS: Record<Variant, string> = {
  dark: 'bg-[#333] text-[#fafafa] border border-[#e3e3e3]',
  outline: 'bg-white text-[#808080] border border-[#e3e3e3]',
  subtle: 'bg-[#f9f9f9] text-[#6b6b6b] border border-[#e3e3e3]',
  attention: 'bg-[#fcf2e5] text-[#4d4d4d] border border-[#e2c59b]',
  // subtle보다 한 톤 진하다. "읽는 중" / "형식 확인 필요"처럼 손이 가야 하는 상태에 쓴다.
  notice: 'bg-[#ededed] text-[#262626] border border-[#e3e3e3]',
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
