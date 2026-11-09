// 지출 직접 입력·수정. CSV·영수증 가져오기와 달리 한 건씩 손으로 적는 경로다.
// expense 를 받으면 그 건을 고치고, 없으면 새로 등록한다. 밭 구성이 같아 한 폼을 쓴다.
import { useState } from 'react'
import { EventSelectField } from '@/features/accounting/components/EventSelectField'
import {
  expenseFormErrorMessage,
  useCreateExpense,
  useUpdateExpense,
} from '@/features/accounting/hooks'
import type { Expense } from '@/features/accounting/types'
import { Field } from '@/shared/ui/AuthShell'
import { Button } from '@/shared/ui/Button'
import { Input, Textarea } from '@/shared/ui/Input'

// 날짜만 받고 시각은 그날 0시(한국)로 둔다. 서버는 시각까지 받지만
// 지출 기록에서 분 단위는 의미가 없고, 목록도 한국 날짜로 보여준다.
function toSpentAt(date: string): string {
  return `${date}T00:00:00+09:00`
}

function today(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date())
}

// 서버가 주는 ISO 시각을 <input type="date">가 받는 한국 날짜로 되돌린다.
function toDateInput(iso: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date(iso))
}

interface ExpenseFormProps {
  clubId: string
  // 있으면 수정, 없으면 새 등록.
  expense?: Expense
  onDone: () => void
}

export function ExpenseForm({ clubId, expense, onDone }: ExpenseFormProps) {
  const create = useCreateExpense(clubId)
  const update = useUpdateExpense(clubId)
  const [spentAt, setSpentAt] = useState(() => (expense ? toDateInput(expense.spentAt) : today()))
  const [amount, setAmount] = useState(expense ? String(expense.amount) : '')
  const [merchant, setMerchant] = useState(expense?.merchant ?? '')
  const [category, setCategory] = useState(expense?.category ?? '')
  const [description, setDescription] = useState(expense?.description ?? '')
  // 행사 연결(선택). 수정 때는 사용자가 이 칸을 건드린 경우에만 보낸다 — 행사 목록을
  // 못 받아 선택지가 비어 있어도 기존 연결이 지워지지 않게 한다(서버는 안 보낸 필드를 그대로 둔다).
  const [eventId, setEventId] = useState(expense?.eventId ?? '')
  const [eventTouched, setEventTouched] = useState(false)
  // 송금 행동이 남긴 자동 기록은 그 행사 정산의 일부라 행사를 바꾸지 않는다(#348).
  const eventLocked = expense?.source === 'ACTION'
  const [error, setError] = useState('')

  const won = Number(amount)
  const amountValid = Number.isInteger(won) && won > 0
  const pending = create.isPending || update.isPending

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (pending) return
    if (!spentAt || !amountValid) {
      setError('지출일과 1원 이상의 금액을 확인해 주세요.')
      return
    }
    setError('')
    const fields = {
      spentAt: toSpentAt(spentAt),
      amount: won,
      // 서버 기본값과 같지만 생성 스키마가 필수로 둔다. 통화 선택은 아직 없다.
      currency: 'KRW' as const,
      merchant: merchant.trim() || null,
      category: category.trim() || null,
      description: description.trim() || null,
    }
    try {
      if (expense) {
        // 비운 칸은 null 로 가서 서버가 그 값을 지운다. 그사이 바뀌었으면 409다.
        await update.mutateAsync({
          expenseId: expense.id,
          body: {
            ...fields,
            ...(eventTouched ? { eventId: eventId || null } : {}),
            expectedVersion: expense.version,
          },
        })
      } else {
        await create.mutateAsync({ ...fields, eventId: eventId || null })
      }
      onDone()
    } catch (cause) {
      setError(expenseFormErrorMessage(cause, expense ? '수정' : '등록'))
    }
  }

  return (
    <form
      className="flex flex-col gap-[14px] border-t border-line bg-bg px-[22px] py-[20px]"
      onSubmit={(event) => void submit(event)}
    >
      {error && (
        <p role="alert" className="text-[12px] font-bold text-failed">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-[14px]">
        <div className="min-w-[150px] flex-1">
          <Field label="지출일" required>
            <Input
              type="date"
              value={spentAt}
              onChange={(event) => setSpentAt(event.target.value)}
            />
          </Field>
        </div>
        <div className="min-w-[150px] flex-1">
          <Field label="금액" required hint="원">
            <Input
              type="number"
              min={1}
              step={1}
              inputMode="numeric"
              placeholder="0"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </Field>
        </div>
      </div>
      <div className="flex flex-wrap gap-[14px]">
        <div className="min-w-[150px] flex-1">
          <Field label="사용처">
            <Input
              placeholder="예: 학교 앞 문구점"
              value={merchant}
              onChange={(event) => setMerchant(event.target.value)}
            />
          </Field>
        </div>
        <div className="min-w-[150px] flex-1">
          <Field label="분류">
            <Input
              placeholder="예: 물품비"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            />
          </Field>
        </div>
      </div>
      <EventSelectField
        value={eventId}
        onChange={(next) => {
          setEventId(next)
          setEventTouched(true)
        }}
        disabled={pending}
        lockedHint={eventLocked ? '송금한 행사에 묶인 자동 기록이에요' : undefined}
        failedHint={
          expense
            ? '행사 목록을 못 불러와 기존 연결을 그대로 둬요'
            : '행사 목록을 못 불러와 연결 없이 등록돼요'
        }
        linkedEventId={expense?.eventId}
      />
      <Field label="내용">
        <Textarea
          placeholder="무엇에 썼는지 적어두면 나중에 찾기 쉬워요"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </Field>
      <div className="flex gap-[8px]">
        <Button type="submit" loading={pending} disabled={!amountValid}>
          {expense ? (pending ? '저장하는 중…' : '저장') : pending ? '등록하는 중…' : '등록'}
        </Button>
        <Button type="button" variant="ghost" disabled={pending} onClick={onDone}>
          취소
        </Button>
      </div>
    </form>
  )
}
