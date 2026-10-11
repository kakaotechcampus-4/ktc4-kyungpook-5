// ④ 새 동아리 입력. 생성 모드에서만 보인다. 소개는 나중에 채워도 되는 값이라 선택이다.
import { Field } from '@/features/auth/components/AuthShell'
import type { ClubField } from '@/features/auth/types'
import { CLUB_FIELDS } from '@/features/auth/types'
import { cn } from '@/shared/lib/cn'
import { Input, Textarea } from '@/shared/ui/Input'

interface NewClubFieldsProps {
  name: string
  onNameChange: (value: string) => void
  field: ClubField
  onFieldChange: (value: ClubField) => void
  intro: string
  onIntroChange: (value: string) => void
}

export function NewClubFields({
  name,
  onNameChange,
  field,
  onFieldChange,
  intro,
  onIntroChange,
}: NewClubFieldsProps) {
  return (
    <div className="flex flex-col gap-[14px]">
      <Field label="동아리 이름" required>
        <Input
          placeholder="동아리 이름을 적어주세요"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
        />
      </Field>

      <Field label="분야">
        <div className="flex flex-wrap gap-[7px]">
          {CLUB_FIELDS.map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={item === field}
              onClick={() => onFieldChange(item)}
              className={cn(
                'rounded-[8px] border px-[13px] py-[7px] text-[11.5px] font-bold',
                item === field
                  ? 'border-blue-600 bg-blue-600 text-white'
                  : 'border-soft bg-card text-ink2 hover:bg-bg',
              )}
            >
              {item}
            </button>
          ))}
        </div>
      </Field>

      <Field label="소개">
        <Textarea
          placeholder="나중에 적어도 괜찮아요"
          value={intro}
          onChange={(e) => onIntroChange(e.target.value)}
        />
      </Field>
    </div>
  )
}
