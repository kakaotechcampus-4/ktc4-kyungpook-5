// S1 회원가입. 기존 동아리에 참여하거나 새로 만든다. 모드에 따라 아래 입력란이 통째로 바뀐다.
// 참여 요청을 보내면 허가를 기다리는 화면으로 바뀐다(대표가 허가해야 쓸 수 있다).
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { AuthShell, ErrorBanner, Field } from '@/features/auth/components/AuthShell'
import { ClubSearchField } from '@/features/auth/components/ClubSearchField'
import { ModeCards } from '@/features/auth/components/ModeCards'
import { NewClubFields } from '@/features/auth/components/NewClubFields'
import { DEMO_CLUBS } from '@/features/auth/mock'
import type { ClubField, ClubSearchResult, SignupMode } from '@/features/auth/types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { JoinPendingScreen } from '@/shared/ui/StateScreen'
import { ToriNote } from '@/shared/ui/ToriNote'

export default function SignupPage() {
  const navigate = useNavigate()
  // 다른 화면과 같은 방식. ?demo면 동아리 찾기에 예시 결과가 나온다.
  const demo = useSearchParams()[0].has('demo')

  const [mode, setMode] = useState<SignupMode>('JOIN')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')

  const [query, setQuery] = useState('')
  const [club, setClub] = useState<ClubSearchResult>()
  const [role, setRole] = useState('총무')

  const [clubName, setClubName] = useState('')
  const [clubField, setClubField] = useState<ClubField>('학술')
  const [intro, setIntro] = useState('')

  const [agreed, setAgreed] = useState(false)
  // 「이미 가입된 이메일이에요」처럼 갈 곳을 함께 줘야 하는 오류는 서버가 알려줘야 한다.
  // 그때 ErrorBanner의 action에 로그인하기 버튼을 넣는다(#41).
  const [error, setError] = useState<string>()
  // 참여 요청을 보낸 뒤. 허가 전까지 들어갈 수 있는 화면이 없어 이 자리에서 대기 화면을 보인다.
  const [requestedAt, setRequestedAt] = useState<string>()

  // TODO(연동): GET /clubs?query=. 지금은 ?demo일 때만 예시에서 거른다.
  const results =
    demo && query.trim() ? DEMO_CLUBS.filter((c) => c.name.includes(query.trim())) : []

  // TODO(연동): POST /auth/signup. 지금은 입력만 확인한다.
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password || !name.trim()) {
      setError('계정 정보를 모두 입력해 주세요')
      return
    }
    if (mode === 'JOIN' && !club) {
      setError('참여할 동아리를 골라 주세요')
      return
    }
    if (mode === 'CREATE' && !clubName.trim()) {
      setError('동아리 이름을 적어 주세요')
      return
    }
    if (!agreed) {
      setError('이용약관에 동의해 주세요')
      return
    }
    setError(undefined)

    // 새로 만들면 바로 대표가 되므로 그대로 들어간다. 참여는 허가를 기다린다.
    if (mode === 'CREATE') {
      navigate('/')
      return
    }
    setRequestedAt(new Date().toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' }))
  }

  if (requestedAt) {
    return (
      <AuthShell>
        <JoinPendingScreen
          club={club?.name}
          role={role}
          sentAt={requestedAt}
          owner={club?.ownerName}
          onCancelRequest={() => setRequestedAt(undefined)}
          onFindOther={() => {
            setRequestedAt(undefined)
            setClub(undefined)
            setQuery('')
          }}
        />
      </AuthShell>
    )
  }

  return (
    <AuthShell
      topRight={
        <div className="flex items-center gap-[10px]">
          <span className="text-[12px] text-mute">이미 계정이 있으신가요?</span>
          <Link
            to="/login"
            className="rounded-[9px] border border-soft px-[14px] py-[8px] text-[12px] font-medium text-ink2 hover:bg-bg"
          >
            로그인
          </Link>
        </div>
      }
    >
      <Card className="w-[480px] max-w-full px-[32px] py-[30px]">
        <form className="flex flex-col gap-[20px]" onSubmit={submit}>
          <div className="flex flex-col gap-[5px]">
            <h1 className="text-h1 text-ink">운영해 시작하기</h1>
            <p className="text-[12px] text-mute">
              두 가지만 적으면 바로 쓸 수 있어요. 나머지는 쓰면서 채워도 됩니다.
            </p>
          </div>

          {error && <ErrorBanner title={error} />}

          <section className="flex flex-col gap-[9px]">
            <h2 className="text-[11.5px] font-bold text-ink2">어떻게 시작하시나요</h2>
            <ModeCards value={mode} onChange={setMode} />
          </section>

          <section className="flex flex-col gap-[12px] border-t border-line pt-[18px]">
            <h2 className="text-h3 text-ink">계정</h2>
            <Field label="이메일" required>
              <Input
                type="email"
                autoComplete="email"
                placeholder="name@knu.ac.kr"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <Field label="비밀번호" required hint="8자 이상">
              <Input
                type="password"
                autoComplete="new-password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <Field label="이름" required>
              <Input
                autoComplete="name"
                placeholder="홍길동"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
          </section>

          <section className="flex flex-col gap-[12px] border-t border-line pt-[18px]">
            <h2 className="text-h3 text-ink">{mode === 'JOIN' ? '동아리' : '새 동아리'}</h2>
            {mode === 'JOIN' ? (
              <ClubSearchField
                query={query}
                onQueryChange={setQuery}
                results={results}
                selected={club}
                onSelect={setClub}
                role={role}
                onRoleChange={setRole}
                onCreateInstead={() => setMode('CREATE')}
              />
            ) : (
              <NewClubFields
                name={clubName}
                onNameChange={setClubName}
                field={clubField}
                onFieldChange={setClubField}
                intro={intro}
                onIntroChange={setIntro}
              />
            )}
          </section>

          <ToriNote
            title={mode === 'JOIN' ? '요청을 보내면 알림이 가요' : '만들면 바로 대표가 돼요'}
          >
            {mode === 'JOIN'
              ? `요청을 보내면 대표${club ? ` ${club.ownerName} 님` : ''}에게 알림이 가요. 허가 전까지는 동아리 자료와 행사에 접근할 수 없어요.`
              : '다음 화면에서 임원을 초대하고 동아리원 명단을 올릴 수 있어요. 명단이 있어야 참가·미납 집계를 해드릴 수 있어요.'}
          </ToriNote>

          <label className="flex items-center gap-[9px]">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="size-[16px] accent-blue-600"
            />
            <span className="text-[11.5px] text-ink2">
              이용약관과 개인정보 처리방침에 동의합니다
            </span>
          </label>

          <Button type="submit" size="lg" className="w-full">
            {mode === 'JOIN' ? '참여 요청 보내기' : '동아리 만들고 시작하기'}
          </Button>
        </form>
      </Card>
    </AuthShell>
  )
}
