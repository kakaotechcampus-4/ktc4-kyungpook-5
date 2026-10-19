import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Input } from '@/shared/ui/Input'
import { Modal } from '@/shared/ui/Modal'
import { Tori } from '@/shared/ui/Tori'
import { FlowRail } from './FlowRail'
import { PreviewControls } from './PreviewControls'
import { PreviewSections } from './PreviewSections'
import { Spotlight } from './Spotlight'
import type { useOnboarding } from './useOnboarding'

export function OnboardingExperience({
  onboarding,
}: {
  onboarding: ReturnType<typeof useOnboarding>
}) {
  const { view = '' } = useParams<{ view: string }>()
  const { state, update } = onboarding
  const navigate = useNavigate()
  const [confirmed, setConfirmed] = useState(false)
  const [editing, setEditing] = useState(false)
  const [sourceOpen, setSourceOpen] = useState(false)
  const [sourceRead, setSourceRead] = useState(false)
  const [savedNotice, setSavedNotice] = useState(false)
  const go = (next = '') => navigate(`/onboarding${next ? `/${next}` : ''}`)
  const closeGuide = useCallback(() => {
    update({ guideEnabled: false })
    document.querySelector<HTMLButtonElement>('[data-guide-toggle]')?.focus()
  }, [update])
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'auto' })
    document.getElementById('onboarding-main')?.focus({ preventScroll: true })
  }, [view])
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && state.guideEnabled && !document.querySelector('dialog[open]')) {
        event.preventDefault()
        closeGuide()
      }
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [state.guideEnabled, closeGuide])
  const patch = (key: keyof typeof state.candidate, value: string) => {
    update({ candidate: { ...state.candidate, [key]: value }, saved: false })
    setConfirmed(false)
  }
  const valid = !!(
    state.candidate.title.trim() &&
    state.candidate.assignee &&
    state.candidate.recipient &&
    state.candidate.dueAt &&
    state.candidate.reminderAt &&
    state.candidate.reminderAt <= state.candidate.dueAt
  )
  const step =
    view === 'meetings'
      ? 4
      : view === 'review' || state.saved || (view === '' && state.meetingPlayed)
        ? 5
        : view === '' && state.recordsAdded
          ? 4
          : 3
  let spot: { target: string; title: string; description: string } | null = null
  if (view === '' && !state.saved)
    spot = !state.recordsAdded
      ? {
          target: 'main-action',
          title: '먼저 회의에서 참고할 자료를 올려요',
          description:
            '자료 올리기를 누르면 자료함이 열려요. 올린 자료는 회의 중 답의 근거가 돼요.',
        }
      : state.meetingPlayed
        ? {
            target: 'main-action',
            title: '대화에서 찾은 할 일을 확인해요',
            description: '할 일 확인하기를 눌러 담당자와 시간을 확인해 주세요.',
          }
        : {
            target: 'main-action',
            title: '자료가 준비됐어요. 회의를 만들어 보세요',
            description: '첫 회의 만들기를 눌러 회의 공간을 만들어 주세요.',
          }
  if (view === 'records')
    spot = state.recordsAdded
      ? {
          target: 'records-next',
          title: '자료 준비가 끝났어요',
          description:
            '첫 회의 만들기를 눌러 주세요. 토리가 이 자료를 참고하는 모습을 볼 수 있어요.',
        }
      : {
          target: 'upload',
          title: '첫 자료를 올려 보세요',
          description: '예시 자료 올리기를 누르면 준비된 문서 2개가 자료함에 들어가요.',
        }
  if (view === 'meetings')
    spot = !state.meetingCreated
      ? {
          target: 'create-meeting',
          title: '회의 공간부터 만들어요',
          description: '회의 이름을 확인하고 회의 만들기를 눌러 주세요.',
        }
      : !state.meetingPlayed
        ? {
            target: 'start-meeting',
            title: '이제 회의를 시작해요',
            description:
              '예시 회의 시작을 누르면 전사와 자료 답이 나타나요. 마이크는 사용하지 않아요.',
          }
        : !sourceRead
          ? {
              target: 'answer-source',
              title: '토리의 답은 출처와 함께 확인해요',
              description: '운영팀 규칙의 출처 보기를 눌러 답의 근거를 확인해 주세요.',
            }
          : {
              target: 'review-candidate',
              title: '대화에서 할 일 후보를 찾았어요',
              description: '할 일 확인하기를 눌러 내용·담당·시각·알림 수신자를 확인하세요.',
            }
  if (view === 'review' && !editing)
    spot = confirmed
      ? {
          target: 'save-item',
          title: '확인한 내용을 저장해요',
          description:
            '확인하고 예시 저장을 눌러 주세요. 메인에서 저장한 할 일을 다시 볼 수 있어요.',
        }
      : {
          target: 'confirm-item',
          title: '담당자와 알림 받을 사람을 확인해요',
          description:
            '내용과 시각을 읽고 확인란을 선택해 주세요. 수정이 필요하면 내용 수정으로 바꿀 수 있어요.',
        }

  const main = (
    <>
      <header className="mb-6">
        <p className="mb-2 text-caption font-bold text-blue-600">
          {state.teamName} · {state.role === 'OWNER' ? '회장' : '임원'}
        </p>
        <h1 className="text-[27px] font-bold leading-10">
          {state.saved
            ? '회의에서 정한 일을 챙겨보세요'
            : `${state.operatorName}님, 첫 회의를 준비해 볼까요?`}
        </h1>
        <p className="mt-3 max-w-xl text-[14px] leading-7 text-ink2">
          자료를 올려두면 회의 중 필요한 답을 찾고, 대화에서 나온 할 일을 확인해 저장할 수 있어요.
        </p>
      </header>
      {savedNotice && (
        <p role="status" className="mb-5 rounded-xl bg-done-bg p-4 text-[13px] font-bold text-done">
          예시 할 일을 저장했어요. 아래에서 담당자와 시각을 다시 확인하세요.
        </p>
      )}
      <div className="grid grid-cols-3 gap-2 sm:gap-4">
        {[
          { label: '참고 자료', count: state.recordsAdded ? '2개' : '0개' },
          { label: '회의', count: state.meetingCreated ? '1개' : '0개' },
          { label: '저장한 할 일', count: state.saved ? '1개' : '0개' },
        ].map((item) => (
          <Card key={item.label} className="p-3 sm:p-5">
            <p className="text-caption text-mute">{item.label}</p>
            <p className="mt-2 text-[25px] font-bold">{item.count}</p>
          </Card>
        ))}
      </div>
      {state.saved ? (
        <Card className="mt-5 border-blue-200 p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-h2">저장한 할 일</h2>
            <Chip tone="done" size="sm">
              예시 저장
            </Chip>
          </div>
          <h3 className="text-[18px] font-bold">{state.candidate.title}</h3>
          <TaskFacts candidate={state.candidate} />
          <p className="mt-4 text-caption text-mute">
            이 브라우저에 저장한 예시예요. 실제 알림은 발송되지 않아요.
          </p>
          <Button className="mt-5" variant="secondary" onClick={() => go('review')}>
            내용 다시 확인
          </Button>
        </Card>
      ) : (
        <Card className="mt-5 p-6 sm:p-8">
          <div className="flex items-start gap-4">
            <Tori size={50} />
            <div>
              <h2 className="text-h2">
                {!state.recordsAdded
                  ? '아직 자료와 회의가 없어요'
                  : state.meetingPlayed
                    ? '회의에서 찾은 할 일을 확인해 주세요'
                    : '참고할 자료가 준비됐어요'}
              </h2>
              <p className="mt-2 text-[13px] leading-7 text-ink2">
                {!state.recordsAdded
                  ? '처음에는 회칙이나 행사 기록 한 개면 충분해요. 먼저 토리가 참고할 자료를 준비해 볼게요.'
                  : state.meetingPlayed
                    ? '할 일은 자동으로 확정되지 않아요. 담당과 시각을 직접 확인하면 메인에서 모아볼 수 있어요.'
                    : '이제 회의를 만들고 대화가 전사·자료 답·할 일 후보로 이어지는 흐름을 볼 수 있어요.'}
              </p>
              <Button
                data-guide-target="main-action"
                size="lg"
                className="mt-5"
                onClick={() =>
                  go(!state.recordsAdded ? 'records' : state.meetingPlayed ? 'review' : 'meetings')
                }
              >
                {!state.recordsAdded
                  ? '자료 올리기'
                  : state.meetingPlayed
                    ? '할 일 확인하기'
                    : '첫 회의 만들기'}
              </Button>
            </div>
          </div>
        </Card>
      )}
    </>
  )

  const records = (
    <Card className="p-6 sm:p-8">
      <Heading title="자료함" description="회의 중 토리가 참고할 문서를 모아두는 곳이에요." />
      <div className="mt-6 flex items-center justify-between">
        <h2 className="text-h3">팀 자료 · {state.recordsAdded ? 2 : 0}개</h2>
        <Chip size="sm">체험 자료</Chip>
      </div>
      {!state.recordsAdded ? (
        <div className="mt-5 rounded-2xl border-2 border-dashed border-soft bg-bg px-5 py-8 text-center">
          <p className="text-h3">아직 등록한 자료가 없어요</p>
          <p className="my-3 text-[13px] leading-6 text-mute">
            체험에서는 파일 선택 대신 준비된 예시를 사용해요.
          </p>
          <Button data-guide-target="upload" onClick={() => update({ recordsAdded: true })}>
            예시 자료 올리기
          </Button>
        </div>
      ) : (
        <>
          <div className="mt-5 space-y-3" role="status">
            {['운영팀 규칙.pdf', '가을 행사 예산표.csv'].map((name) => (
              <div key={name} className="rounded-xl border border-line p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="text-h3">{name}</h3>
                  <Chip size="sm" tone="done">
                    검색 준비됨 · 예시
                  </Chip>
                </div>
                <p className="mt-2 text-caption text-mute">회의 중 답변의 근거로 참고할 자료</p>
              </div>
            ))}
          </div>
          <div className="mt-6 rounded-xl bg-blue-50 p-5">
            <p className="mb-4 text-[13px] leading-6 text-ink2">
              자료 준비가 끝났어요. 이제 회의 중 질문이 나오면 토리가 이 문서에서 답을 찾아주는
              흐름을 볼게요.
            </p>
            <Button data-guide-target="records-next" onClick={() => go('meetings')}>
              첫 회의 만들기
            </Button>
          </div>
        </>
      )}
    </Card>
  )

  const meetings = (
    <Card className="p-6 sm:p-8">
      {!state.meetingCreated ? (
        <>
          <Heading
            title="첫 회의를 만들어요"
            description="회의 이름을 정하면 전사와 할 일을 모아볼 공간이 생겨요."
          />
          <form
            className="mt-6 max-w-lg space-y-5"
            onSubmit={(event) => {
              event.preventDefault()
              if (state.meetingTitle.trim()) update({ meetingCreated: true })
            }}
          >
            <Input
              label="회의 이름"
              value={state.meetingTitle}
              required
              maxLength={100}
              onChange={(event) => update({ meetingTitle: event.target.value })}
            />
            <div className="rounded-xl bg-bg p-4 text-[13px] leading-6 text-ink2">
              참고 자료: 운영팀 규칙.pdf 외 1개
              <br />
              소속: {state.teamName}
            </div>
            <Button
              data-guide-target="create-meeting"
              type="submit"
              disabled={!state.meetingTitle.trim()}
            >
              회의 만들기
            </Button>
          </form>
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <Heading
              title={state.meetingTitle}
              description={
                state.meetingPlayed
                  ? '예시 전사 2개 · 자료 답 1개 · 확인할 할 일 1개'
                  : '회의 공간이 준비됐어요. 시작하면 대화가 아래에 쌓여요.'
              }
            />
            <Chip size="sm">{state.meetingPlayed ? '예시 회의 진행됨' : '시작 전'}</Chip>
          </div>
          {!state.meetingPlayed ? (
            <div className="mt-6 rounded-2xl bg-bg p-7 text-center">
              <Tori size={60} className="mx-auto" />
              <h2 className="mt-4 text-h2">아직 전사가 없어요</h2>
              <p className="my-4 text-[13px] leading-7 text-mute">
                예시 회의 시작을 누르면 대화가 나타나요.
                <br />
                실제 녹음 대신 준비된 전사를 사용해요.
              </p>
              <Button
                data-guide-target="start-meeting"
                onClick={() => update({ meetingPlayed: true })}
              >
                예시 회의 시작
              </Button>
            </div>
          ) : (
            <div className="mt-6 space-y-5" aria-label="예시 확정 전사 타임라인">
              <Transcript time="00:12">
                행사장 예약은 언제까지 확인해야 하죠? 운영팀 규칙에 안내가 있었던 것 같아요.
              </Transcript>
              <div className="ml-4 border-l-2 border-blue-300 py-1 pl-4">
                <div className="mb-2 flex items-center gap-2">
                  <Tori size={26} />
                  <span className="text-[11px] text-mute">00:15 · 토리의 예시 답</span>
                </div>
                <p className="text-[13px] leading-7 text-ink2">
                  운영팀 규칙에는 행사 7일 전까지 장소 예약을 확인하도록 안내되어 있어요.
                </p>
                <Button
                  data-guide-target="answer-source"
                  className="mt-3"
                  variant="soft"
                  size="sm"
                  onClick={() => setSourceOpen(true)}
                >
                  운영팀 규칙.pdf · 3쪽 출처 보기
                </Button>
              </div>
              <Transcript time="00:24">
                하늘님이 금요일 오후 4시까지 예약을 확인해 주세요. 30분 전에 알림도 받으면 좋겠어요.
              </Transcript>
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-5">
                <p className="text-[11px] font-bold text-blue-600">
                  대화에서 찾은 후보 · 아직 저장되지 않았어요
                </p>
                <h2 className="mt-2 text-h3">{state.candidate.title}</h2>
                <p className="mt-2 text-[13px] leading-6 text-ink2">
                  담당·마감·알림 받을 사람을 직접 확인해야 저장돼요.
                </p>
                <Button
                  data-guide-target="review-candidate"
                  className="mt-4"
                  onClick={() => {
                    setConfirmed(false)
                    go('review')
                  }}
                >
                  할 일 확인하기
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  )

  const review = (
    <Card className="p-6 sm:p-8">
      <Heading
        title="이 할 일을 저장할까요?"
        description="대화에서 찾은 내용은 후보예요. 담당자·시각·알림 받을 사람을 직접 확인해 주세요."
      />
      {editing ? (
        <div className="mt-6 space-y-5">
          <Input
            label="할 일 내용"
            value={state.candidate.title}
            onChange={(event) => patch('title', event.target.value)}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <PersonSelect
              label="담당자"
              value={state.candidate.assignee}
              onChange={(value) => patch('assignee', value)}
            />
            <PersonSelect
              label="알림 수신자"
              value={state.candidate.recipient}
              onChange={(value) => patch('recipient', value)}
            />
            <Input
              label="마감 · 한국시간"
              type="datetime-local"
              value={state.candidate.dueAt}
              onChange={(event) => patch('dueAt', event.target.value)}
            />
            <Input
              label="알림 · 한국시간"
              type="datetime-local"
              value={state.candidate.reminderAt}
              onChange={(event) => patch('reminderAt', event.target.value)}
            />
          </div>
          {!valid && (
            <p role="alert" className="text-caption text-failed">
              내용과 시각을 입력하고, 알림을 마감 이전으로 확인해 주세요.
            </p>
          )}
          <Button disabled={!valid} onClick={() => setEditing(false)}>
            수정 완료
          </Button>
        </div>
      ) : (
        <>
          <div
            data-guide-target="confirm-item"
            className="mt-6 rounded-2xl border border-blue-100 bg-blue-50 p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-[17px] font-bold">{state.candidate.title}</h2>
              <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
                내용 수정
              </Button>
            </div>
            <TaskFacts candidate={state.candidate} />
            <label className="mt-5 flex items-start gap-2 border-t border-blue-200 pt-4 text-[13px] font-bold">
              <input
                className="mt-1 size-4 shrink-0 accent-blue-600"
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              <span>내용·담당자·시각·수신자를 확인했어요</span>
            </label>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button
              data-guide-target="save-item"
              disabled={!valid || !confirmed}
              onClick={() => {
                if (!confirmed || !valid) return
                update({ saved: true })
                setSavedNotice(true)
                go()
              }}
            >
              확인하고 예시 저장
            </Button>
            <p className="text-[11px] leading-5 text-mute">
              이 브라우저에만 저장해요.
              <br />
              실제 알림은 예약·발송하지 않아요.
            </p>
          </div>
        </>
      )}
    </Card>
  )

  return (
    <div className="mx-auto max-w-[960px] pb-8">
      <PreviewControls onboarding={onboarding} />
      <FlowRail current={step} complete={state.saved} />
      {view === '' ? (
        main
      ) : view === 'records' ? (
        records
      ) : view === 'meetings' ? (
        meetings
      ) : view === 'review' ? (
        review
      ) : view === 'mypage' ? (
        <Card className="p-6">
          <Heading
            title={state.operatorName}
            description={`${state.teamName} · ${state.role === 'OWNER' ? '회장' : '임원'} · 목업 계정`}
          />
          <Button className="mt-5" onClick={() => go()}>
            메인으로 돌아가기
          </Button>
        </Card>
      ) : (
        <>
          <p className="mb-5 text-caption text-mute">
            지금은 처음 이용하는 흐름을 살펴보고 있어요.
          </p>
          <PreviewSections view={view} />
          <Button className="mt-5" onClick={() => go()}>
            메인으로 돌아가기
          </Button>
        </>
      )}
      {state.guideEnabled && spot && !sourceOpen && (
        <Spotlight
          target={`[data-guide-target="${spot.target}"]`}
          title={spot.title}
          description={spot.description}
          step={step}
          total={5}
          onClose={closeGuide}
        />
      )}
      <Modal
        open={sourceOpen}
        onClose={() => {
          setSourceOpen(false)
          setSourceRead(true)
        }}
        title="출처 확인 · 예시"
        subtitle="운영팀 규칙.pdf · 3쪽"
        width={520}
      >
        <div className="rounded-xl border border-line bg-bg p-5">
          <h2 className="text-h3">제 4조 · 행사 장소 준비</h2>
          <p className="mt-3 text-[14px] leading-8">
            행사 장소는 행사일 7일 전까지 예약 여부를 확인한다. 운영 담당자는 장소의 수용 인원과
            사용 가능 시간을 함께 점검한다.
          </p>
        </div>
        <p className="text-caption text-mute">이 문장은 온보딩을 위한 예시 자료예요.</p>
        <Button
          onClick={() => {
            setSourceOpen(false)
            setSourceRead(true)
          }}
        >
          출처 확인했어요
        </Button>
      </Modal>
    </div>
  )
}

function Heading({ title, description }: { title: string; description: string }) {
  return (
    <header>
      <h1 className="text-[25px] font-bold leading-9">{title}</h1>
      <p className="mt-2 text-[13px] leading-7 text-ink2">{description}</p>
    </header>
  )
}
function Transcript({ time, children }: { time: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-[#F4EDE2] p-4">
      <p className="mb-2 text-[11px] text-mute">{time} · 예시 확정 전사</p>
      <p className="text-[14px] leading-7">{children}</p>
    </div>
  )
}
function TaskFacts({
  candidate,
}: {
  candidate: ReturnType<typeof useOnboarding>['state']['candidate']
}) {
  return (
    <dl className="mt-4 grid grid-cols-[80px_1fr] gap-x-3 gap-y-3 text-[13px] leading-6">
      <dt className="text-mute">담당자</dt>
      <dd className="font-bold">{candidate.assignee}</dd>
      <dt className="text-mute">마감</dt>
      <dd>{candidate.dueAt.replace('T', ' ')} (한국시간)</dd>
      <dt className="text-mute">알림 시각</dt>
      <dd>{candidate.reminderAt.replace('T', ' ')} (한국시간)</dd>
      <dt className="text-mute">알림 수신자</dt>
      <dd>{candidate.recipient} 1명</dd>
    </dl>
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
        {['김하늘', '박지훈'].map((person, index) => (
          <option key={person} value={person}>
            {person} · {index ? '회장' : '임원'}
          </option>
        ))}
      </select>
    </label>
  )
}
