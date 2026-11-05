// 운영진 초대. 메일을 보내지 않고 초대 코드를 만들어 보여준다 — 만든 사람이 직접 전한다.
//
// 코드는 응답에 한 번만 나오고 서버에는 해시만 남는다. 창을 닫으면 다시 볼 수 없으므로
// 닫기 전에 복사하라고 분명히 적는다.
import { useState } from 'react'
import { clubErrorMessage, useCreateInvitation } from '@/features/clubs/hooks'
import { copyText } from '@/shared/lib/clipboard'
import { toast } from '@/shared/lib/toast'
import { Field } from '@/shared/ui/AuthShell'
import { Button } from '@/shared/ui/Button'
import { Input } from '@/shared/ui/Input'
import { Modal } from '@/shared/ui/Modal'
import { ToriNote } from '@/shared/ui/ToriNote'

type StaffRole = 'OWNER' | 'MANAGER'

const ROLES: Array<{ value: StaffRole; label: string; desc: string }> = [
  { value: 'MANAGER', label: '임원', desc: '승인과 처리를 함께 맡아요' },
  { value: 'OWNER', label: '회장', desc: '동아리 정보까지 고칠 수 있어요' },
]

interface InviteStaffModalProps {
  open: boolean
  clubId: string
  onClose: () => void
}

export function InviteStaffModal({ open, clubId, onClose }: InviteStaffModalProps) {
  const create = useCreateInvitation()
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<StaffRole>('MANAGER')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')

  const close = () => {
    setEmail('')
    setRole('MANAGER')
    setCode('')
    setError('')
    onClose()
  }

  const submit = async () => {
    if (create.isPending || !email.trim()) return
    setError('')
    try {
      const result = await create.mutateAsync({ clubId, email: email.trim(), role })
      setCode(result.token)
    } catch (cause) {
      setError(clubErrorMessage(cause))
    }
  }

  const copy = async () => {
    toast.show(
      (await copyText(code))
        ? { kind: 'done', title: '초대 코드를 복사했어요' }
        : { kind: 'error', title: '복사하지 못했어요', desc: '코드를 직접 선택해 복사해 주세요.' },
    )
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="운영진 초대"
      subtitle={code ? '아래 코드를 전해 주세요' : '초대할 사람의 이메일과 역할을 정해 주세요'}
      width={520}
      footerNote={code ? '창을 닫으면 코드를 다시 볼 수 없어요' : undefined}
      footer={
        code ? (
          <span className="flex gap-[8px]">
            <Button variant="secondary" onClick={close}>
              닫기
            </Button>
            <Button onClick={() => void copy()}>코드 복사</Button>
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
              초대 코드 만들기
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

        {code ? (
          <>
            <p
              className="select-all break-all rounded-[12px] bg-bg px-[16px] py-[18px] text-center text-[15px] font-bold"
              role="status"
            >
              {code}
            </p>
            <ToriNote title="전할 때 알아두세요">
              코드를 가진 사람은 누구나 이 동아리의 운영진이 돼요. 초대하려는 사람에게만
              전해 주세요.
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
            <Field label="역할">
              <div className="flex flex-col gap-[7px]">
                {ROLES.map((item) => (
                  <label
                    key={item.value}
                    className="flex items-center gap-[9px] text-[12.5px] text-ink2"
                  >
                    <input
                      type="radio"
                      name="invite-role"
                      checked={role === item.value}
                      onChange={() => setRole(item.value)}
                    />
                    <span className="font-bold text-ink">{item.label}</span>
                    <span className="text-mute">{item.desc}</span>
                  </label>
                ))}
              </div>
            </Field>
          </>
        )}
      </div>
    </Modal>
  )
}
