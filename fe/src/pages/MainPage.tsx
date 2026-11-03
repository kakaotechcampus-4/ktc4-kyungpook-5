import { useMe } from '@/features/auth/hooks'
import { ToriHome } from '@/features/dashboard/components/ToriHome'
import { useAuthStore } from '@/shared/auth/store'
import { Card } from '@/shared/ui/Card'

export default function MainPage() {
  const session = useMe()
  const { token, me } = useAuthStore()
  return (
    <>
      {token && session.isError && !me && (
        <Card role="alert" className="p-4">
          로그인 정보를 확인하지 못했어요.{' '}
          <button className="underline" onClick={() => void session.refetch()}>
            다시 확인
          </button>
        </Card>
      )}
      <ToriHome />
    </>
  )
}
