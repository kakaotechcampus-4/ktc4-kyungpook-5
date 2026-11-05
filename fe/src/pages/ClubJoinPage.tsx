import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useMe } from '@/features/auth/hooks'
import { clubErrorMessage, useJoinClub } from '@/features/clubs/hooks'
import { useAuthStore } from '@/shared/auth/store'
import { AuthShell, ErrorBanner, Field } from '@/shared/ui/AuthShell'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'

export default function ClubJoinPage() {
  const token = useAuthStore((state) => state.token)
  const selectClub = useAuthStore((state) => state.selectClub)
  const me = useMe()
  const navigate = useNavigate()
  const join = useJoinClub()
  const [code, setCode] = useState('')
  const [error, setError] = useState('')

  if (!token) return <Navigate to="/login" replace />

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (join.isPending || !code.trim()) return
    setError('')
    try {
      const result = await join.mutateAsync(code.trim())
      // 들어간 동아리를 바로 쓰려면 /me 의 소속 목록부터 다시 받아야 한다.
      await me.refetch()
      selectClub(result.clubId)
      navigate('/dashboard')
    } catch (cause) {
      setError(clubErrorMessage(cause))
    }
  }

  return (
    <AuthShell
      topRight={
        <Link to="/login" className="text-blue-700 underline">
          소속 선택으로
        </Link>
      }
    >
      <Card className="w-[480px] max-w-full px-[32px] py-[30px]">
        <form className="flex flex-col gap-[20px]" onSubmit={(event) => void submit(event)}>
          <div className="flex flex-col gap-2">
            <h1 className="text-h1">초대 코드로 참여</h1>
            <p className="text-mute">회장·임원에게 받은 코드를 넣어 주세요.</p>
          </div>

          {error && <ErrorBanner title={error} />}

          <Field label="초대 코드" required>
            <Input
              autoComplete="off"
              placeholder="받은 코드를 붙여넣어 주세요"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </Field>

          <Button type="submit" size="lg" loading={join.isPending} disabled={!code.trim()}>
            {join.isPending ? '확인하는 중…' : '참여하기'}
          </Button>

          <p className="text-center text-[12px] text-mute">
            아직 동아리가 없다면{' '}
            <Link to="/clubs/new" className="font-bold text-blue-700 underline">
              직접 만들기
            </Link>
          </p>
        </form>
      </Card>
    </AuthShell>
  )
}
