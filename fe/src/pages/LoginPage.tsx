import { Link } from 'react-router-dom'
import { AuthShell } from '@/shared/ui/AuthShell'
import { LoginForm } from '@/features/auth/components/LoginForm'
import { Tori } from '@/shared/ui/Tori'

export default function LoginPage() {
  return (
    <AuthShell>
      <Tori size={76} />
      <h1 className="mt-[14px] text-display text-ink">운영해</h1>
      <p className="mt-[6px] text-[12px] text-mute">팀·조직의 회의와 다음 할 일을 함께 챙겨요</p>
      <LoginForm />
      <Link to="/onboarding" className="mt-4 text-[12px] font-bold text-blue-700 underline">
        처음 사용 가이드 다시 보기
      </Link>
    </AuthShell>
  )
}
