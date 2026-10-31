// 지출 직접 입력. CSV·영수증 가져오기와 달리 한 건씩 손으로 적는 경로다.
// 등록과 수정이 같은 밭을 쓰므로 한 폼으로 둔다 — expense 를 주면 수정이다.
import { useState } from 'react'
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

// 저장된 시각(UTC)을 한국 날짜로 되돌린다. 넣을 때와 같은 기준이라야 날짜가 안 밀린다.
function toDateInput(iso: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date(iso))
}

interface ExpenseFormProps {
  clubId: string
  // 주면 그 지출을 고치고, 없으면 새로 만든다.
  expense?: Expense
  onDone: () => void
}

export function ExpenseForm({ clubId, expense, onDone }: ExpenseFormProps) {
  const create = useCreateExpense(clubId)
  const update = useUpdateExpense(clubId)
  const [spentAt, setSpentAt] = useState(() =>
    expense ? toDateInput(expense.spentAt) : today(),
  )
  const [amount, setAmount] = useState(expense ? String(expense.amount) : '')
  const [merchant, setMerchant] = useState(expense?.merchant ?? '')
  const [category, setCategory] = useState(expense?.category ?? '')
  const [description, setDescription] = useState(expense?.description ?? '')
  const [error, setError] = useState('')

  const pending = create.isPending || update.isPending
  const won = Number(amount)
  const amountValid = Number.isInteger(won) && won > 0

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (pending) return
    if (!spentAt || !amountValid) {
      setError('지출일과 1원 이상의 금액을 확인해 주세요.')
      return
    }
    setError('')
    const values = {
      spentAt: toSpentAt(spentAt),
      amount: won,
      merchant: merchant.trim() || null,
      category: category.trim() || null,
      description: description.trim() || null,
    }
    try {
      if (expense) {
        // 본 뒤에 바뀌었으면 서버가 거절한다. 전부 다시 보내도 덮어쓰기는 막힌다.
        await update.mutateAsync({
          expense,
          body: { ...values, expectedVersion: expense.version },
        })
      } else {
        // 서버 기본값과 같지만 생성 스키마가 필수로 둔다. 통화 선택은 아직 없다.
        await create.mutateAsync({ ...values, currency: 'KRW' })
      }
      onDone()
    } catch (cause) {
      setError(expenseFormErrorMessage(cause))
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
      <Field label="내용">
        <Textarea
          placeholder="무엇에 썼는지 적어두면 나중에 찾기 쉬워요"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </Field>
      <div className="flex gap-[8px]">
        <Button type="submit" disabled={pending || !amountValid}>
          {pending ? '저장하는 중…' : expense ? '저장' : '등록'}
        </Button>
        <Button type="button" variant="ghost" disabled={pending} onClick={onDone}>
          취소
        </Button>
      </div>
    </form>
  )
}
