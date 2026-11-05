// 결정 검토 모달. Action 카드의 [검토하기]로 연다.
// 승인하기 전에 무엇을 보고 판단하는지가 유형마다 달라, 가운데 본문만 유형별로 갈린다.
// 겉 틀(제목·출처·토리 주의·하단)은 어느 유형이든 같다.
// 공지·발송은 보낼 내용을 여기서 고쳐 저장한다(#335). 실행 대기 공지의 [내용 고치기]도 이 모달을 연다.
import { useState } from 'react'
import {
  blanksIn,
  canSave,
  draftView,
  editorText,
  isDirty,
  isDraftTarget,
  startEdit,
  type ActionOutcome,
  type ContentEdit,
} from '@/features/events/actionDraft'
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

// 저장·승인 뒤 본문 위에 띄우는 안내
// saveConflict: 고치는 사이 초안이 도착해 저장이 막힘 · approveConflict: 승인하려는 사이 초안이 도착함
// reapprove: 승인된 공지를 고쳐 승인 대기로 돌아감
type Notice = 'saveConflict' | 'approveConflict' | 'reapprove' | null

interface ReviewModalProps {
  action?: EventAction
  onClose: () => void
  onApprove: (action: EventAction) => Promise<ActionOutcome>
  onDeny: (action: EventAction, reason: string) => Promise<boolean>
  // 본문 저장. expectedVersion은 고치기 시작한 때의 version이다.
  onSaveContent?: (
    action: EventAction,
    content: string,
    expectedVersion: number | undefined,
  ) => Promise<ActionOutcome>
  pending: boolean
  saving?: boolean
}

