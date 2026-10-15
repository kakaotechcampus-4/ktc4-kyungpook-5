// 답변 입력 모달. 확인 요청(CONFIRMATION)의 [답변하기]로 연다.
// 확인 요청은 승인할 일이 아니라 토리가 모르는 걸 묻는 질문이라, 고르면 바로 완료로 간다.
import { useState } from 'react'
import type { EventAction } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import { Textarea } from '@/shared/ui/Input'
import { Modal } from '@/shared/ui/Modal'
import { ToriNote } from '@/shared/ui/ToriNote'

// 보기 중에 없을 때 직접 적는 자리. allowManual이 켜진 질문에만 보인다.
// 값은 서버에 보내는 choice와 같다(L2 확인 요청 카드의 직접 처리와 같은 값).
const MANUAL_KEY = 'MANUAL'

interface AnswerModalProps {
  action?: EventAction
  onClose: () => void
  // choice는 options[].key, 직접 처리면 'MANUAL'이고 적은 내용은 manualValue로 준다
  // (POST /actions/{id}/resolve 요청 값과 같다)
  onAnswer: (action: EventAction, choice: string, manualValue?: string) => void
}

export function AnswerModal({ action, onClose, onAnswer }: AnswerModalProps) {
  const [picked, setPicked] = useState<string>()
  const [manual, setManual] = useState('')

  // 답변·닫기 어느 쪽으로 끝나든 비운다. 모달은 화면에 남아 있어 다음 질문으로 넘어가기 때문이다.
  const reset = () => {
    setPicked(undefined)
    setManual('')
  }

  const close = () => {
    reset()
    onClose()
  }

  if (!action) return null

  const options = action.options ?? []
  const manualValue = manual.trim()
  // 보기를 골랐거나, 직접 처리면 내용까지 적어야 보낼 수 있다
  const choice =
    picked === MANUAL_KEY
      ? manualValue
        ? MANUAL_KEY
        : undefined
      : options.find((o) => o.key === picked)?.key

  const submit = () => {
    if (!choice) return
    reset()
    onAnswer(action, choice, choice === MANUAL_KEY ? manualValue : undefined)
  }

  return (
    <Modal
      open
      onClose={close}
      title={action.title}
      chip={<Chip tone="pending">질문 대기</Chip>}
      subtitle="토리가 모르는 것을 묻고 있어요"
      width={600}
      footerNote="답변하면 바로 완료로 가요"
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            취소
          </Button>
          <Button disabled={!choice} onClick={submit}>
            답변 완료
          </Button>
        </>
      }
    >
      {action.subtitle && (
        <p className="rounded-[11px] border border-line bg-bg px-[14px] py-[12px] text-[12.5px] leading-[19px] text-ink2">
          {action.subtitle}
        </p>
      )}

      <div className="flex flex-col gap-[8px]">
        <span className="text-[11.5px] font-bold text-ink2">답변 고르기</span>
        {options.map((option) => (
          <button
            key={option.key}
            type="button"
            aria-pressed={picked === option.key}
            onClick={() => setPicked(option.key)}
            className={cn(
              'flex items-center gap-[10px] rounded-[11px] border px-[14px] py-[12px] text-left',
              picked === option.key
                ? 'border-blue-600 bg-blue-50'
                : 'border-soft bg-card hover:bg-bg',
            )}
          >
            <span
              className={cn(
                'flex size-[15px] shrink-0 items-center justify-center rounded-full border',
                picked === option.key ? 'border-blue-600' : 'border-soft',
              )}
            >
              {picked === option.key && <span className="size-[7px] rounded-full bg-blue-600" />}
            </span>
            <span
              className={cn(
                'text-[12.5px] font-bold',
                picked === option.key ? 'text-blue-700' : 'text-ink',
              )}
            >
              {option.label}
            </span>
          </button>
        ))}

        {action.allowManual && (
          <button
            type="button"
            aria-pressed={picked === MANUAL_KEY}
            onClick={() => setPicked(MANUAL_KEY)}
            className={cn(
              'rounded-[11px] border px-[14px] py-[12px] text-left text-[12.5px] font-bold',
              picked === MANUAL_KEY
                ? 'border-blue-600 bg-blue-50 text-blue-700'
                : 'border-soft bg-card text-ink hover:bg-bg',
            )}
          >
            직접 처리
          </button>
        )}
      </div>

      {picked === MANUAL_KEY && (
        <Textarea
          label="어떻게 처리할지"
          placeholder="어떻게 하면 되는지 적어 주세요"
          maxLength={200}
          value={manual}
          onChange={(e) => setManual(e.target.value)}
        />
      )}

      <ToriNote title="답변은 기록에 남아요">
        다음 행사 때 같은 걸 다시 묻지 않도록 이 답을 기억해 둘게요.
      </ToriNote>
    </Modal>
  )
}
