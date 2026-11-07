// 임원 초대 링크는 만든 사람이 직접 전한다. 원문은 생성할 때 한 번만 받을 수 있다.
//
// 역할은 임원(MANAGER)으로 고정한다. 회장은 한 명이어야 한다 — 서버는 아직
// OWNER 초대도 받으므로, 이 화면에서만 막혀 있다는 점을 알고 있어야 한다.
import { useState } from 'react'
import { clubErrorMessage, useCreateInvitation } from '@/features/clubs/hooks'
import type { InvitationCreateResult } from '@/features/clubs/types'
import { copyText } from '@/shared/lib/clipboard'
import { toast } from '@/shared/lib/toast'
import { Field } from '@/shared/ui/AuthShell'
import { Button } from '@/shared/ui/Button'
import { Input } from '@/shared/ui/Input'
import { Modal } from '@/shared/ui/Modal'
import { ToriNote } from '@/shared/ui/ToriNote'

interface InviteStaffModalProps {
  open: boolean
  clubId: string
  onClose: () => void
}

export function InviteStaffModal({ open, clubId, onClose }: InviteStaffModalProps) {
  const create = useCreateInvitation()
  const [email, setEmail] = useState('')
  const [invitation, setInvitation] = useState<InvitationCreateResult | null>(null)
  const [error, setError] = useState('')
  const link = invitation
    ? new URL(`/clubs/join#${encodeURIComponent(invitation.token)}`, window.location.origin).href
    : ''

  const close = () => {
    setEmail('')
    setInvitation(null)
    setError('')
    onClose()
  }

  const submit = async () => {
    if (create.isPending || !email.trim()) return
    setError('')
    try {
      const result = await create.mutateAsync({ clubId, email: email.trim(), role: 'MANAGER' })
      setInvitation(result)
    } catch (cause) {
      setError(clubErrorMessage(cause))
    }
  }

  const copy = async () => {
    toast.show(
      (await copyText(link))
        ? { kind: 'done', title: '초대 링크를 복사했어요' }
        : { kind: 'error', title: '복사하지 못했어요', desc: '링크를 직접 선택해 복사해 주세요.' },
    )
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="임원 초대"
      subtitle={invitation ? '아래 링크를 초대할 운영진에게 전해 주세요' : '초대 기록에 남길 이메일을 적어 주세요'}
      width={520}
      footerNote={invitation ? '창을 닫으면 링크를 다시 볼 수 없어요' : undefined}
      footer={
        invitation ? (
          <span className="flex gap-[8px]">
            <Button variant="secondary" onClick={close}>
              닫기
            </Button>
            <Button onClick={() => void copy()}>링크 복사</Button>
          </span>
        ) : (
          <span className="flex gap-[8px]">
            <Button variant="secondary" onClick={close}>
              취소
            </Button>
            <Button
              loading={create.isPending}
              disabled={!email.trim()}
              onClick={() => void submit()}
            >
              초대 링크 만들기
            </Button>
          </span>
        )
      }
    >
      <div className="flex flex-col gap-[16px]">
        {error && (
          <p role="alert" className="text-[12px] font-bold text-failed">
            {error}
          </p>
        )}

        {invitation ? (
          <>
            <p
              className="select-all break-all rounded-[12px] bg-bg px-[16px] py-[18px] text-center text-[15px] font-bold"
              role="status"
            >
              {link}
            </p>
            <p className="text-[12px] text-mute">
              만료{' '}
              <time dateTime={invitation.expiresAt}>
                {new Date(invitation.expiresAt).toLocaleString('ko-KR')}
              </time>
            </p>
            <ToriNote title="전할 때 알아두세요">
              만료 전까지 여러 계정이 같은 링크로 임원으로 참여할 수 있어요. 초대하려는
              사람에게만 전해 주세요.
            </ToriNote>
          </>
        ) : (
          <>
            <Field label="이메일" required hint="메일은 보내지 않아요 · 기록용이에요">
              <Input
                type="email"
                autoComplete="off"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </Field>
            <p className="text-[12px] text-mute">
              임원으로 들어와요. 승인·거절과 단계 처리를 함께 맡습니다.
            </p>
          </>
        )}
      </div>
    </Modal>
  )
}
