import { useMe } from '@/features/auth/hooks'
import ServiceHomePage from '@/features/home/ServiceHomePage'
import { useAuthStore } from '@/shared/auth/store'

export default function MainEntryPage() {
  const token = useAuthStore((state) => state.token)
  const me = useMe()
  const signedIn = Boolean(token && me.isSuccess && me.data)

  return (
    <ServiceHomePage
      primaryHref={signedIn ? '/dashboard' : '/login'}
      primaryLabel={signedIn ? '서비스 열기' : '운영해 시작하기'}
    />
  )
}