export function ReviewModal({
  action,
  onClose,
  onApprove,
  onDeny,
  onSaveContent,
  pending,
  saving = false,
}: ReviewModalProps) {
  // 진행하지 않기를 누르면 사유를 받는다. 사유 없이는 넘어가지 않는다.
  const [denying, setDenying] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState(false)
  // 고치는 중인 본문. 열려 있는 동안 다시 조회해도 입력한 글을 덮지 않는다.
  const [edit, setEdit] = useState<ContentEdit | null>(null)
  const [notice, setNotice] = useState<Notice>(null)

  // 승인·거절·닫기 어느 쪽으로 끝나든 비운다. 모달은 화면에 남아 있어 다음 Action으로 넘어가기 때문이다.
  const reset = () => {
    setDenying(false)
    setReason('')
    setError(false)
    setEdit(null)
    setNotice(null)
  }

  if (!action) return null

  const busy = pending || saving
  const editable =
    !!onSaveContent &&
    isDraftTarget(action.type) &&
    (action.status === 'PENDING' || action.status === 'APPROVED')
  const approved = action.status === 'APPROVED'
  const text = editorText(action, edit)
  const dirty = isDirty(action, edit)
  const blanks = blanksIn(text)
  const view = draftView(action)
  const warning = MANUAL_WARNING[action.type]

  const close = () => {
    if (dirty && !window.confirm('저장하지 않은 수정이 있어요. 닫으면 고친 글이 사라져요.')) return
    reset()
    onClose()
  }

  const save = async (expectedVersion: number | undefined) => {
    if (!onSaveContent) return
    setError(false)
    const outcome = await onSaveContent(action, text, expectedVersion)
    if (outcome === 'ok') {
      // 목록은 이미 다시 불러왔다. 입력칸은 저장된 본문을 그대로 따라간다.
      setEdit(null)
      setNotice(approved ? 'reapprove' : null)
    } else if (outcome === 'conflict') {
      // 입력한 글은 그대로 두고 어느 쪽으로 할지 고르게 한다
      setNotice('saveConflict')
    } else {
      setError(true)
    }
  }

  const approve = async () => {
    setError(false)
    const outcome = await onApprove(action)
    if (outcome === 'ok') reset()
    else if (outcome === 'conflict') {
      setEdit(null)
      setNotice('approveConflict')
    } else setError(true)
  }

  // 머리글 칩과 하단. 실행 대기 공지는 고치기만 할 수 있고, 고쳐 저장하면 승인 대기로 돌아간다.
  const footer = approved ? (
    <Button variant="secondary" disabled={busy} onClick={close}>
      닫기
    </Button>
  ) : denying ? (
    <>
      <Button variant="secondary" disabled={busy} onClick={() => setDenying(false)}>
        취소
      </Button>
      <Button
        variant="danger"
        disabled={busy || !reason.trim()}
        onClick={() => { setError(false); void onDeny(action, reason.trim()).then((success) => { if (success) reset(); else setError(true) }) }}
      >
        진행하지 않기
      </Button>
    </>
  ) : (
    <>
      <Button variant="danger" disabled={busy} onClick={() => setDenying(true)}>
        진행하지 않기
      </Button>
      <Button variant="secondary" disabled={busy} onClick={close}>
        나중에 결정
      </Button>
      <Button disabled={busy || dirty} loading={pending} onClick={() => void approve()}>
        이 내용 승인하기
      </Button>
    </>
  )

  const footerNote = approved
    ? '고쳐서 저장하면 다시 승인해야 해요'
    : denying
      ? '사유는 기록에 남습니다'
      : dirty
        ? '고친 내용을 저장한 뒤 승인할 수 있어요'
        : '승인 전에는 아무것도 보내지 않아요'

  return (
    <Modal
      open
      onClose={close}
      // 고친 글이 있으면 Esc·바깥 누르기로 닫지 않는다. 버튼으로 닫을 때 한 번 더 묻는다.
      dismissible={!busy && !dirty}
      title={action.title}
      chip={approved ? <Chip tone="approved">실행 대기</Chip> : <Chip tone="pending">승인 대기</Chip>}
      subtitle={[ACTION_TYPE_LABEL[action.type], action.subtitle].filter(Boolean).join(' · ')}
      footerNote={footerNote}
      footer={footer}
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
          disabled={busy}
          placeholder="왜 하지 않기로 했는지 적어 주세요"
          maxLength={200}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      ) : (
        <>
          {notice === 'saveConflict' && (
            <ToriNote title="토리 초안이 도착했어요" tone="cream">
              <div role="alert" className="flex flex-col gap-[10px]">
                <p>입력한 글은 그대로 있어요. 토리 초안으로 바꾸거나, 내 글로 저장해 주세요.</p>
                <div className="flex flex-wrap gap-[8px]">
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={busy}
                    onClick={() => { setEdit(null); setNotice(null) }}
                  >
                    토리 초안 보기
                  </Button>
                  <Button
                    size="sm"
                    disabled={busy || !text.trim()}
                    loading={saving}
                    onClick={() => void save(action.version)}
                  >
                    내 글로 저장
                  </Button>
                </div>
              </div>
            </ToriNote>
          )}
          {notice === 'approveConflict' && (
            <ToriNote title="토리 초안이 도착했어요">
              <p role="alert">내용을 확인한 뒤 승인해 주세요.</p>
            </ToriNote>
          )}
          {notice === 'reapprove' && (
            <ToriNote title="고친 내용으로 다시 승인이 필요해요" tone="cream">
              <p role="status">확인한 뒤 「이 내용 승인하기」를 눌러 주세요.</p>
            </ToriNote>
          )}

          {editable ? (
            <div className="flex flex-col gap-[8px]">
              <div className="flex flex-wrap items-baseline justify-between gap-x-[12px] gap-y-[2px]">
                <label htmlFor={`content-${action.id}`} className="text-[11.5px] font-bold text-ink2">
                  보낼 내용
                </label>
                <span className={dirty ? 'text-[11px] font-medium text-pending' : 'text-[11px] text-mute'}>
                  {dirty
                    ? '저장하지 않은 수정이 있어요'
                    : action.contentSource === 'USER'
                      ? '직접 고친 내용'
                      : action.contentSource === 'AI'
                        ? '토리가 준비한 초안'
                        : ''}
                </span>
              </div>
              {/* 토리가 쓰는 동안에도 직접 쓸 수 있다. 그사이 초안이 오면 저장할 때 고르게 한다. */}
              {view === 'DRAFTING' && !dirty && (
                <p role="status" className="text-[12px] leading-[18px] text-mute">
                  토리가 초안을 쓰고 있어요. 기다리거나 직접 써도 돼요.
                </p>
              )}
              {view === 'FAILED' && !dirty && !text && (
                <p className="text-[12px] leading-[18px] text-mute">
                  초안을 받지 못했어요. 직접 쓰거나, 본문 없이 승인할 수 있어요.
                </p>
              )}
              <Textarea
                id={`content-${action.id}`}
                rows={8}
                disabled={busy}
                placeholder="보낼 내용을 적어 주세요"
                value={text}
                onChange={(e) => setEdit(startEdit(action, edit, e.target.value))}
              />
              <div className="flex flex-wrap items-center justify-between gap-[8px]">
                <span className="min-w-0 text-[11px] leading-[16px] break-words text-pending">
                  {blanks.length > 0 && `아직 비워 둔 곳: ${blanks.join(', ')}`}
                </span>
                {notice !== 'saveConflict' && (
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={busy || !canSave(action, edit)}
                    loading={saving}
                    onClick={() => void save(edit?.baseVersion)}
                  >
                    고친 내용 저장
                  </Button>
                )}
              </div>
            </div>
          ) : (
            action.content !== null &&
            action.content !== undefined && (
              <div className="flex flex-col gap-[8px]">
                <span className="text-[11.5px] font-bold text-ink2">보낼 내용</span>
                <p className="rounded-[11px] border border-line bg-bg px-[14px] py-[12px] text-[12px] leading-[18px] break-words whitespace-pre-line text-ink2">
                  {action.content}
                </p>
              </div>
            )
          )}

          {warning && !approved && (
            <ToriNote title="제가 보내지 않아요" tone="cream">
              {warning}
            </ToriNote>
          )}
        </>
      )}
    </Modal>
  )
}
