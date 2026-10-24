// 토리 안내 박스(Figma 「toribox」). 모달·카드 곳곳에서 토리가 설명을 덧붙일 때 쓴다.
import type { ReactNode } from 'react'
import { cn } from '@/shared/lib/cn'
import { Tori } from '@/shared/ui/Tori'

// blue: 안내 · cream: 주의 · blush: 위험
type Tone = 'blue' | 'cream' | 'blush'

const TONE_CLASS: Record<Tone, string> = {
  blue: 'border-blue-200 bg-blue-50 text-blue-700',
  cream: 'border-pending-line bg-pending-bg text-pending',
  blush: 'border-failed-line bg-failed-bg text-failed',
}

interface ToriNoteProps {
  title: string
  children?: ReactNode
  tone?: Tone
  className?: string
}

export function ToriNote({ title, children, tone = 'blue', className }: ToriNoteProps) {
  return (
    <div
      className={cn(
        'flex w-full items-start gap-[12px] rounded-[14px] border pt-[14px] pr-[17px] pb-[15px] pl-[15px]',
        TONE_CLASS[tone],
        className,
      )}
    >
      <Tori size={36} />
      <div className="flex min-w-0 flex-1 flex-col gap-[5px]">
        <p className="text-[13px] font-bold">{title}</p>
        {children && <div className="text-[12.5px] leading-[19px]">{children}</div>}
      </div>
    </div>
  )
}
