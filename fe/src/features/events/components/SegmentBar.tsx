// 세그먼트 진행 바: 단계 수만큼 칸을 나누고, 진행 중인 단계까지 채운다. 끝난 행사는 연한 파랑.
import { cn } from '@/shared/lib/cn'
import type { StepState } from '@/features/events/types'

interface SegmentBarProps {
  states: StepState[]
  // 끝난 행사면 true
  muted?: boolean
}

export function SegmentBar({ states, muted = false }: SegmentBarProps) {
  const filled = muted ? 'bg-blue-300' : 'bg-blue-600'
  return (
    <div className="flex gap-[4px]">
      {states.map((state, i) => (
        <span
          key={i}
          className={cn('h-[7px] flex-1 rounded-[3px]', state === 'TODO' ? 'bg-track' : filled)}
        />
      ))}
    </div>
  )
}
