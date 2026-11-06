// 동아리 정보 수정(#213). 회장만 들어온다 — 서버도 OWNER 만 받는다.
// 현재 값은 GET /clubs/{clubId} 로 채운다(#223). /me 는 이름과 역할만 준다.
import { useState } from 'react'
import { clubErrorMessage, useUpdateClub } from '@/features/clubs/hooks'
import { CLUB_CATEGORIES, type Club } from '@/features/clubs/types'
import { cn } from '@/shared/lib/cn'
import { CLUB_CATEGORY_LABEL } from '@/shared/lib/labels'
import { Field } from '@/shared/ui/AuthShell'
import { Button } from '@/shared/ui/Button'
import { Input, Textarea } from '@/shared/ui/Input'

interface ClubEditFormProps {
  club: Club
  onDone: () => void
}

export function ClubEditForm({ club, onDone }: ClubEditFormProps) {
  const update = useUpdateClub(club.id)
  const [name, setName] = useState(club.name)
  const [category, setCategory] = useState(club.category)
  const [description, setDescription] = useState(club.description ?? '')
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
        // 비우면 null 로 보낸다 — 서버가 그 값을 지운다.
        category,
        description: description.trim() || null,
      })
      onDone()
    } catch (cause) {
      setError(clubErrorMessage(cause))
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

      <Field label="분야" hint="다시 누르면 선택을 지웁니다">
        <div className="flex flex-wrap gap-[7px]">
          {CLUB_CATEGORIES.map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={item === category}
              onClick={() => setCategory(item === category ? null : item)}
              className={cn(
                'rounded-[8px] border px-[13px] py-[7px] text-[11.5px] font-bold transition-colors duration-150 motion-reduce:transition-none',
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
        <Textarea value={description} onChange={(event) => setDescription(event.target.value)} />
      </Field>

      <div className="flex gap-[8px]">
        <Button type="submit" loading={update.isPending} disabled={!name.trim()}>
          {update.isPending ? '저장하는 중…' : '저장'}
        </Button>
        <Button type="button" variant="ghost" disabled={update.isPending} onClick={onDone}>
          취소
        </Button>
      </div>
    </form>
  )
}
