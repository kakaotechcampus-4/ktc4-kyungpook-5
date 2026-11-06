// 현재 단계 카드(L2): 진행 중인 단계에서 토리가 한 일과 남은 일 개수. 남은 일은 왼쪽 「지금 할 일」에서
// 처리하고, 자세한 내용은 Step 모달에서 본다.
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
  // 이 단계에서 토리가 쓰는 중이거나 써 둔 초안 문장(todo.draftSentences)
  draftNotes?: string[]
  // [단계 자세히 보기] → Step 모달
  onOpen: () => void
  className?: string
}

export function CurrentStepCard({
  step,
  position,
  draftNotes = [],
  onOpen,
  className,
}: CurrentStepCardProps) {
  // "3/10 – 3/12 · AI 실행". 빠진 값은 건너뛴다.
  const summary = [
    formatPeriod(step.startsAt, step.deadline),
    step.actor && STEP_ACTOR_LABEL[step.actor],
  ]
    .filter(Boolean)
    .join(' · ')
  const done = step.doneActions ?? []
  const remaining = step.remainingActions ?? []
  const waiting = remaining.filter((a) => a.approveNeeded && a.status === 'PENDING').length

  return (
    <Card className={cn('flex flex-col gap-[18px] px-[26px] pt-[24px] pb-[26px]', className)}>
      <div className="flex items-center gap-[9px]">
        <h2 className="text-h2">
          {position}. {step.name}
        </h2>
        <Chip tone="approved">진행 중</Chip>
      </div>
      {summary && <p className="text-caption text-mute">{summary}</p>}

      {/* 명세에 요약 문장이 따로 없어 한 일 제목을 이어 붙인다. 완료된 일만 오므로 토리 초안은 따로 덧붙인다. */}
      {(done.length > 0 || draftNotes.length > 0) && (
        <ToriNote title="이 단계에서 한 일">
          {[...done.map((a) => a.title), ...draftNotes].join(' ')}
        </ToriNote>
      )}

      {/* 남은 일은 왼쪽 「지금 할 일」과 겹치니 개수만 남긴다 */}
      {remaining.length > 0 && (
        <p className="text-body text-ink2">
          <span className="font-bold">남은 일 {remaining.length}건</span>
          {waiting > 0 && <span className="text-mute"> · 승인 대기 {waiting}건</span>}
        </p>
      )}

      <Button variant="soft" className="w-full" onClick={onOpen}>
        단계 자세히 보기
      </Button>
    </Card>
  )
}
