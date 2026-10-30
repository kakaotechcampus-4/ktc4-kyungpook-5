import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AuthShell, ErrorBanner, Field } from '@/shared/ui/AuthShell'
import { useSignup } from '@/features/auth/hooks'
import { ApiError } from '@/shared/api/types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'

export default function SignupPage() {
  const signup = useSignup()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [created, setCreated] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (signup.isPending) return
    if (!email.trim() || !name.trim() || password.length < 8) {
      setError('이메일과 이름, 8자 이상의 비밀번호를 확인해 주세요.')
      return
    }
    if (password !== passwordConfirm) {
      setError('비밀번호가 서로 달라요. 다시 확인해 주세요.')
      return
    }
    setError('')
    try {
      await signup.mutateAsync({ email: email.trim(), password, name: name.trim() })
      setPassword('')
      setPasswordConfirm('')
      setCreated(true)
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.code === 'VALIDATION_FAILED'
          ? '입력 정보 또는 이미 가입된 이메일인지 확인해 주세요.'
          : '계정 생성 결과를 확인하지 못했어요. 이미 생성됐을 수 있으니 로그인부터 확인해 주세요.',
      )
    }
  }

  return (
    <AuthShell
      topRight={
        <Link to="/login" className="text-blue-700 underline">
          로그인
        </Link>
      }
    >
      <Card className="w-[480px] max-w-full px-[32px] py-[30px]">
        {created ? (
          <div className="flex flex-col gap-4" role="status">
            <h1 className="text-h1">계정이 만들어졌어요</h1>
            <p className="text-mute">
              로그인할 수 있어요. 이메일 인증 메일 발송과 소속 생성·참여 화면은 아직 준비 중입니다.
            </p>
            <Link to="/login" className="text-blue-700 underline">
              로그인으로 이동
            </Link>
          </div>
        ) : (
          <form className="flex flex-col gap-[20px]" onSubmit={(event) => void submit(event)}>
            <div className="flex flex-col gap-2">
              <h1 className="text-h1">계정 만들기</h1>
              <p className="text-mute">
                계정을 먼저 만들어요. 소속 생성과 참여 화면은 아직 준비 중입니다.
              </p>
              <p className="text-mute">이메일 인증 메일은 아직 발송되지 않습니다.</p>
            </div>
            {error && <ErrorBanner title={error} />}
            <Field label="이메일" required>
              <Input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </Field>
            <Field label="비밀번호" required hint="8자 이상">
              <Input
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
            <Field label="비밀번호 확인" required>
              <Input
                type="password"
                autoComplete="new-password"
                value={passwordConfirm}
                onChange={(event) => setPasswordConfirm(event.target.value)}
              />
            </Field>
            <Field label="이름" required>
              <Input
                autoComplete="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </Field>
            <Button type="submit" size="lg" disabled={signup.isPending}>
              {signup.isPending ? '계정 만드는 중…' : '계정 만들기'}
            </Button>
          </form>
        )}
      </Card>
    </AuthShell>
  )
}
