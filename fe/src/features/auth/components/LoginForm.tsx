import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  authErrorMessage,
  useClubSelection,
  useLogin,
  useLogout,
  useMe,
} from '@/features/auth/hooks'
import { ErrorBanner } from '@/features/auth/components/AuthShell'
import { useAuthStore } from '@/shared/auth/store'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'

const ROLE_LABEL = { OWNER: '대표', MANAGER: '운영진', MEMBER: '구성원' }

export function LoginForm() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const token = useAuthStore((state) => state.token)
  const me = useAuthStore((state) => state.me)
  const selectedClubId = useAuthStore((state) => state.clubId)
  const meQuery = useMe()
  const login = useLogin()
  const logout = useLogout()
  const chooseClub = useClubSelection()

  if (token && me) {
    return (
      <Card className="mt-[26px] flex w-[400px] max-w-full flex-col gap-[16px] px-[28px] py-[28px]">
        <h2 className="text-h3">회의를 진행할 팀·조직 선택</h2>
        <p className="break-all text-[12px] text-mute">{me.email}</p>
        {me.clubs.length ? (
          <div className="flex flex-col gap-[9px]">
            {me.clubs.map((club) => (
              <Button
                key={club.id}
                variant={club.id === selectedClubId ? 'primary' : 'secondary'}
                className="justify-between whitespace-normal text-left"
                onClick={() => chooseClub(club.id)}
              >
                <span>{club.name}</span>
                <span className="shrink-0 text-[11px]">{ROLE_LABEL[club.role]} · 회의로 ›</span>
              </Button>
            ))}
          </div>
        ) : (
          <div className="rounded-[11px] bg-bg p-[15px] text-[13px] leading-relaxed text-ink2">
            가입된 팀·조직이 없어요. 대표에게 이 계정의 초대를 요청하고, 소속 등록 후 다시 확인해
            주세요.
          </div>
        )}
        {meQuery.error && <ErrorBanner title={authErrorMessage(meQuery.error)} />}
        <div className="flex gap-[8px]">
          <Button
            variant="secondary"
            disabled={meQuery.isFetching}
            onClick={() => void meQuery.refetch()}
          >
            {meQuery.isFetching ? '확인 중…' : '소속 다시 확인'}
          </Button>
          <Button variant="ghost" disabled={logout.isPending} onClick={() => logout.mutate()}>
            다른 계정으로 로그인
          </Button>
        </div>
      </Card>
    )
  }

  if (token) {
    return (
      <Card className="mt-[26px] flex w-[360px] max-w-full flex-col gap-[16px] px-[28px] py-[28px]">
        <p role="status" className="text-[13px]">
          {meQuery.isFetching ? '계정과 소속을 확인하고 있어요…' : '계정 정보를 불러오지 못했어요.'}
        </p>
        {meQuery.error && <ErrorBanner title={authErrorMessage(meQuery.error)} />}
        <Button disabled={meQuery.isFetching} onClick={() => void meQuery.refetch()}>
          다시 확인
        </Button>
        <Button variant="ghost" onClick={() => logout.mutate()}>
          다시 로그인
        </Button>
      </Card>
    )
  }

  return (
    <Card className="mt-[26px] w-[360px] max-w-full px-[32px] py-[28px]">
      <form
        className="flex flex-col gap-[16px]"
        onSubmit={(event) => {
          event.preventDefault()
          login.mutate({ email: email.trim(), password })
        }}
      >
        {login.error && <ErrorBanner title={authErrorMessage(login.error)} />}
        <Input
          label="이메일"
          type="email"
          autoComplete="email"
          placeholder="name@knu.ac.kr"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Input
          label="비밀번호"
          type="password"
          autoComplete="current-password"
          placeholder="••••••••"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <Button type="submit" size="lg" className="w-full" disabled={login.isPending}>
          {login.isPending ? '로그인 확인 중…' : '로그인'}
        </Button>
        <Link to="/signup" className="text-[11.5px] font-bold text-blue-700 hover:underline">
          처음이신가요? 회원가입 ›
        </Link>
        <div className="flex flex-col gap-[9px] border-t border-line pt-[18px]">
          <span className="text-[11px] text-mute">소셜 로그인은 준비 중이에요</span>
          <Button variant="secondary" size="lg" disabled>
            Google로 계속하기
          </Button>
          <Button variant="secondary" size="lg" disabled>
            카카오로 계속하기
          </Button>
        </div>
      </form>
    </Card>
  )
}
