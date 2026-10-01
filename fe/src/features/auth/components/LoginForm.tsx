// S0 로그인 카드
import { Link } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { Input } from '@/shared/ui/Input'
import { useLoginForm } from '@/features/auth/hooks'

export function LoginForm() {
  const form = useLoginForm()

  return (
    <div className="flex w-[440px] flex-col gap-[22px] rounded-[22px] border border-[#e8e8e8] bg-white p-[34px] shadow-[0px_8px_20px_-6px_rgba(0,0,0,0.05),0px_1px_3px_0px_rgba(0,0,0,0.05)]">
      <div className="flex flex-col gap-[6px]">
        <p className="text-[26px] font-bold text-[#1f1f1f]">로그인</p>
        <p className="text-[13px] text-[#6b6b6b]">동아리 운영을 이어서 하시죠.</p>
      </div>

      <Input
        id="login-email"
        label="이메일"
        type="email"
        placeholder="name@knu.ac.kr"
        value={form.email}
        onChange={(e) => form.setEmail(e.target.value)}
      />

      <div className="flex w-full flex-col gap-[6px]">
        <div className="flex w-full items-center gap-[6px]">
          <span className="text-[12px] font-medium text-[#4d4d4d]">비밀번호</span>
          <div className="h-px flex-1" />
          <button type="button" className="text-[11.5px] font-medium text-[#737373] hover:underline">
            비밀번호를 잊으셨나요?
          </button>
        </div>
        <span className="flex w-full items-center gap-[8px] rounded-[10px] border border-[#d9d9d9] bg-white px-[14px] py-[13px] focus-within:border-[#a3a3a3]">
          <input
            id="login-password"
            type="password"
            placeholder="••••••••"
            className="w-full flex-1 border-none text-[13px] text-[#262626] outline-none placeholder:text-[#999]"
            value={form.password}
            onChange={(e) => form.setPassword(e.target.value)}
          />
        </span>
      </div>

      <label className="flex items-center gap-[10px] text-[12px] text-[#666]">
        <input
          type="checkbox"
          className="size-[18px] rounded-[5px] border-[1.5px] border-[#383838] accent-[#383838]"
          checked={form.keepSignedIn}
          onChange={(e) => form.setKeepSignedIn(e.target.checked)}
        />
        로그인 상태 유지
      </label>

      {form.error && <p className="text-[12px] text-red-600">{form.error}</p>}

      <Button className="w-full" disabled={!form.canSubmit} onClick={() => void form.submit()}>
        {form.submitting ? '로그인 중...' : '로그인'}
      </Button>

      <div className="flex w-full items-center gap-[12px]">
        <div className="h-px flex-1 bg-[#e6e6e6]" />
        <p className="text-[11.5px] text-[#8c8c8c]">또는</p>
        <div className="h-px flex-1 bg-[#e6e6e6]" />
      </div>

      <div className="flex w-full flex-col gap-[9px]">
        <Button variant="secondary" className="w-full">
          <span className="size-[18px] rounded-[6px] bg-[#e0e0e0]" />
          Google 계정으로 계속하기
        </Button>
        <Button variant="secondary" className="w-full">
          <span className="size-[18px] rounded-[6px] bg-[#e0e0e0]" />
          카카오 계정으로 계속하기
        </Button>
      </div>

      <div className="h-px w-full bg-[#ebebeb]" />

      <p className="flex w-full items-center justify-center gap-[6px] text-[12.5px]">
        <span className="text-[#6b6b6b]">아직 계정이 없으신가요?</span>
        <Link to="/signup" className="font-semibold text-[#262626] hover:underline">
          회원가입
        </Link>
      </p>
    </div>
  )
}
