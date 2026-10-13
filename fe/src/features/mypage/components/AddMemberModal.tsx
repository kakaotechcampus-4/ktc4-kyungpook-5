// 동아리원 추가 모달. 한 명씩 직접 넣거나 명단 파일로 한 번에 올린다.
import { useState } from 'react'
import type { MemberGroup } from '@/features/mypage/types'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Input } from '@/shared/ui/Input'
import { Modal } from '@/shared/ui/Modal'
import { ToriNote } from '@/shared/ui/ToriNote'

const EXECUTIVE_TITLES = ['회장', '부회장', '총무', '홍보부장', '기타']

type Method = '직접 입력' | '파일로 올리기'

const GROUPS: Array<{ value: MemberGroup; desc: string }> = [
  { value: '임원', desc: '직책이 있는 운영진이에요' },
  { value: '동아리원', desc: '일반 회원이에요' },
]

interface AddMemberModalProps {
  open: boolean
  onClose: () => void
  onAdd: (member: { name: string; group: MemberGroup; subtitle: string; contact?: string }) => void
}

export function AddMemberModal({ open, onClose, onAdd }: AddMemberModalProps) {
  const [method, setMethod] = useState<Method>('직접 입력')
  const [group, setGroup] = useState<MemberGroup>('임원')
  const [name, setName] = useState('')
  // 임원이면 직책, 동아리원이면 학번이 들어간다.
  const [subtitle, setSubtitle] = useState(EXECUTIVE_TITLES[2])
  const [contact, setContact] = useState('')

  const reset = () => {
    setName('')
    setSubtitle(EXECUTIVE_TITLES[2])
    setContact('')
  }

  const submit = () => {
    if (!name.trim()) return
    onAdd({ name: name.trim(), group, subtitle, contact: contact.trim() || undefined })
    reset()
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="동아리원 추가"
      subtitle="명단 파일로 한 번에 올리거나, 한 명씩 직접 입력해요"
      width={600}
      footerNote={method === '직접 입력' ? '추가하면 바로 명단에 보여요' : undefined}
      footer={
        method === '직접 입력' ? (
          <>
            <Button variant="secondary" onClick={onClose}>
              취소
            </Button>
            <Button onClick={submit}>추가하기</Button>
          </>
        ) : (
          <Button variant="secondary" onClick={onClose}>
            닫기
          </Button>
        )
      }
    >
      <div className="flex gap-[4px] rounded-[12px] border border-line bg-bg p-[4px]">
        {(['직접 입력', '파일로 올리기'] as Method[]).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setMethod(item)}
            aria-pressed={item === method}
            className={cn(
              'flex-1 rounded-[9px] py-[9px] text-[12.5px]',
              item === method ? 'bg-blue-600 font-bold text-white' : 'font-medium text-ink2',
            )}
          >
            {item}
          </button>
        ))}
      </div>

      {method === '직접 입력' ? (
        <>
          <div className="flex flex-col gap-[7px]">
            <span className="text-[11.5px] font-bold text-ink2">구분</span>
            <div className="flex gap-[10px]">
              {GROUPS.map((item) => {
                const selected = item.value === group
                return (
                  <button
                    key={item.value}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => {
                      setGroup(item.value)
                      // 임원은 직책, 동아리원은 학번이라 자리가 달라 비운다.
                      setSubtitle(item.value === '임원' ? EXECUTIVE_TITLES[2] : '')
                    }}
                    className={cn(
                      'flex flex-1 items-start gap-[9px] rounded-[12px] border px-[14px] py-[13px] text-left',
                      selected ? 'border-blue-600 bg-blue-50' : 'border-soft bg-card hover:bg-bg',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-[2px] flex size-[15px] shrink-0 items-center justify-center rounded-full border',
                        selected ? 'border-blue-600' : 'border-soft',
                      )}
                    >
                      {selected && <span className="size-[7px] rounded-full bg-blue-600" />}
                    </span>
                    <span className="flex flex-col gap-[3px]">
                      <span
                        className={cn(
                          'text-[12.5px] font-bold',
                          selected ? 'text-blue-700' : 'text-ink',
                        )}
                      >
                        {item.value}
                      </span>
                      <span className="text-[10.5px] text-mute">{item.desc}</span>
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Input의 className은 안쪽 <input>에 붙으므로, 너비는 바깥 div로 나눈다. */}
          <div className="flex gap-[12px]">
            <div className="flex-1">
              <Input
                label="이름"
                placeholder="한도윤"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="flex-1">
              {group === '임원' ? (
                <label className="flex w-full flex-col gap-[7px]">
                  <span className="text-[11.5px] font-bold text-ink2">직책</span>
                  <select
                    value={subtitle}
                    onChange={(e) => setSubtitle(e.target.value)}
                    className="w-full rounded-[11px] border border-soft bg-bg px-[15px] py-[12px] text-[13.5px] text-ink outline-none focus:border-blue-600 focus:bg-card"
                  >
                    {EXECUTIVE_TITLES.map((title) => (
                      <option key={title}>{title}</option>
                    ))}
                  </select>
                </label>
              ) : (
                <Input
                  label="학번"
                  placeholder="22학번"
                  value={subtitle}
                  onChange={(e) => setSubtitle(e.target.value)}
                />
              )}
            </div>
          </div>

          <Input
            label="연락처 (선택)"
            placeholder="010-0000-0000"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
          />
        </>
      ) : (
        <>
          <div className="flex flex-col items-center gap-[9px] rounded-[14px] border-[1.5px] border-dashed border-soft bg-bg px-[20px] py-[34px]">
            <span className="text-[12.5px] font-bold text-ink2">
              명단 파일을 여기로 끌어다 놓기
            </span>
            <span className="text-[11px] text-mute">xlsx · csv 파일만 올릴 수 있습니다</span>
          </div>
          {/* TODO(연동): POST /clubs/{clubId}/members/bulk. 양식·미리보기는 붙일 때 함께 만든다. */}
          <ToriNote title="이름과 학번만 있으면 돼요" tone="cream">
            연락처는 비워도 괜찮아요. 같은 이름이 있으면 올리기 전에 알려드릴게요.
          </ToriNote>
        </>
      )}
    </Modal>
  )
}
