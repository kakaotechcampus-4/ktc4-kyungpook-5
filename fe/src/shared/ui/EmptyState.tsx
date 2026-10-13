// 빈 상태 블록: 데이터가 없을 때 그 자리를 대신한다. 토리 + 한 줄 + 안내 + (할 일 버튼).
// page: 화면 본문을 통째로 대신할 때(흰 카드) · inline: 카드 안 한 구역을 대신할 때(크림 바탕)
import type { ReactNode } from 'react'
import { cn } from '@/shared/lib/cn'
import { Tori } from '@/shared/ui/Tori'

interface EmptyStateProps {
  title: string
  desc: string
  // 할 일 버튼. 없으면 안내만 보여준다.
  action?: ReactNode
  variant?: 'page' | 'inline'
  // 시안 기준 page 96~104 · inline 64~72
  toriSize?: number
  className?: string
}

const VARIANT = {
  page: {
    box: 'gap-[15px] rounded-[18px] border-[1.5px] bg-card px-[40px] pt-[50px] pb-[52px]',
    title: 'text-[20px] text-ink',
    desc: 'max-w-[450px] text-body leading-[21px]',
    tori: 104,
  },
  inline: {
    box: 'gap-[11px] rounded-[14px] border bg-bg px-[20px] py-[30px]',
    title: 'text-[14px] text-ink2',
    desc: 'text-[12px] leading-[18px]',
    tori: 64,
  },
}

export function EmptyState({
  title,
  desc,
  action,
  variant = 'page',
  toriSize,
  className,
}: EmptyStateProps) {
  const v = VARIANT[variant]
  return (
    <div
      className={cn(
        'flex flex-col items-center border-dashed border-soft text-center',
        v.box,
        className,
      )}
    >
      <Tori size={toriSize ?? v.tori} />
      <p className={cn('font-bold', v.title)}>{title}</p>
      <p className={cn('text-mute', v.desc)}>{desc}</p>
      {action && <div className={variant === 'page' ? 'pt-[6px]' : undefined}>{action}</div>}
    </div>
  )
}
