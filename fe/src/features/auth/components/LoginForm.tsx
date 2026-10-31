import { useState } from 'react'
import { beginKakaoLogin, kakaoConfigured } from '@/features/auth/kakao'
import { Link } from 'react-router-dom'
import {
  authErrorMessage,
  useClubSelection,
  useLogin,
  useLogout,
  useMe,
} from '@/features/auth/hooks'
import { ErrorBanner } from '@/shared/ui/AuthShell'
import { useAuthStore } from '@/shared/auth/store'
import { MEMBER_ROLE_LABEL } from '@/shared/lib/labels'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'

export function LoginForm() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [kakaoError, setKakaoError] = useState(false)
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
        <h2 className="text-h3">들어갈 팀·조직 선택</h2>
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
                <span className="shrink-0 text-[11px]">
                  {MEMBER_ROLE_LABEL[club.role]} · 들어가기 ›
                </span>
              </Button>
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-[11px]">
            <div className="rounded-[11px] bg-bg p-[15px] text-[13px] leading-relaxed text-ink2">
              이용할 수 있는 소속이 없어요. 동아리를 직접 만들거나, 회장·임원이 보낸 초대 코드로
              참여할 수 있어요.
            </div>
            <Link to="/clubs/new">
              <Button className="w-full">동아리 만들기</Button>
            </Link>
            <Link to="/clubs/join">
              <Button variant="secondary" className="w-full">
                초대 코드로 참여
              </Button>
            </Link>
            <Link
              to="/dashboard"
              className="text-center text-[12px] font-bold text-blue-700 underline"
            >
              동아리 없이 먼저 둘러보기
            </Link>
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
          <Button
            size="lg"
            className="w-full !bg-[#FEE500] !text-[#191919] hover:!bg-[#f5dc00]"
            disabled={!kakaoConfigured || login.isPending}
            onClick={() => {
              try {
                beginKakaoLogin()
              } catch {
                setKakaoError(true)
              }
            }}
          >
            카카오로 계속하기
          </Button>
          {!kakaoConfigured && (
            <span className="text-[11px] text-mute">카카오 로그인은 준비 중이에요.</span>
          )}
          {kakaoError && (
            <ErrorBanner title="카카오 로그인을 시작하지 못했어요. 브라우저 설정을 확인해 주세요." />
          )}
          <Button variant="secondary" size="lg" disabled>
            Google로 계속하기 (준비 중)
          </Button>
        </div>
      </form>
    </Card>
  )
}
