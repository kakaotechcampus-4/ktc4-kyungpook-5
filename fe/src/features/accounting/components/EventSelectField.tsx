// 지출을 행사에 연결하는 선택 칸 (#367). 직접 입력 폼과 영수증 확정 화면이 함께 쓴다.
// 선택지 이름·순서는 장부 표와 같은 규칙(eventOptions)이다.
import { useMemo } from 'react'
import { eventOptions } from '@/features/accounting/eventLabels'
import { useEvents } from '@/features/events/hooks'
import { Field } from '@/shared/ui/AuthShell'

interface EventSelectFieldProps {
  // '' 는 연결 안 함.
  value: string
  onChange: (eventId: string) => void
  disabled?: boolean
  // 있으면 칸을 잠그고 이 문구를 보인다(예: 자동 기록).
  lockedHint?: string
  // 행사 목록을 못 받았을 때 저장하면 어떻게 되는지.
  failedHint: string
  // 이미 연결된 행사. 선택지에 없어도(목록을 받는 중·실패 등) 값을 잃지 않게 한 줄 더 둔다.
  linkedEventId?: string | null
}

export function EventSelectField({
  value,
  onChange,
  disabled,
  lockedHint,
  failedHint,
  linkedEventId,
}: EventSelectFieldProps) {
  const events = useEvents()
  const options = useMemo(() => eventOptions(events.data ?? []), [events.data])
  const linkedMissing = !!linkedEventId && !options.some((o) => o.id === linkedEventId)
  const hint =
    lockedHint ??
    (events.isLoading ? '행사 목록을 불러오는 중이에요' : events.isError ? failedHint : undefined)

  return (
    <Field label="행사" hint={hint}>
      <select
        className="w-full rounded-[11px] border border-soft bg-bg px-[15px] py-[12px] text-[13.5px] text-ink outline-none focus:border-blue-600 focus:bg-card disabled:text-mute"
        disabled={disabled || !!lockedHint || events.isLoading || events.isError}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">연결 안 함</option>
        {linkedMissing && linkedEventId && <option value={linkedEventId}>연결된 행사</option>}
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  )
}
