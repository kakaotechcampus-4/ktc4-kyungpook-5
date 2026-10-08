// 행사 취소 확인 모달. 취소 정리 화면으로 들어가는 입구다.
// 되돌릴 수 없는 일이라 무슨 일이 생기는지 먼저 보이고, 체크를 해야 버튼이 켜진다.
import { useState } from 'react'
import type { EventDetail } from '@/features/events/types'
import { formatDateRange } from '@/shared/lib/format'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import { Modal } from '@/shared/ui/Modal'
import { ToriNote } from '@/shared/ui/ToriNote'

const CONSEQUENCES = [
  '승인 대기 중인 일이 모두 취소돼요',
  '남은 단계가 더 진행되지 않아요',
  '이미 보낸 공지와 이체는 되돌릴 수 없어요',
]

interface CancelConfirmModalProps {
  open: boolean
  event: EventDetail
  onClose: () => void
  onConfirm: () => void
}

export function CancelConfirmModal({ open, event, onClose, onConfirm }: CancelConfirmModalProps) {
  const [agreed, setAgreed] = useState(false)

  const close = () => {
    setAgreed(false)
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="행사를 취소할까요?"
      chip={<Chip tone="failed">되돌릴 수 없음</Chip>}
      subtitle={[
        event.title,
        formatDateRange(event.startDate, event.endDate),
        event.headcount ? `${event.headcount}명` : null,
      ]
        .filter(Boolean)
        .join(' · ')}
      width={600}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            돌아가기
          </Button>
          <Button variant="danger" disabled={!agreed} onClick={onConfirm}>
            행사 취소하기
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-[9px] rounded-[12px] border border-failed-line bg-failed-bg px-[16px] pt-[14px] pb-[15px]">
        <span className="text-[12.5px] font-bold text-failed">취소하면 이렇게 됩니다</span>
        <ul className="flex flex-col gap-[5px]">
          {CONSEQUENCES.map((line) => (
            <li key={line} className="text-[12px] leading-[18px] text-failed">
              · {line}
            </li>
          ))}
        </ul>
      </div>

      <ToriNote title="취소 정리를 도와드릴게요">
        취소하면 참가자 안내 · 예약 취소 · 환불 · 정산 기록 네 단계를 만들어서 차례로 안내해 드려요.
      </ToriNote>

      <label className="flex items-center gap-[9px]">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="size-[16px] accent-blue-600"
        />
        <span className="text-[12px] text-ink2">위 내용을 확인했습니다</span>
      </label>
    </Modal>
  )
}
