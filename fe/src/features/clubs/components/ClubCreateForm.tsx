// 동아리 생성 입력. 분야와 소개는 나중에 채워도 되는 값이라 선택이다.
import { useState } from 'react'
import { CLUB_CATEGORIES, type ClubCategory, type CreateClubInput } from '@/features/clubs/types'
import { cn } from '@/shared/lib/cn'
import { CLUB_CATEGORY_LABEL } from '@/shared/lib/labels'
import { Field } from '@/shared/ui/AuthShell'
import { Button } from '@/shared/ui/Button'
import { Input, Textarea } from '@/shared/ui/Input'

interface ClubCreateFormProps {
  pending: boolean
  onSubmit: (input: CreateClubInput) => void
}

export function ClubCreateForm({ pending, onSubmit }: ClubCreateFormProps) {
  const [name, setName] = useState('')
  const [category, setCategory] = useState<ClubCategory | null>(null)
  const [description, setDescription] = useState('')

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (pending || !name.trim()) return
    onSubmit({
      name: name.trim(),
      category,
      description: description.trim() || null,
    })
  }

  return (
    <form className="flex flex-col gap-[16px]" onSubmit={submit}>
      <Field label="동아리 이름" required>
        <Input
          placeholder="동아리 이름을 적어주세요"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </Field>

      <Field label="분야">
        <div className="flex flex-wrap gap-[7px]">
          {CLUB_CATEGORIES.map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={item === category}
              onClick={() => setCategory(item === category ? null : item)}
              className={cn(
                'rounded-[8px] border px-[13px] py-[7px] text-[11.5px] font-bold',
                item === category
                  ? 'border-blue-600 bg-blue-600 text-white'
                  : 'border-soft bg-card text-ink2 hover:bg-bg',
              )}
            >
              {CLUB_CATEGORY_LABEL[item]}
            </button>
          ))}
        </div>
      </Field>

      <Field label="소개">
        <Textarea
          placeholder="나중에 적어도 괜찮아요"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </Field>

      <Button type="submit" size="lg" disabled={pending || !name.trim()}>
        {pending ? '만드는 중…' : '동아리 만들기'}
      </Button>
    </form>
  )
}
