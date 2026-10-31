// 행사 완료 확인 모달. 앱이 끝났다고 판단하지 않고 운영진이 직접 표시한다.
// 되돌리는 경로가 없어서, 남은 일이 있으면 먼저 보여주고 묻는다.
import type { EventDetail } from '@/features/events/types'
import { formatDateRange } from '@/shared/lib/format'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import { Modal } from '@/shared/ui/Modal'
import { ToriNote } from '@/shared/ui/ToriNote'

interface CompleteConfirmModalProps {
  open: boolean
  event: EventDetail
  // 아직 끝나지 않은 단계 수
  remainingSteps: number
  // 아직 검토하지 않은 승인 대기 수
  pendingApprovals: number
  pending: boolean
  onClose: () => void
  onConfirm: () => void
}

export function CompleteConfirmModal({
  open,
  event,
  remainingSteps,
  pendingApprovals,
  pending,
  onClose,
  onConfirm,
}: CompleteConfirmModalProps) {
  const leftovers = [
    remainingSteps > 0 && `끝나지 않은 단계 ${remainingSteps}개`,
    pendingApprovals > 0 && `검토하지 않은 승인 ${pendingApprovals}건`,
  ].filter((item): item is string => Boolean(item))

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="행사를 완료로 표시할까요?"
      chip={<Chip tone="failed">되돌릴 수 없음</Chip>}
      subtitle={[event.title, formatDateRange(event.startDate, event.endDate)]
        .filter(Boolean)
        .join(' · ')}
      width={520}
      footer={
        <span className="flex gap-[8px]">
          <Button variant="secondary" onClick={onClose}>
            아직이에요
          </Button>
          <Button disabled={pending} onClick={onConfirm}>
            {pending ? '처리하는 중…' : '완료로 표시'}
          </Button>
        </span>
      }
    >
      <div className="flex flex-col gap-[14px]">
        {leftovers.length > 0 && (
          <ToriNote title="아직 남은 일이 있어요">{leftovers.join(' · ')}</ToriNote>
        )}
        <ul className="flex flex-col gap-[7px] text-[13px] leading-[20px] text-ink2">
          <li>완료한 뒤에는 승인·거절·단계 완료를 더 처리할 수 없어요.</li>
          <li>지난 기록은 그대로 남아서 언제든 다시 볼 수 있어요.</li>
          <li>정산과 환급이 끝났는지 먼저 확인해 주세요.</li>
        </ul>
      </div>
    </Modal>
  )
}
