import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Input } from '@/shared/ui/Input'
import { Tori } from '@/shared/ui/Tori'
import { cn } from '@/shared/lib/cn'
import { CoachMark } from './CoachMark'
import type { useOnboarding } from './useOnboarding'
import type { OnboardingState } from './model'

const pathFor = (view = '') => `/onboarding${view ? `/${view}` : ''}`
const coreViews = ['', 'setup', 'records', 'meetings', 'review', 'complete']
const samplePeople = ['김하늘', '박지훈']

function Highlight({
  active,
  children,
  className,
}: {
  active: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'rounded-[20px] transition-shadow motion-reduce:transition-none',
        active && 'ring-2 ring-blue-600 ring-offset-4 ring-offset-bg',
        className,
      )}
    >
      {children}
    </div>
  )
}

function resumeView(state: OnboardingState) {
  if (!state.setupDone) return 'setup'
  if (!state.recordsAdded) return 'records'
  if (!state.meetingPlayed) return 'meetings'
  return state.saved ? 'complete' : 'review'
}

export function OnboardingExperience({
  onboarding,
}: {
  onboarding: ReturnType<typeof useOnboarding>
}) {
  const { view = '' } = useParams<{ view: string }>()
  const navigate = useNavigate()
  const { state, update, reset } = onboarding
  const [confirmed, setConfirmed] = useState(false)
  const [notice, setNotice] = useState('')
  const go = (next = '') => navigate(pathFor(next))
  const guided = state.guideEnabled && coreViews.includes(view)
  const completedCount = [
    state.setupDone,
    state.recordsAdded,
    state.meetingPlayed,
    state.saved,
  ].filter(Boolean).length

  const hideGuide = useCallback(() => {
    update({ guideEnabled: false })
    document.querySelector<HTMLButtonElement>('[data-guide-toggle]')?.focus()
  }, [update])

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'auto' })
    document.getElementById('onboarding-main')?.focus({ preventScroll: true })
  }, [view])

  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || !state.guideEnabled || document.querySelector('dialog[open]'))
        return
      event.preventDefault()
      hideGuide()
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [state.guideEnabled, hideGuide])

  const coach = (
    step: number,
    title: string,
    description: string,
    previous?: string,
    next?: string,
    nextDisabled = false,
  ) =>
    guided && (
      <CoachMark
        step={step}
        title={title}
        onClose={hideGuide}
        onPrevious={previous !== undefined ? () => go(previous) : undefined}
        onNext={next !== undefined ? () => go(next) : undefined}
        nextDisabled={nextDisabled}
        nextLabel={step === 1 ? '같이 시작하기' : '다음'}
      >
        {description}
      </CoachMark>
    )

  const patchCandidate = (key: keyof OnboardingState['candidate'], value: string) => {
    update({ candidate: { ...state.candidate, [key]: value }, saved: false })
    setConfirmed(false)
  }
  const valid =
    state.candidate.title.trim() &&
    state.candidate.assignee &&
    state.candidate.recipient &&
    state.candidate.dueAt &&
    state.candidate.reminderAt &&
    state.candidate.reminderAt <= state.candidate.dueAt

  const welcome = (
    <>
      {coach(
        1,
        '첫 운영, 어디서 시작할지 함께 볼까요?',
        '아래 시작 카드를 따라가면 자료를 모으고, 회의에서 나온 일을 확인하는 흐름을 체험할 수 있어요.',
        undefined,
        'setup',
      )}
      <Highlight active={guided}>
        <Card className="relative overflow-hidden border-blue-100 p-6 sm:p-9">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-10 -top-10 size-60 rounded-full bg-blue-50"
          />
          <div className="relative flex flex-col items-start justify-between gap-6 sm:flex-row">
            <div className="max-w-lg">
              <Chip tone="approved" size="sm">
                {state.role === 'OWNER' ? '회장' : '임원'}을 위한 첫 시작
              </Chip>
              <h1 className="mt-5 text-[28px] font-bold leading-[1.4] tracking-tight text-ink sm:text-[34px]">
                반가워요, {state.operatorName}님.
                <br />
                운영의 시작을 함께해요.
              </h1>
              <p className="mt-4 max-w-md text-[14px] leading-7 text-ink2">
                자료는 한곳에 모으고, 회의에서는 이야기에 집중하세요. 놓치기 쉬운 다음 할 일은
                토리와 함께 확인해요.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Button size="lg" onClick={() => go(resumeView(state))}>
                  {state.saved
                    ? '완료한 시작 가이드 보기'
                    : completedCount
                      ? '이어서 체험하기'
                      : '우리 팀 시작하기'}{' '}
                  <span aria-hidden>→</span>
                </Button>
                <Button size="lg" variant="ghost" onClick={() => go('meetings')}>
                  예시 회의 먼저 보기
                </Button>
              </div>
              <p className="mt-3 text-[11px] text-mute">
                약 2분 · 예시 데이터로 부담 없이 둘러보세요
              </p>
            </div>
            <div className="relative hidden self-end rounded-full sm:block border border-blue-100 bg-white/75 p-6 sm:mt-10 sm:self-auto sm:p-8">
              <Tori size={112} />
              <span className="absolute -bottom-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-blue-100 px-4 py-1.5 text-[12px] font-bold text-blue-700">
                안녕하세요, 토리예요!
              </span>
            </div>
          </div>
        </Card>
      </Highlight>
      <section className="mt-8">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-h2">처음이라면, 이 순서로 시작해요</h2>
          <span className="text-caption text-mute">{completedCount} / 4 완료</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {[
            {
              view: 'setup',
              title: '우리 팀 확인',
              desc: '팀 이름과 내 역할을 살펴봐요',
              done: state.setupDone,
            },
            {
              view: 'records',
              title: '자료 모으기',
              desc: '회의에서 함께 찾아볼 자료를 준비해요',
              done: state.recordsAdded,
            },
            {
              view: 'meetings',
              title: '회의 살펴보기',
              desc: '전사와 자료 답이 쌓이는 흐름을 봐요',
              done: state.meetingPlayed,
            },
            {
              view: 'review',
              title: '다음 할 일 확인',
              desc: '내용·담당·시각·수신자를 직접 확인해요',
              done: state.saved,
            },
          ].map((item, index) => (
            <button
              key={item.view}
              type="button"
              onClick={() => go(item.view)}
              className="flex items-start gap-4 rounded-2xl border border-line bg-card p-5 text-left transition-colors hover:border-blue-300 hover:bg-blue-50"
            >
              <span
                className={cn(
                  'flex size-8 shrink-0 items-center justify-center rounded-full text-[12px] font-bold',
                  item.done ? 'bg-blue-100 text-blue-700' : 'bg-bg text-mute',
                )}
              >
                {item.done ? '✓' : `0${index + 1}`}
              </span>
              <span>
                <span className="block text-h3">{item.title}</span>
                <span className="mt-1 block text-caption leading-5 text-mute">{item.desc}</span>
              </span>
              <span className="ml-auto text-mute" aria-hidden>
                ↗
              </span>
            </button>
          ))}
        </div>
      </section>
    </>
  )

  const setup = (
    <>
      {coach(
        2,
        '먼저 우리 팀을 확인해요',
        '서비스는 회장과 임원이 함께 사용해요. 이곳의 이름과 역할은 예시이며, 체험 중 자유롭게 바꿔도 괜찮아요.',
        '',
        'records',
        !state.setupDone,
      )}
      <Highlight active={guided}>
        <Card className="p-6 sm:p-8">
          <StepHeading
            number="01"
            title="우리 팀의 시작"
            description="운영을 함께할 공간을 확인해 주세요."
          />
          <form
            className="mt-7 grid gap-5 sm:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault()
              update({ setupDone: true })
              go('records')
            }}
          >
            <Input
              label="팀 이름"
              value={state.teamName}
              required
              maxLength={60}
              onChange={(event) => update({ teamName: event.target.value })}
            />
            <Input
              label="내 이름"
              value={state.operatorName}
              required
              maxLength={30}
              onChange={(event) => update({ operatorName: event.target.value })}
            />
            <label className="text-caption font-bold">
              내 역할
              <select
                className="mt-2 block w-full rounded-xl border border-soft bg-bg p-3 font-normal"
                value={state.role}
                onChange={(event) => update({ role: event.target.value as 'OWNER' | 'MANAGER' })}
              >
                <option value="OWNER">회장</option>
                <option value="MANAGER">임원</option>
              </select>
            </label>
            <div className="rounded-xl bg-bg p-4 text-caption leading-6 text-mute">
              일반 동아리원은 내부 명단으로 관리해요. 이 체험에서는 실제 계정이나 팀을 만들지
              않아요.
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={!state.teamName.trim() || !state.operatorName.trim()}>
                확인하고 자료 모으기 →
              </Button>
            </div>
          </form>
        </Card>
      </Highlight>
    </>
  )

  const records = (
    <>
      {coach(
        3,
        '토리가 참고할 자료를 모아요',
        '자료가 준비되면 회의 중 질문에 답과 출처를 함께 보여줄 수 있어요. 아래 버튼으로 예시 자료를 추가해 보세요.',
        'setup',
        'meetings',
        !state.recordsAdded,
      )}
      <Highlight active={guided}>
        <Card className="p-6 sm:p-8">
          <StepHeading
            number="02"
            title="회의 전에 자료를 준비해요"
            description="회칙, 행사 기록, 예산표처럼 함께 참고할 자료를 모아두세요."
          />
          <div className="mt-7 rounded-2xl border-2 border-dashed border-soft bg-bg px-5 py-8 text-center">
            <span aria-hidden className="text-[28px]">
              ↥
            </span>
            <h3 className="mt-2 text-h3">첫 자료 한 개부터 시작해요</h3>
            <p className="my-3 text-caption text-mute">
              실제 파일 대신 준비된 예시 PDF와 CSV를 사용해요.
            </p>
            <Button disabled={state.recordsAdded} onClick={() => update({ recordsAdded: true })}>
              {state.recordsAdded ? '예시 자료 추가됨' : '예시 자료 추가'}
            </Button>
          </div>
          {state.recordsAdded && (
            <div className="mt-5 space-y-3" role="status">
              {['운영팀 규칙.pdf', '가을 행사 예산표.csv'].map((name) => (
                <div
                  key={name}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line p-4"
                >
                  <div>
                    <p className="text-h3">{name}</p>
                    <p className="mt-1 text-caption text-mute">예시 문서 · 실제 업로드 없음</p>
                  </div>
                  <Chip tone="done" size="sm">
                    예시 · 검색 준비 완료
                  </Chip>
                </div>
              ))}
            </div>
          )}
          <div className="mt-6 flex justify-end">
            <Button
              variant="secondary"
              disabled={!state.recordsAdded}
              onClick={() => go('meetings')}
            >
              예시 회의로 이동 →
            </Button>
          </div>
        </Card>
      </Highlight>
    </>
  )

  const meetings = (
    <>
      {coach(
        4,
        '회의의 이야기가 다음 일로 이어져요',
        '전사가 본문에 쌓이고, 토리는 필요한 순간 자료의 답과 출처를 덧붙여요. 예시 전사를 열어 흐름을 살펴보세요.',
        'records',
        'review',
        !state.meetingPlayed,
      )}
      <Highlight active={guided}>
        <Card className="p-6 sm:p-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <StepHeading
              number="03"
              title="가을 행사 준비 회의"
              description="예시 회의 · 마이크와 음성 인식을 사용하지 않아요."
            />
            <Chip size="sm">목업 타임라인</Chip>
          </div>
          {!state.meetingPlayed ? (
            <div className="mt-7 rounded-2xl bg-bg p-8 text-center">
              <Tori size={64} className="mx-auto" />
              <p className="my-4 text-caption leading-6 text-mute">
                회의가 시작되면 확정된 전사가 이곳에 쌓여요.
                <br />
                준비된 짧은 예시를 먼저 확인해 보세요.
              </p>
              <Button onClick={() => update({ meetingPlayed: true })}>예시 전사 보기</Button>
            </div>
          ) : (
            <div className="mt-7 space-y-5" aria-label="예시 확정 전사 타임라인">
              <div className="rounded-xl bg-[#F4EDE2] p-4">
                <p className="mb-2 text-[11px] text-mute">00:12 · 예시 확정 전사</p>
                <p className="text-[14px] leading-7">
                  행사장 예약은 언제까지 확인해야 하죠? 운영팀 규칙에 안내가 있었던 것 같아요.
                </p>
              </div>
              <div className="ml-4 border-l-2 border-blue-300 py-1 pl-4">
                <div className="mb-2 flex items-center gap-2">
                  <Tori size={26} />
                  <span className="text-[11px] text-mute">00:15 · 토리의 예시 답</span>
                </div>
                <p className="text-[13px] leading-7 text-ink2">
                  운영팀 규칙에는 행사 7일 전까지 장소 예약을 확인하도록 안내되어 있어요.
                </p>
                <span className="mt-2 inline-block rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-[11px] text-blue-700">
                  출처 예시 · 운영팀 규칙.pdf · 3쪽
                </span>
              </div>
              <div className="rounded-xl bg-[#F4EDE2] p-4">
                <p className="mb-2 text-[11px] text-mute">00:24 · 예시 확정 전사</p>
                <p className="text-[14px] leading-7">
                  하늘님이 금요일 오후 4시까지 예약을 확인해 주세요. 30분 전에 알림도 받으면
                  좋겠어요.
                </p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
                <p className="text-h3 text-blue-900">확인할 할 일 후보 1개</p>
                <p className="mt-2 text-caption leading-6 text-ink2">
                  행사장 예약 확인 · 담당·마감·수신자는 다음 화면에서 직접 확인해요.
                </p>
                <Button className="mt-4" onClick={() => go('review')}>
                  후보 확인하기 →
                </Button>
              </div>
            </div>
          )}
        </Card>
      </Highlight>
    </>
  )

  const review = (
    <>
      {coach(
        5,
        '저장하기 전, 마지막으로 확인해요',
        '추출된 이름과 시간은 후보예요. 내용·담당·시각·알림 수신자를 확인하고 아래 확인란을 선택해 주세요.',
        'meetings',
      )}
      <Highlight active={guided}>
        <Card className="p-6 sm:p-8">
          <StepHeading
            number="04"
            title="다음 할 일을 확인해요"
            description="직접 수정해 본 뒤 예시로 저장해 보세요."
          />
          <form
            className="mt-7 space-y-5"
            onSubmit={(event) => {
              event.preventDefault()
              if (!valid || !confirmed) return
              update({ saved: true })
              go('complete')
            }}
          >
            <Input
              label="할 일 내용"
              value={state.candidate.title}
              required
              maxLength={100}
              onChange={(event) => patchCandidate('title', event.target.value)}
            />
            <div className="grid gap-5 sm:grid-cols-2">
              <PersonSelect
                label="담당자"
                value={state.candidate.assignee}
                onChange={(value) => patchCandidate('assignee', value)}
              />
              <Input
                label="마감 · 한국시간"
                type="datetime-local"
                value={state.candidate.dueAt}
                required
                onChange={(event) => patchCandidate('dueAt', event.target.value)}
              />
              <PersonSelect
                label="알림 수신자"
                value={state.candidate.recipient}
                onChange={(value) => patchCandidate('recipient', value)}
              />
              <Input
                label="알림 · 한국시간"
                type="datetime-local"
                value={state.candidate.reminderAt}
                required
                onChange={(event) => patchCandidate('reminderAt', event.target.value)}
              />
            </div>
            <div className="rounded-xl bg-bg p-4 text-caption leading-7">
              <p>
                <strong>{state.candidate.title || '내용 미입력'}</strong> · 담당{' '}
                {state.candidate.assignee}
              </p>
              <p>
                마감 {state.candidate.dueAt.replace('T', ' ')} / 알림{' '}
                {state.candidate.reminderAt.replace('T', ' ')}
              </p>
              <p>지정 수신자 {state.candidate.recipient} 1명</p>
              <label className="mt-3 flex items-start gap-2">
                <input
                  className="mt-1.5 size-4 shrink-0 accent-blue-600"
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                <span>내용·담당자·시각·수신자를 확인했어요</span>
              </label>
            </div>
            {!valid && (
              <p role="alert" className="text-caption text-failed">
                내용과 시각을 입력하고, 알림 시각을 마감 이전으로 확인해 주세요.
              </p>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={!valid || !confirmed}>
                예시로 저장하기
              </Button>
              <p className="text-[11px] leading-5 text-mute">
                이 브라우저에만 남아요.
                <br />
                실제 일정·예약·알림은 생성되지 않아요.
              </p>
            </div>
          </form>
        </Card>
      </Highlight>
    </>
  )

  const complete = (
    <Card className="p-7 text-center sm:p-12">
      <span
        className="mx-auto flex size-12 items-center justify-center rounded-full bg-blue-100 text-[24px] text-blue-700"
        aria-hidden
      >
        ✓
      </span>
      <Tori size={80} className="mx-auto mt-6" />
      <h1 className="mt-5 text-[27px] font-bold">첫 할 일을 확인했어요!</h1>
      <p className="mx-auto mt-3 max-w-md text-[14px] leading-7 text-ink2">
        자료를 준비하고, 회의에서 나온 일을 직접 확인하는 흐름을 살펴봤어요. 이제 팀의 운영을 시작할
        준비가 됐어요.
      </p>
      <div className="mx-auto mt-6 max-w-md rounded-2xl bg-bg p-5 text-left">
        <Chip tone="done" size="sm">
          예시 저장 완료
        </Chip>
        <h2 className="mt-3 text-h3">{state.candidate.title}</h2>
        <p className="mt-2 text-caption leading-6 text-mute">
          담당 {state.candidate.assignee} · 수신 {state.candidate.recipient}
          <br />
          마감 {state.candidate.dueAt.replace('T', ' ')}
          <br />
          실제 일정·알림 예약과 Push 발송은 없어요.
        </p>
      </div>
      <Button className="mt-7" size="lg" onClick={() => go()}>
        목업 메인 둘러보기 →
      </Button>
    </Card>
  )

  const extras: Record<string, ReactNode> = {
    events: (
      <Card className="p-6 sm:p-8">
        <StepHeading
          title="행사도 한곳에서 살펴봐요"
          description="지금은 준비된 행사 예시만 표시해요."
        />
        <div className="mt-6 rounded-2xl border border-line p-5">
          <Chip tone="pending" size="sm">
            준비 중 · 예시
          </Chip>
          <h2 className="mt-3 text-h2">가을 네트워킹 데이</h2>
          <p className="mt-2 text-caption leading-7 text-mute">
            10월 30일 · 캠퍼스 라운지 · 예상 참가 24명
          </p>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            {['장소 예약 확인', '참가 신청 안내', '운영 물품 준비'].map((title, i) => (
              <div key={title} className="rounded-xl bg-bg p-4 text-caption">
                <span className="text-mute">0{i + 1}</span>
                <p className="mt-2 font-bold">{title}</p>
              </div>
            ))}
          </div>
        </div>
      </Card>
    ),
    accounting: (
      <Card className="p-6 sm:p-8">
        <StepHeading
          title="운영비의 흐름을 살펴봐요"
          description="자료함에 올린 예산표와 실제 지출 내역은 따로 관리해요. 아래는 예시 지출이에요."
        />
        <div className="my-6 rounded-2xl bg-blue-50 p-5">
          <p className="text-caption text-blue-700">예시 지출 합계</p>
          <p className="mt-2 text-[28px] font-bold text-blue-900">80,000원</p>
        </div>
        {[
          { title: '행사 간식', amount: '48,000원', date: '10. 16.' },
          { title: '운영 물품', amount: '32,000원', date: '10. 15.' },
        ].map((item) => (
          <div
            key={item.title}
            className="flex justify-between gap-3 border-t border-line py-4 text-[13px]"
          >
            <div>
              <p className="font-bold">{item.title}</p>
              <p className="mt-1 text-caption text-mute">{item.date} · 예시 기록</p>
            </div>
            <span className="font-bold">{item.amount}</span>
          </div>
        ))}
      </Card>
    ),
    planning: (
      <Card className="p-6 sm:p-8">
        <StepHeading
          title="행사의 큰 틀부터 잡아요"
          description="무엇을 준비할지 함께 이야기하고, 필요한 일을 단계로 나누는 화면이에요."
        />
        <div className="mt-6 rounded-xl bg-[#F4EDE2] p-5 text-[14px] leading-7">
          새로 온 팀원들과 서로 알아갈 수 있는 행사를 준비하고 싶어요.
        </div>
        <div className="mt-5 border-l-2 border-blue-300 pl-5">
          <Tori size={32} />
          <p className="mt-3 text-[13px] leading-7 text-ink2">
            예시 계획: 가벼운 소개 → 팀별 미션 → 함께 돌아보기. 인원과 예산을 정하면 필요한 준비를
            차근차근 확인할 수 있어요.
          </p>
        </div>
      </Card>
    ),
  }

  return (
    <div className="mx-auto max-w-[1040px] pb-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <p className="text-caption text-mute">
          {state.teamName || '우리 팀'} <span className="mx-2 text-line">/</span> 처음 시작하기
        </p>
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-soft px-2 py-1.5">
          <span className="pl-1 text-[10px] font-bold text-mute">체험용 임시 버튼</span>
          <Button
            data-guide-toggle
            size="sm"
            variant="ghost"
            onClick={() => {
              update({ guideEnabled: !state.guideEnabled })
              if (!state.guideEnabled && !coreViews.includes(view)) go(resumeView(state))
            }}
          >
            {state.guideEnabled ? '온보딩 끄기' : '온보딩 켜기'}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              reset()
              setConfirmed(false)
              setNotice('온보딩을 처음 상태로 초기화했어요.')
              go()
            }}
          >
            온보딩 초기화
          </Button>
        </div>
      </div>
      {notice && (
        <p
          role="status"
          className="mb-5 rounded-xl bg-blue-50 px-4 py-3 text-caption text-blue-700"
        >
          {notice}
        </p>
      )}
      {!coreViews.includes(view) && (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50 px-4 py-3">
          <p className="text-caption text-ink2">
            잠깐 둘러보는 중이에요. 시작 안내는 이어서 볼 수 있어요.
          </p>
          <Button size="sm" variant="soft" onClick={() => go(resumeView(state))}>
            시작 가이드 이어보기
          </Button>
        </div>
      )}
      {view === ''
        ? welcome
        : view === 'setup' || view === 'mypage'
          ? setup
          : view === 'records'
            ? records
            : view === 'meetings'
              ? meetings
              : view === 'review'
                ? review
                : view === 'complete'
                  ? state.saved
                    ? complete
                    : review
                  : (extras[view] ?? welcome)}
    </div>
  )
}

function StepHeading({
  number,
  title,
  description,
}: {
  number?: string
  title: string
  description: string
}) {
  return (
    <header>
      {number && <p className="mb-2 text-[11px] font-bold text-blue-600">START {number}</p>}
      <h1 className="text-[23px] font-bold leading-9 tracking-tight text-ink">{title}</h1>
      <p className="mt-2 text-[13px] leading-6 text-mute">{description}</p>
    </header>
  )
}

function PersonSelect({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="text-caption font-bold">
      {label}
      <select
        className="mt-2 block w-full rounded-xl border border-soft bg-bg p-3 font-normal"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {samplePeople.map((person, index) => (
          <option key={person} value={person}>
            {person} · {index ? '회장' : '임원'}
          </option>
        ))}
      </select>
    </label>
  )
}
