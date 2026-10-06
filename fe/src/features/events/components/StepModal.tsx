// Step 모달(진행 중 행사): 단계 하나에서 토리가 한 일 · 할 일 · 처리된 일. L2에서 단계를 누르면 열린다.
import { ActionCard } from '@/features/events/components/ActionCard'
import type { EventAction, EventStep, StepState } from '@/features/events/types'
import { formatPeriod } from '@/shared/lib/format'
import { STEP_ACTOR_LABEL } from '@/shared/lib/labels'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import { EmptyState } from '@/shared/ui/EmptyState'
import { Modal } from '@/shared/ui/Modal'
import { ToriNote } from '@/shared/ui/ToriNote'

const STATE_CHIP = {
  CURRENT: { label: '진행 중', tone: 'approved' },
  DONE: { label: '완료', tone: 'done' },
  TODO: { label: '예정', tone: 'neutral' },
} as const satisfies Record<StepState, unknown>

interface StepModalProps {
  step: EventStep
  // 스테퍼에서 몇 번째 단계인지(1부터)
  position: number
  // 이 단계의 Action 전부. 상태로 할 일 · 처리된 일을 나눈다. 아직 못 받았으면 undefined.
  actions: EventAction[] | undefined
  // Action을 불러오지 못했으면 true. 빈 목록과 헷갈리지 않게 따로 보인다.
  actionsFailed: boolean
  onRetryActions: () => void
  onClose: () => void
  // Action 카드의 [게시했습니다] 등
  onCompleteAction: (action: EventAction) => void
  onCompleteStep: (step: EventStep) => void
}

export function StepModal({
  step,
  position,
  actions,
  actionsFailed,
  onRetryActions,
  onClose,
  onCompleteAction,
  onCompleteStep,
}: StepModalProps) {
  const chip = STATE_CHIP[step.state]
  const manual = step.actor === 'MANUAL'
  const done = step.doneActions ?? []
  // 실패한 일은 다시 시도해야 해서 할 일에 둔다
  const todo = (actions ?? []).filter((a) => ['PENDING', 'APPROVED', 'FAILED'].includes(a.status))
  const handled = (actions ?? []).filter((a) => a.status === 'DONE' || a.status === 'DENIED')

  // 할 일이 없을 때 이유
  const emptyReason = manual
    ? '직접 수행 단계라 토리가 준비할 일이 없어요.'
    : step.state === 'TODO'
      ? '단계가 시작되면 토리가 할 일을 준비해요.'
      : '이 단계의 일은 모두 처리됐어요.'

  return (
    <Modal
      open
      onClose={onClose}
      width={660}
      title={`${position}. ${step.name}`}
      chip={<Chip tone={chip.tone}>{chip.label}</Chip>}
      // "AI 실행 · 3/10 – 3/12"
      subtitle={[
        step.actor && STEP_ACTOR_LABEL[step.actor],
        formatPeriod(step.startedTime, step.deadline),
      ]
        .filter(Boolean)
        .join(' · ')}
      footerNote={
        step.state === 'CURRENT'
          ? manual
            ? '직접 수행 단계예요'
            : '완료는 토리가 정하지 않아요'
          : undefined
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            닫기
          </Button>
          {/* 끝난 단계는 다시 완료할 수 없고, 아직 시작 안 한 단계는 건너뛰지 않는다 */}
          {step.state === 'CURRENT' && (
            <Button onClick={() => onCompleteStep(step)}>단계 완료로 표시</Button>
          )}
        </>
      }
    >
      {/* 명세에 요약 문장이 따로 없어 한 일 제목을 이어 붙인다(현재 단계 카드와 같다) */}
      {done.length > 0 ? (
        <ToriNote title="이 단계에서 한 일">{done.map((a) => a.title).join(' ')}</ToriNote>
      ) : (
        <>
          <h3 className="text-[15px] font-bold">이 단계에서 한 일</h3>
          <p className="rounded-[12px] border border-dashed border-soft bg-bg px-[16px] py-[20px] text-center text-[12.5px] text-mute">
            아직 기록된 내용이 없어요
          </p>
        </>
      )}

      {!actions ? (
        <>
          <h3 className="text-[15px] font-bold">할 일</h3>
          {actionsFailed ? (
            <EmptyState
              variant="inline"
              toriSize={52}
              title="할 일을 불러오지 못했어요"
              desc="잠시 뒤에 다시 눌러 주세요."
              action={
                <Button variant="secondary" onClick={onRetryActions}>
                  다시 시도
                </Button>
              }
            />
          ) : (
            <p className="py-[20px] text-center text-[12.5px] text-mute">불러오는 중이에요</p>
          )}
        </>
      ) : todo.length > 0 ? (
        <>
          <div className="flex items-center gap-[9px]">
            <h3 className="text-[15px] font-bold">할 일</h3>
            <Chip tone="approved">{todo.length}건</Chip>
          </div>
          {todo.map((action) => (
            <ActionCard key={action.id} action={action} onComplete={onCompleteAction} />
          ))}
        </>
      ) : (
        <>
          <h3 className="text-[15px] font-bold">할 일 · 0건</h3>
          <EmptyState variant="inline" toriSize={52} title="할 일이 없어요" desc={emptyReason} />
        </>
      )}

      {handled.length > 0 && (
        <>
          <h3 className="text-[15px] font-bold">처리된 일 · {handled.length}건</h3>
          {handled.map((action) => (
            <ActionCard key={action.id} action={action} />
          ))}
        </>
      )}
    </Modal>
  )
}
