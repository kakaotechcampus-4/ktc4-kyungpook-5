import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useClubSelection, useMe } from '@/features/auth/hooks'
import { ClubJoinForm } from '@/features/clubs/components/ClubJoinForm'
import { clubErrorMessage, useJoinClub } from '@/features/clubs/hooks'
import { useAuthStore } from '@/shared/auth/store'
import { AuthShell, ErrorBanner } from '@/shared/ui/AuthShell'
import { Card } from '@/shared/ui/Card'

export default function ClubJoinPage() {
  const token = useAuthStore((state) => state.token)
  const me = useMe()
  const chooseClub = useClubSelection()
  const join = useJoinClub()
  const [error, setError] = useState('')

  if (!token) return <Navigate to="/login" replace />

  const submit = async (inviteToken: string) => {
    setError('')
    try {
      const result = await join.mutateAsync(inviteToken)
      // 참여한 동아리를 바로 쓰려면 /me의 소속 목록부터 다시 받아야 한다.
      await me.refetch()
      chooseClub(result.clubId)
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
        <div className="flex flex-col gap-[20px]">
          <div className="flex flex-col gap-2">
            <h1 className="text-h1">초대 코드로 참여</h1>
            <p className="text-mute">회장·임원이 보낸 초대 코드를 넣어주세요.</p>
          </div>
          {error && <ErrorBanner title={error} />}
          <ClubJoinForm pending={join.isPending} onSubmit={(value) => void submit(value)} />
          <p className="text-center text-[12px] text-mute">
            아직 동아리가 없다면{' '}
            <Link to="/clubs/new" className="font-bold text-blue-700 underline">
              직접 만들기
            </Link>
          </p>
        </div>
      </Card>
    </AuthShell>
  )
}
