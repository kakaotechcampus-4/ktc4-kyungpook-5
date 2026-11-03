// 초대 코드로 참여. 코드는 회장·임원이 보낸 초대 링크에 들어 있다.
import { useState } from 'react'
import { Field } from '@/shared/ui/AuthShell'
import { Button } from '@/shared/ui/Button'
import { Input } from '@/shared/ui/Input'

interface ClubJoinFormProps {
  pending: boolean
  onSubmit: (token: string) => void
}

export function ClubJoinForm({ pending, onSubmit }: ClubJoinFormProps) {
  const [token, setToken] = useState('')

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (pending || !token.trim()) return
    onSubmit(token.trim())
  }

  return (
    <form className="flex flex-col gap-[16px]" onSubmit={submit}>
      <Field label="초대 코드" required hint="회장·임원이 보낸 초대에 들어 있어요">
        <Input
          placeholder="초대 코드를 붙여넣어 주세요"
          value={token}
          onChange={(event) => setToken(event.target.value)}
        />
      </Field>
      <Button type="submit" size="lg" disabled={pending || !token.trim()}>
        {pending ? '확인하는 중…' : '참여하기'}
      </Button>
    </form>
  )
}
