// 동아리 정보 수정(#213). 보낸 밭만 바뀌므로 적지 않은 칸은 건드리지 않는다.
//
// 지금 분야·소개가 무엇인지 알 방법이 없다 — /me 는 id·이름·역할만 주고 동아리
// 하나를 조회하는 경로가 없다. 그래서 비워 두면 보내지 않는다. 조회가 생기면
// 현재 값을 채워 두고 평범한 수정 폼으로 바꾸면 된다.
import { useState } from 'react'
import { clubUpdateErrorMessage, useUpdateClub } from '@/features/mypage/hooks'
import type { components } from '@/shared/api/schema'
import { cn } from '@/shared/lib/cn'
import { CLUB_CATEGORIES, CLUB_CATEGORY_LABEL } from '@/shared/lib/labels'
import { Field } from '@/shared/ui/AuthShell'
import { Button } from '@/shared/ui/Button'
import { Input, Textarea } from '@/shared/ui/Input'

interface ClubEditFormProps {
  clubId: string
  currentName: string
  onDone: () => void
}

export function ClubEditForm({ clubId, currentName, onDone }: ClubEditFormProps) {
  const update = useUpdateClub(clubId)
  const [name, setName] = useState(currentName)
  const [category, setCategory] = useState<components['schemas']['ClubCategory'] | null>(null)
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (update.isPending) return
    if (!name.trim()) {
      setError('동아리 이름을 적어주세요.')
      return
    }
    setError('')
    try {
      await update.mutateAsync({
        name: name.trim(),
        // 고르지 않았으면 보내지 않는다. null을 보내면 지금 값이 지워진다.
        ...(category ? { category } : {}),
        ...(description.trim() ? { description: description.trim() } : {}),
      })
      onDone()
    } catch (cause) {
      setError(clubUpdateErrorMessage(cause))
    }
  }

  return (
    <form
      className="flex flex-col gap-[14px] border-t border-line pt-[18px]"
      onSubmit={(event) => void submit(event)}
    >
      {error && (
        <p role="alert" className="text-[12px] font-bold text-failed">
          {error}
        </p>
      )}

      <Field label="동아리 이름" required>
        <Input value={name} onChange={(event) => setName(event.target.value)} />
      </Field>

      <Field label="분야" hint="고르지 않으면 그대로 둡니다">
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

      <Field label="소개" hint="비워두면 그대로 둡니다">
        <Textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </Field>

      <div className="flex gap-[8px]">
        <Button type="submit" disabled={update.isPending || !name.trim()}>
          {update.isPending ? '저장하는 중…' : '저장'}
        </Button>
        <Button type="button" variant="ghost" disabled={update.isPending} onClick={onDone}>
          취소
        </Button>
      </div>
    </form>
  )
}
