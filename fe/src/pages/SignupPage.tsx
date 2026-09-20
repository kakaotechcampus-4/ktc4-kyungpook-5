// SignupPage — 조립만 한다. 로직은 features/ 로.
import { AuthHeader } from '@/features/auth/components/AuthHeader'
import { SignupForm } from '@/features/auth/components/SignupForm'

export default function SignupPage() {
  return (
    <div className="flex min-h-screen w-full flex-col items-center bg-[#f6f6f6]">
      <AuthHeader promptText="이미 계정이 있으신가요?" linkText="로그인" linkTo="/login" />
      <div className="flex w-full flex-1 items-start justify-center px-[26px] pt-[52px] pb-[60px]">
        <SignupForm />
      </div>
    </div>
  )
}
