// 진행률 바
import { cn } from '@/shared/lib/cn'

interface ProgressBarProps {
  value: number
  max: number
  className?: string
}

export function ProgressBar({ value, max, className }: ProgressBarProps) {
  const percent = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0

  return (
    <div className={cn('h-[8px] w-full overflow-hidden rounded-[4px] bg-track', className)}>
      <div className="h-full rounded-[4px] bg-blue-600" style={{ width: `${percent}%` }} />
    </div>
  )
}
