// 결정 검토 모달. Action 카드의 [검토하기]로 연다.
// 승인하기 전에 무엇을 보고 판단하는지가 유형마다 달라, 가운데 본문만 유형별로 갈린다.
// 겉 틀(제목·출처·토리 주의·하단)은 어느 유형이든 같다.
import { useState } from 'react'
import type { EventAction } from '@/features/events/types'
import { daysUntil, formatDday, formatMonthDay } from '@/shared/lib/format'
import { ACTION_TYPE_LABEL } from '@/shared/lib/labels'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import { Textarea } from '@/shared/ui/Input'
import { Modal } from '@/shared/ui/Modal'
import { ToriNote } from '@/shared/ui/ToriNote'

// 승인해도 토리가 직접 하지 않는 유형. 운영진이 밖에서 해야 해서 한 번 더 짚는다.
const MANUAL_WARNING: Partial<Record<EventAction['type'], string>> = {
  NOTICE: '승인하시면 문구를 띄워 드릴게요. 올리는 건 직접 해 주세요.',
  EXTERNAL_SEND: '승인하시면 받는 사람과 문구를 띄워 드릴게요. 보내는 건 직접 해 주세요.',
  TRANSFER: '승인하시면 계좌와 금액을 띄워 드릴게요. 이체는 직접 하세요.',
  CONTRACT: '승인하시면 계약 조건을 띄워 드릴게요. 계약은 직접 하세요.',
}

interface ReviewModalProps {
  action?: EventAction
  onClose: () => void
  onApprove: (action: EventAction) => Promise<boolean>
  onDeny: (action: EventAction, reason: string) => Promise<boolean>
  pending: boolean
}

export function ReviewModal({ action, onClose, onApprove, onDeny, pending }: ReviewModalProps) {
  // 진행하지 않기를 누르면 사유를 받는다. 사유 없이는 넘어가지 않는다.
  const [denying, setDenying] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState(false)

  // 승인·거절·닫기 어느 쪽으로 끝나든 비운다. 모달은 화면에 남아 있어 다음 Action으로 넘어가기 때문이다.
  const reset = () => {
    setDenying(false)
    setReason('')
    setError(false)
  }

  const close = () => {
    reset()
    onClose()
  }

  if (!action) return null

  const content = action.content ?? ''
  const warning = MANUAL_WARNING[action.type]

  return (
    <Modal
      open
      onClose={close}
      dismissible={!pending}
      title={action.title}
      chip={<Chip tone="pending">승인 대기</Chip>}
      subtitle={[ACTION_TYPE_LABEL[action.type], action.subtitle].filter(Boolean).join(' · ')}
      footerNote={denying ? '사유는 기록에 남습니다' : '승인 전에는 아무것도 보내지 않아요'}
      footer={
        denying ? (
          <>
            <Button variant="secondary" disabled={pending} onClick={() => setDenying(false)}>
              취소
            </Button>
            <Button
              variant="danger"
              disabled={pending || !reason.trim()}
              onClick={() => { setError(false); void onDeny(action, reason.trim()).then((success) => { if (success) reset(); else setError(true) }) }}
            >
              진행하지 않기
            </Button>
          </>
        ) : (
          <>
            <Button variant="danger" disabled={pending} onClick={() => setDenying(true)}>
              진행하지 않기
            </Button>
            <Button variant="secondary" disabled={pending} onClick={close}>
              나중에 결정
            </Button>
            <Button disabled={pending} onClick={() => { setError(false); void onApprove(action).then((success) => { if (success) reset(); else setError(true) }) }}>
              이 내용 승인하기
            </Button>
          </>
        )
      }
    >
      {error && <p role="alert" className="text-failed">처리하지 못했어요. 연결과 행동 상태를 확인한 뒤 다시 시도해 주세요.</p>}
      {action.dueDate && (
        <div className="flex items-center gap-[9px]">
          <span className="text-[11.5px] text-mute">마감 {formatMonthDay(action.dueDate)}</span>
          <Chip tone="pending" size="sm">
            {formatDday(daysUntil(action.dueDate))}
          </Chip>
        </div>
      )}

      {denying ? (
        <Textarea
          label="진행하지 않는 이유"
          disabled={pending}
          placeholder="왜 하지 않기로 했는지 적어 주세요"
          maxLength={200}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      ) : (
        <>
          {action.content !== null && action.content !== undefined && (
            <div className="flex flex-col gap-[8px]">
              <span className="text-[11.5px] font-bold text-ink2">보낼 내용</span>
              <p className="rounded-[11px] border border-line bg-bg px-[14px] py-[12px] text-[12px] leading-[18px] text-ink2">{content}</p>
            </div>
          )}

          {warning && (
            <ToriNote title="제가 보내지 않아요" tone="cream">
              {warning}
            </ToriNote>
          )}
        </>
      )}
    </Modal>
  )
}
