// 상태 칩. 색은 0·기준 「상태」 한 쌍(배경 + 글자)을 그대로 쓴다.
import type { HTMLAttributes } from 'react'
import { cn } from '@/shared/lib/cn'

type Tone = 'neutral' | 'done' | 'pending' | 'approved' | 'failed' | 'blush'

interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone
  size?: 'md' | 'sm'
}

const TONE_CLASS: Record<Tone, string> = {
  neutral: 'bg-chip text-ink2',
  done: 'bg-done-bg text-done',
  pending: 'bg-pending-bg text-pending',
  approved: 'bg-approved-bg text-approved',
  failed: 'bg-failed-bg text-failed',
  blush: 'bg-blush-bg text-blush',
}

const SIZE_CLASS = {
  md: 'px-[11px] py-[6px] text-[11.5px]',
  sm: 'px-[10px] py-[5px] text-[10.5px]',
}

export function Chip({ tone = 'neutral', size = 'md', className, ...props }: ChipProps) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center rounded-[8px] font-bold whitespace-nowrap',
        TONE_CLASS[tone],
        SIZE_CLASS[size],
        className,
      )}
      {...props}
    />
  )
}
