import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useClubSelection, useMe } from '@/features/auth/hooks'
import { ClubCreateForm } from '@/features/clubs/components/ClubCreateForm'
import { clubErrorMessage, useCreateClub } from '@/features/clubs/hooks'
import type { CreateClubInput } from '@/features/clubs/types'
import { useAuthStore } from '@/shared/auth/store'
import { AuthShell, ErrorBanner } from '@/shared/ui/AuthShell'
import { Card } from '@/shared/ui/Card'

export default function ClubCreatePage() {
  const token = useAuthStore((state) => state.token)
  const me = useMe()
  const chooseClub = useClubSelection()
  const create = useCreateClub()
  const [error, setError] = useState('')

  if (!token) return <Navigate to="/login" replace />

  const submit = async (input: CreateClubInput) => {
    setError('')
    try {
      const club = await create.mutateAsync(input)
      // 만든 동아리를 바로 쓰려면 /me의 소속 목록부터 다시 받아야 한다.
      await me.refetch()
      chooseClub(club.id)
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
            <h1 className="text-h1">동아리 만들기</h1>
            <p className="text-mute">만든 사람이 회장이 되고, 바로 이 동아리로 시작해요.</p>
          </div>
          {error && <ErrorBanner title={error} />}
          <ClubCreateForm pending={create.isPending} onSubmit={(input) => void submit(input)} />
          <p className="text-center text-[12px] text-mute">
            이미 있는 동아리에 들어가려면{' '}
            <Link to="/clubs/join" className="font-bold text-blue-700 underline">
              초대 코드로 참여
            </Link>
          </p>
        </div>
      </Card>
    </AuthShell>
  )
}
