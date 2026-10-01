// 공용 카드
import type { HTMLAttributes } from 'react'
import { cn } from '@/shared/lib/cn'

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-[18px] border border-[#e8e8e8] bg-white shadow-[0px_8px_20px_-6px_rgba(0,0,0,0.05),0px_1px_3px_0px_rgba(0,0,0,0.05)]',
        className,
      )}
      {...props}
    />
  )
}
