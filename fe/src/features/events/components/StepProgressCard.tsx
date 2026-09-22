import { useState } from 'react'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { cn } from '@/shared/lib/cn'
import { formatMonthDay } from '@/shared/lib/format'
import type { EventStep, StepActor } from '@/features/events/types'

// 막대 색은 그 단계를 누가 수행하는지를 뜻한다. 아직 오지 않은 단계는 색 없이 회색이다.
const ACTOR_BAR_CLASS: Record<StepActor, string> = {
  AI: 'bg-[#5a7599]',
  APPROVAL_REQUIRED: 'bg-[#aa7c3a]',
  MANUAL: 'bg-[#969696]',
}

const STATE_LABEL: Record<EventStep['state'], string> = {
  DONE: '완료',
  CURRENT: '진행 중',
  TODO: '예정',
}

function periodOf(step: EventStep): string | null {
  if (!step.startedTime) return null
  const started = formatMonthDay(step.startedTime)
  return step.deadline ? `${started} – ${formatMonthDay(step.deadline)}` : started
}

function ActionList({ title, items }: { title: string; items: EventStep['doneActions'] }) {
  return (
    <div className="flex min-w-px flex-1 flex-col gap-[7px]">
      <p className="text-[11.5px] font-semibold text-[#666]">{title}</p>
      {items.length === 0 ? (
        <p className="text-[12px] text-[#8c8c8c]">없습니다</p>
      ) : (
        items.map((item) => (
          <p key={item.id} className="text-[12px] text-[#4d4d4d]">
            · {item.title}
            {item.status === 'PENDING' && item.approveNeeded && ' (승인 대기 중)'}
          </p>
        ))
      )}
    </div>
  )
}

export function StepProgressCard({ steps }: { steps: EventStep[] }) {
  const currentIndex = Math.max(
    0,
    steps.findIndex((step) => step.state === 'CURRENT'),
  )
  const [selectedIndex, setSelectedIndex] = useState(currentIndex)
  const selected = steps[selectedIndex]

  if (!selected) return null

  return (
    <Card className="flex w-full flex-col gap-[16px] p-[24px]">
      <div className="flex w-full items-center gap-[8px]">
        <p className="text-[15px] font-semibold text-[#242424]">진행 상황</p>
        <Chip variant="subtle">
          {steps.length}단계 중 {currentIndex + 1}번째
        </Chip>
        <div className="h-px flex-1" />
        <p className="text-[11px] whitespace-nowrap text-[#808080]">
          단계를 누르면 그 단계에서 한 일과 할 일이 보입니다
        </p>
      </div>

      <div className="flex w-full items-start gap-[5px]">
        {steps.map((step, index) => (
          <button
            key={step.id}
            type="button"
            onClick={() => setSelectedIndex(index)}
            aria-pressed={index === selectedIndex}
            className="flex min-w-px flex-1 flex-col items-start gap-[7px] overflow-hidden text-left"
          >
            <span
              className={cn(
                'h-[8px] w-full rounded-[4px]',
                step.state === 'TODO' ? 'bg-[#e6e6e6]' : ACTOR_BAR_CLASS[step.actor],
                index === selectedIndex && 'border-2 border-[#262626]',
              )}
            />
            <span
              className={cn(
                'text-[10px] whitespace-nowrap',
                step.state === 'TODO' ? 'text-[#8c8c8c]' : 'text-[#383838]',
                index === selectedIndex ? 'font-semibold' : 'font-medium',
              )}
            >
              {step.name}
            </span>
          </button>
        ))}
      </div>

      <div className="flex w-full flex-col gap-[12px] rounded-[14px] bg-[#f8f8f8] px-[20px] py-[18px]">
        <div className="flex w-full items-center gap-[8px]">
          <p className="text-[14px] font-semibold text-[#242424]">
            {selectedIndex + 1}. {selected.name}
          </p>
          <Chip variant={selected.state === 'CURRENT' ? 'dark' : 'subtle'}>
            {STATE_LABEL[selected.state]}
          </Chip>
          <div className="h-px flex-1" />
          {periodOf(selected) && (
            <p className="text-[11.5px] whitespace-nowrap text-[#737373]">{periodOf(selected)}</p>
          )}
        </div>

        <div className="flex w-full items-start gap-[24px]">
          <ActionList title="이 단계에서 한 일" items={selected.doneActions} />
          <ActionList title="남은 일" items={selected.remainingActions} />
        </div>
      </div>
    </Card>
  )
}
