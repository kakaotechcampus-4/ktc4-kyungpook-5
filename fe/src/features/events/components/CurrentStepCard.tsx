// 현재 단계 카드(L2): 진행 중인 단계에서 토리가 한 일과 남은 일. 자세한 내용은 Step 모달에서 본다.
import type { EventStep } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { formatPeriod } from '@/shared/lib/format'
import { STEP_ACTOR_LABEL } from '@/shared/lib/labels'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { ToriNote } from '@/shared/ui/ToriNote'

interface CurrentStepCardProps {
  step: EventStep
  // 스테퍼에서 몇 번째 단계인지(1부터)
  position: number
  // [단계 자세히 보기] → Step 모달
  onOpen: () => void
  className?: string
}

export function CurrentStepCard({ step, position, onOpen, className }: CurrentStepCardProps) {
  // "3/10 – 3/12 · AI 실행". 빠진 값은 건너뛴다.
  const summary = [
    formatPeriod(step.startedTime, step.deadline),
    step.actor && STEP_ACTOR_LABEL[step.actor],
  ]
    .filter(Boolean)
    .join(' · ')
  const done = step.doneActions ?? []
  const remaining = step.remainingActions ?? []

  return (
    <Card className={cn('flex flex-col gap-[18px] px-[26px] pt-[24px] pb-[26px]', className)}>
      <div className="flex items-center gap-[9px]">
        <h2 className="text-h2">
          {position}. {step.name}
        </h2>
        <Chip tone="approved">진행 중</Chip>
      </div>
      {summary && <p className="text-caption text-mute">{summary}</p>}

      {/* 명세에 요약 문장이 따로 없어 한 일 제목을 이어 붙인다 */}
      {done.length > 0 && (
        <ToriNote title="이 단계에서 한 일">{done.map((a) => a.title).join(' ')}</ToriNote>
      )}

      {remaining.length > 0 && (
        <div className="flex flex-col gap-[8px] text-ink2">
          <h3 className="text-body font-bold">남은 일</h3>
          <ul className="flex flex-col gap-[8px] text-[12.5px] leading-[19px]">
            {remaining.map((a) => (
              <li key={a.id}>
                · {a.title}
                {a.approveNeeded && a.status === 'PENDING' && ' (승인 대기 중)'}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Button variant="soft" className="w-full" onClick={onOpen}>
        단계 자세히 보기
      </Button>
    </Card>
  )
}
