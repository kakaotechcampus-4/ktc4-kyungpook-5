import { Navigate } from 'react-router-dom'
import { useMe } from '@/features/auth/hooks'
import { onboardingEntry } from '@/features/onboarding/entry'
import { useAuthStore } from '@/shared/auth/store'
import { Button } from '@/shared/ui/Button'
import { StateScreen } from '@/shared/ui/StateScreen'

export default function MainEntryPage() {
  const token = useAuthStore((state) => state.token)
  const me = useMe()

  if (token && me.isPending) {
    return <StateScreen title="로그인 상태를 확인하고 있어요" desc="잠시만 기다려 주세요." />
  }
  if (token && me.isError) {
    return (
      <StateScreen
        title="로그인 상태를 확인하지 못했어요"
        desc="연결을 확인하고 다시 시도해 주세요."
      >
        <Button onClick={() => void me.refetch()}>다시 확인</Button>
      </StateScreen>
    )
  }
  return <Navigate to={onboardingEntry(Boolean(token && me.data))} replace />
}
