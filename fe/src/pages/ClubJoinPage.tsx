import { Link, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/shared/auth/store'
import { AuthShell } from '@/shared/ui/AuthShell'
import { Card } from '@/shared/ui/Card'

export default function ClubJoinPage() {
  const token = useAuthStore((state) => state.token)
  if (!token) return <Navigate to="/login" replace />

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
            <p className="text-mute">초대 기능을 현재 사용할 수 없어요.</p>
          </div>
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
