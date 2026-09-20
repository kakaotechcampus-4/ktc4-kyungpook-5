// S0 로그인 — 조립만 한다. 로직은 features/ 로.
import { AuthHeader } from '@/features/auth/components/AuthHeader'
import { LoginForm } from '@/features/auth/components/LoginForm'

export default function S0LoginPage() {
  return (
    <div className="flex min-h-screen w-full flex-col items-center bg-[#f6f6f6]">
      <AuthHeader promptText="아직 계정이 없으신가요?" linkText="회원가입" linkTo="/signup" />
      <div className="flex w-full flex-1 items-center justify-center pt-[110px] pb-[140px]">
        <LoginForm />
      </div>
    </div>
  )
}
