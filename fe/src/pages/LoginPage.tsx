// S0 로그인. 이메일·비밀번호로 들어오고, 소셜 로그인은 자리만 잡아 둔다.
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthShell, ErrorBanner } from '@/features/auth/components/AuthShell'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Tori } from '@/shared/ui/Tori'

export default function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  // 배너는 로그인이 막혔을 때만. 남은 시도 횟수(hint)는 서버가 알려줘야 채울 수 있다.
  const [error, setError] = useState<{ title: string; hint?: string }>()

  // TODO(연동): POST /auth/login. 지금은 입력만 확인하고 메인으로 보낸다.
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) {
      setError({ title: '이메일과 비밀번호를 모두 입력해 주세요' })
      return
    }
    setError(undefined)
    navigate('/')
  }

  return (
    <AuthShell>
      <Tori size={76} />
      <h1 className="mt-[14px] text-display text-ink">운영해</h1>
      <p className="mt-[6px] text-[12px] text-mute">동아리 활동, 이제 혼자 하지 마세요</p>

      <Card className="mt-[26px] w-[360px] max-w-full px-[32px] py-[28px]">
        <form className="flex flex-col gap-[16px]" onSubmit={submit}>
          {error && <ErrorBanner title={error.title} hint={error.hint} />}

          <Input
            label="이메일"
            type="email"
            autoComplete="email"
            placeholder="name@knu.ac.kr"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            label="비밀번호"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          <Button type="submit" size="lg" className="w-full">
            로그인
          </Button>

          <div className="flex items-center justify-between">
            <button type="button" className="text-[11.5px] text-mute hover:text-ink2">
              비밀번호를 잊었어요
            </button>
            <Link to="/signup" className="text-[11.5px] font-bold text-blue-700 hover:underline">
              처음이신가요? 회원가입 ›
            </Link>
          </div>

          <div className="flex flex-col gap-[9px] border-t border-line pt-[18px]">
            <span className="text-[11px] text-mute">다른 방법으로 계속하기</span>
            {/* TODO(연동): OAuth. 버튼 자리만 잡아 둔다. */}
            <Button type="button" variant="secondary" size="lg" className="w-full">
              Google로 계속하기
            </Button>
            <Button type="button" variant="secondary" size="lg" className="w-full">
              카카오로 계속하기
            </Button>
          </div>
        </form>
      </Card>
    </AuthShell>
  )
}
