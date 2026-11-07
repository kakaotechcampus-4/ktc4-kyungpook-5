import { useEffect, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useMe } from '@/features/auth/hooks'
import { clubErrorMessage, useJoinClub } from '@/features/clubs/hooks'
import { useAuthStore } from '@/shared/auth/store'
import { AuthShell, ErrorBanner, Field } from '@/shared/ui/AuthShell'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'

const PENDING_INVITATION = 'unyounghae_pending_invitation'

export default function ClubJoinPage() {
  const token = useAuthStore((state) => state.token)
  const selectClub = useAuthStore((state) => state.selectClub)
  const me = useMe()
  const navigate = useNavigate()
  const { hash } = useLocation()
  const join = useJoinClub()
  const inviteFromLink = /^#[A-Za-z0-9_-]+$/.test(hash) ? hash.slice(1) : ''
  const [editedCode, setEditedCode] = useState<string | null>(null)
  const [error, setError] = useState('')
  const code = editedCode ?? (inviteFromLink || sessionStorage.getItem(PENDING_INVITATION) || '')

  // 로그인 복귀 주소에 초대 토큰을 노출하지 않고 같은 탭에서만 이어 간다.
  useEffect(() => {
    if (inviteFromLink) sessionStorage.setItem(PENDING_INVITATION, inviteFromLink)
  }, [inviteFromLink])

  if (!token) return <Navigate to="/login?next=%2Fclubs%2Fjoin" replace />

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (join.isPending || !code.trim()) return
    setError('')
    try {
      const result = await join.mutateAsync(code.trim())
      sessionStorage.removeItem(PENDING_INVITATION)
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
            <h1 className="text-h1">운영진 초대 수락</h1>
            <p className="text-mute">초대 코드를 확인하고 참여해 주세요.</p>
          </div>

          {error && <ErrorBanner title={error} />}

          <Field label="초대 코드" required>
            <Input
              autoComplete="off"
              placeholder="받은 코드를 붙여넣어 주세요"
              value={code}
              onChange={(event) => setEditedCode(event.target.value)}
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
