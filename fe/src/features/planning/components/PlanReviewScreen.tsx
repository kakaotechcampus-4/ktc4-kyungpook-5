import { useEffect, useId, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import type { components } from '@/shared/api/schema'
import { useRequestPlanReview, useReviewInFlight, useStartEvent } from '../hooks'
import { currentExcluded, reviewGroups } from '../reviewModel'
import { reviewCardState, showGenerationWarnings } from '../reviewState'
import { PlanReviewCard } from './PlanReviewCard'
import { PlanStageNav } from './PlanStageNav'
import { StepComposer } from './StepComposer'
import { StepDetailModal } from './StepDetailModal'
import { Button } from '@/shared/ui/Button'
import { cn } from '@/shared/lib/cn'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { ToriNote } from '@/shared/ui/ToriNote'
import { formatDateRange, formatMonthDay } from '@/shared/lib/format'
import { ApiError } from '@/shared/api/types'

type S = components['schemas']
const actorLabel = (actor: string) =>
  ({ AI: 'AI 실행', APPROVAL_REQUIRED: '승인 필요', MANUAL: '직접 수행' })[actor] ?? actor
// 왼쪽 날짜 줄이 시작일(없으면 마감일)을 보이므로 칸 안에는 나머지 하나만 적는다.
const stepDue = (step: S['PlannedStepOut']) =>
  step.startsAt && step.deadline
    ? `${formatMonthDay(step.deadline)}까지`
    : step.startsAt
      ? '마감 미정'
      : step.deadline
        ? '시작 미정'
        : ''

export function PlanReviewScreen({
  eventId,
  screen,
  steps,
  onReload,
}: {
  eventId: string
  screen: S['PlanScreenOut']
  steps: S['PlannedStepOut'][]
  onReload: () => Promise<unknown>
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const heading = useRef<HTMLHeadingElement>(null)
  const [completion] = useState(() => {
    const generated = location.state?.generated as { count?: number; key?: string } | undefined
    return typeof generated?.count === 'number' && generated.count > 0
      ? `계획 초안 ${generated.count}단계를 만들었어요`
      : ''
  })
  useEffect(() => {
    if (!location.state?.focusPlan) return
    heading.current?.focus()
    // Consume route feedback so reload/back cannot announce the same completion again.
    navigate(location.pathname + location.search, { replace: true, state: null })
  }, [location.pathname, location.search, location.state, navigate])
  const queryClient = useQueryClient()
  // 편집 중 재조회가 원본 버전을 바꾸지 않도록 선택한 스냅샷을 유지한다.
  const [editing, setEditing] = useState<S['PlannedStepOut'] | null>(null)
  const [composing, setComposing] = useState(false)
  // 편집 모드가 「준비 순서」 칸을 통째로 바꾸므로 버튼도 새로 그려진다. 돌아올 때는 id로 다시 찾는다.
  const composeId = useId()
  const returnFocus = useRef<HTMLButtonElement | null>(null)
  const [savedId, setSavedId] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  // 안내에 「행사 상세 열기」를 같이 둘지. 상태가 바뀌었을 때만 그쪽이 더 아는 것이 많다.
  const [noticeNeedsEvent, setNoticeNeedsEvent] = useState(false)
  const start = useStartEvent(eventId)
  const requestReview = useRequestPlanReview(eventId)
  const requesting = useReviewInFlight(eventId)
  const review = screen.review ?? null
  const state = reviewCardState({ planRevision: screen.planRevision, review, requesting })
  const conditions = screen.draft.conditions
  const excluded = currentExcluded(steps)
  const knownCodes = new Set<string>(steps.map((step) => step.code))
  const warningsShown =
    showGenerationWarnings(screen.planRevision, review) && screen.warnings.length > 0
  const blockerId = useId()
  // 운영 시작을 막는 조건. 서버도 같은 두 가지(시작일·단계 하나 이상)로 막는다.
  const startBlocker = !conditions.startDate
    ? {
        title: '행사 시작일이 아직 없어요',
        action: '행사 조건에서 정하기',
        to: `/planning?${new URLSearchParams({ eventId, stage: 'conditions' })}`,
      }
    : !steps.length
      ? { title: '포함된 단계가 없어요', action: '', to: '' }
      : null
  // 화면에 그리는 순서(단계 묶음 순). 들어올 때 차례로 올라오는 지연에 쓴다.
  const order = new Map(
    reviewGroups(steps)
      .flatMap((group) => group.steps)
      .map((step, index) => [step.id, index]),
  )
  const closeDetail = () => {
    setEditing(null)
    requestAnimationFrame(() => returnFocus.current?.focus())
  }
  const begin = async () => {
    setNotice('')
    setNoticeNeedsEvent(false)
    try {
      await start.mutateAsync()
      await queryClient.invalidateQueries({ queryKey: ['events'] })
      navigate(`/events/${encodeURIComponent(eventId)}`)
    } catch (cause) {
      setNotice(
        cause instanceof ApiError && ['VALIDATION_FAILED', 'PLAN_INCOMPLETE'].includes(cause.code)
          ? '운영을 시작하려면 행사 시작일과 하나 이상의 단계가 필요해요. 행사 조건을 확인해 주세요.'
          : cause instanceof ApiError && cause.code === 'EVENT_NOT_PLANNING'
            ? '행사 상태가 바뀌었어요. 현재 상태를 확인해 주세요.'
            : '운영 시작 결과를 확인하지 못했어요. 현재 상태를 확인한 뒤 다시 시도해 주세요.',
      )
      // 이때만 행사 상세가 이 화면보다 아는 것이 많다(이미 계획 중이 아니다).
      setNoticeNeedsEvent(
        !(
          cause instanceof ApiError && ['VALIDATION_FAILED', 'PLAN_INCOMPLETE'].includes(cause.code)
        ),
      )
    }
  }
  return (
    <>
      <PlanStageNav current="review" eventId={eventId} canReview />
      {/* 초안 생성 화면에서 넘어왔을 때만 보인다. 새로고침·뒤로 가기로는 다시 뜨지 않는다. */}
      {completion && (
        <p
          role="status"
          className="flex animate-turn-in flex-wrap items-center gap-x-2 gap-y-1 rounded-xl bg-blue-50 px-4 py-3 break-keep text-ink motion-reduce:animate-none"
        >
          <svg
            aria-hidden
            viewBox="0 0 18 18"
            className="size-[18px] shrink-0 text-done"
            fill="none"
          >
            <circle cx="9" cy="9" r="9" className="fill-done-bg" />
            <path
              d="M5.2 9.3 7.9 12l4.9-5.6"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="font-semibold">{completion}.</span>
          <span className="text-ink2">단계를 눌러 내용과 일정을 고칠 수 있어요.</span>
        </p>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2
              ref={heading}
              tabIndex={-1}
              className="focus:outline-none text-[21px] font-bold [overflow-wrap:anywhere]"
            >
              {conditions.title || '행사 계획'}
            </h2>
            <Chip tone="approved">계획 중</Chip>
          </div>
          {/* 값 사이는 「|」로 나눈다. 띄어쓰기만으로는 「경북대 백호관 100명」처럼 붙어 읽힌다.
              시작일은 운영 시작을 막는 유일한 조건이라, 비어 있으면 오른쪽 운영 시작 칸의 안내와 같은 색으로 둔다. */}
          <p className="mt-2 flex flex-wrap items-center gap-x-[10px] gap-y-1 text-caption text-ink2">
            {[
              conditions.startDate ? (
                formatDateRange(conditions.startDate, conditions.endDate)
              ) : (
                <span className="font-medium text-pending">행사 일정 미정</span>
              ),
              conditions.location || '장소 미정',
              conditions.headcount === null
                ? '인원 미정'
                : `${conditions.headcount.toLocaleString('ko-KR')}명`,
              conditions.feePerPerson === null
                ? '참가비 미정'
                : conditions.feePerPerson === 0
                  ? '참가비 무료'
                  : `1인 ${conditions.feePerPerson.toLocaleString('ko-KR')}원`,
            ].map((item, index) => (
              <span key={index} className="flex items-center gap-x-[10px]">
                {index > 0 && (
                  <span aria-hidden className="text-soft">
                    |
                  </span>
                )}
                {item}
              </span>
            ))}
          </p>
        </div>
        {/* 「행사 조건 수정」·「이전 대화 보기」·「행사 상세」를 모두 걷어냈다.
            앞의 둘은 위의 단계 토글이 대신한다 — 조건과 대화는 행사 조건 쪽에 있다.
            행사 상세는 계획 중일 때 계획 요약만 보여 주어 이 화면보다 아는 것이 적다.
            상태가 바뀌어 정말 필요할 때만 아래 안내에서 띄운다. */}
      </div>
      {composing ? (
        // 단계 구성 변경은 다른 주소로 넘어가지 않고 이 자리를 편집 모드로 바꾼다.
        <StepComposer
          eventId={eventId}
          onDone={() => {
            setComposing(false)
            requestAnimationFrame(() => document.getElementById(composeId)?.focus())
          }}
        />
      ) : (
        <div className="grid min-w-0 grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_272px]">
          <Card className="min-w-0 p-4 sm:p-6">
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-h2">준비 순서</h2>
              <Button
                variant="secondary"
                size="sm"
                id={composeId}
                onClick={() => setComposing(true)}
              >
                단계 구성 변경
              </Button>
            </div>
            <div className="space-y-7">
              {reviewGroups(steps).map((group) => (
                <section key={group.name} aria-label={group.name}>
                  <h3 className="mb-3 flex items-center justify-between text-h3">
                    {group.name}
                    <span className="text-label font-normal text-mute">
                      {group.steps.length}개 단계
                    </span>
                  </h3>
                  <ol className="space-y-3">
                    {group.steps.map((step) => (
                      <li
                        key={step.id}
                        id={`plan-step-${step.id}`}
                        // 새 초안으로 막 들어왔으면 위에서부터 차례로 올라온다. 지연은 앞의 10개까지만 늘린다.
                        style={
                          completion
                            ? { animationDelay: `${Math.min(order.get(step.id) ?? 0, 10) * 45}ms` }
                            : undefined
                        }
                        className={cn(
                          'grid scroll-mt-6 grid-cols-[42px_minmax(0,1fr)] gap-2 sm:grid-cols-[52px_minmax(0,1fr)] sm:gap-3',
                          completion && 'animate-step-rise motion-reduce:animate-none',
                        )}
                      >
                        <div className="flex flex-col items-center gap-2 pt-3 text-label tabular-nums text-ink2">
                          <span>
                            {step.startsAt || step.deadline
                              ? formatMonthDay(step.startsAt || step.deadline!)
                              : '미정'}
                          </span>
                          <span aria-hidden className="size-2 rounded-full bg-blue-400" />
                          <span aria-hidden className="min-h-4 w-px flex-1 bg-line" />
                        </div>
                        {/* 칸 전체가 수정 창을 여는 자리다. 버튼의 ::after 가 칸을 덮어 어디를 눌러도 같은 버튼이 눌리고,
                          화면 낭독기에는 지금처럼 「○○ 일정·내용 수정」 버튼 하나로 읽힌다. */}
                        <div
                          className={cn(
                            'group/step relative min-w-0 rounded-xl border p-3 transition-[background-color,border-color,box-shadow] duration-150 ease-out motion-reduce:transition-none sm:p-4',
                            savedId === step.id
                              ? 'border-blue-200 bg-blue-50'
                              : 'border-transparent bg-bg',
                            step.editable &&
                              'hover:border-blue-300 hover:bg-card hover:shadow-[0_2px_10px_rgba(32,43,56,0.07)] has-[:focus-visible]:border-blue-400 has-[:focus-visible]:bg-card has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-blue-600',
                          )}
                        >
                          <div className="flex items-start justify-between gap-x-2">
                            <div className="min-w-0">
                              <h4 className="font-semibold [overflow-wrap:anywhere]">
                                {step.name}
                              </h4>
                              <div className="mt-1 flex flex-wrap items-center gap-2 text-label">
                                <Chip
                                  size="sm"
                                  tone={
                                    step.actor === 'APPROVAL_REQUIRED'
                                      ? 'pending'
                                      : step.actor === 'AI'
                                        ? 'approved'
                                        : 'neutral'
                                  }
                                >
                                  {actorLabel(step.actor)}
                                </Chip>
                                {/* 시작일은 왼쪽 줄에 있다. 여기에는 마감만 적어 같은 날짜를 두 번 읽지 않게 한다. */}
                                {stepDue(step) && (
                                  <span className="text-mute">{stepDue(step)}</span>
                                )}
                              </div>
                            </div>
                            <button
                              type="button"
                              disabled={!step.editable}
                              aria-label={`${step.name} 일정·내용 수정`}
                              onClick={(event) => {
                                returnFocus.current = event.currentTarget
                                setEditing(step)
                              }}
                              className="flex shrink-0 items-center gap-1 rounded-[8px] px-[10px] py-[6px] text-[13px] font-semibold text-blue-600 outline-none after:absolute after:inset-0 after:rounded-xl after:content-[''] enabled:cursor-pointer focus-visible:bg-blue-100 focus-visible:text-blue-700 disabled:text-mute disabled:opacity-60 group-hover/step:enabled:bg-blue-100 group-hover/step:enabled:text-blue-700"
                            >
                              <svg
                                aria-hidden
                                viewBox="0 0 16 16"
                                className="size-[14px]"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="1.5"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              >
                                <path d="M10.5 2.5l3 3L6 13H3v-3l7.5-7.5z" />
                              </svg>
                              수정
                            </button>
                          </div>
                          {step.actions.length > 0 && (
                            <ul className="mt-2 space-y-1 text-caption text-ink2 [overflow-wrap:anywhere]">
                              {step.actions.map((action) => (
                                <li key={action.id}>{action.title}</li>
                              ))}
                            </ul>
                          )}
                          {savedId === step.id && (
                            <p role="status" className="mt-2 text-label text-done">
                              변경 내용을 저장했어요.
                            </p>
                          )}
                        </div>
                      </li>
                    ))}
                  </ol>
                </section>
              ))}
            </div>
            <details className="mt-6 border-t border-line pt-2">
              <summary className="cursor-pointer rounded py-3 text-caption font-semibold text-ink2">
                포함하지 않은 단계 {excluded.length}개 보기
              </summary>
              <p className="mb-3 text-label text-mute">
                단계 구성 변경에서 다시 포함할 수 있어요. 이전 일정과 입력은 복원되지 않아요.
              </p>
              {excluded.map((step) => {
                const initial = screen.excludedSteps.find(
                  (item) => item.code === step.code && !knownCodes.has(item.code),
                )
                return (
                  <div key={step.code} className="border-t border-line py-3">
                    <p className="text-caption font-semibold">
                      {step.name}
                      <span className="ml-2 text-label font-normal text-mute">{step.phase}</span>
                    </p>
                    {initial?.reason && (
                      <p className="mt-1 text-label text-mute [overflow-wrap:anywhere]">
                        AI가 처음 제외한 이유: {initial.reason}
                      </p>
                    )}
                  </div>
                )
              })}
            </details>
          </Card>
          <aside className="grid min-w-0 gap-4 xl:sticky xl:top-5">
            {/* 이 화면의 끝은 운영 시작이다. 맨 위에 두고, 막는 이유와 고치러 가는 길을 버튼 바로 위에 붙인다.
              예전에는 버튼 밑 작은 글자였고, 그 글자가 가리키던 「행사 조건 수정」 버튼은 단계 토글로 바뀌어 없었다. */}
            <Card className="flex flex-col gap-4 p-5">
              {/* 예전 「계획 요약」 상자를 한 줄로 줄였다. 좁은 열에서는 항목 단위로만 줄을 바꾼다. */}
              <div className="flex flex-col gap-1 tabular-nums">
                <p className="text-caption font-semibold text-ink">
                  준비 {screen.summary.totalSteps}단계
                </p>
                <p className="flex flex-wrap gap-x-3 gap-y-0.5 text-label font-normal text-ink2">
                  {(
                    [
                      ['AI 실행', screen.summary.aiSteps],
                      ['승인 필요', screen.summary.approvalSteps],
                      ['직접 수행', screen.summary.manualSteps],
                    ] as const
                  ).map(([label, count]) => (
                    <span key={label} className="whitespace-nowrap">
                      {label} <span className="font-semibold text-ink">{count}</span>
                    </span>
                  ))}
                </p>
              </div>
              {startBlocker && (
                <div
                  id={blockerId}
                  className="flex items-start gap-[10px] rounded-[10px] border border-pending-line bg-pending-bg px-[14px] py-[12px] text-pending"
                >
                  <svg
                    aria-hidden
                    viewBox="0 0 16 16"
                    className="mt-[2px] size-[15px] shrink-0"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  >
                    <circle cx="8" cy="8" r="6.25" />
                    <path d="M8 4.75v3.75M8 11.1v.15" />
                  </svg>
                  <span className="flex min-w-0 flex-col gap-[3px]">
                    <span className="text-caption font-bold">{startBlocker.title}</span>
                    {startBlocker.to && (
                      <Link
                        to={startBlocker.to}
                        className="text-caption font-semibold text-blue-700 underline-offset-4 hover:underline"
                      >
                        {startBlocker.action} →
                      </Link>
                    )}
                  </span>
                </div>
              )}
              <div className="flex flex-col gap-2">
                <Button
                  className="w-full"
                  loading={start.isPending}
                  disabled={!!startBlocker}
                  aria-describedby={startBlocker ? blockerId : undefined}
                  onClick={() => void begin()}
                >
                  운영 시작
                </Button>
                <p className="text-label leading-relaxed text-mute">
                  행사를 진행 중으로 전환해요. 실행·발송은 별도 승인이 필요해요.
                </p>
              </div>
              {notice && (
                <p role="alert" className="text-caption text-failed">
                  {notice}{' '}
                  {noticeNeedsEvent && (
                    <Link
                      className="font-semibold text-blue-700 underline underline-offset-4"
                      to={`/events/${encodeURIComponent(eventId)}`}
                    >
                      행사 상세 열기
                    </Link>
                  )}
                </p>
              )}
            </Card>
            {/* 「준비 순서를 확인해 주세요」 기본 안내는 뺐다. 고친 뒤에는 검토 카드가 스스로 뜬다. */}
            {(warningsShown || state !== 'hidden') && (
              <section
                aria-label="확인할 점"
                className="min-w-0 space-y-3 [overflow-wrap:anywhere]"
              >
                <h2 className="text-h3">확인할 점</h2>
                {warningsShown && (
                  <ToriNote title="초안을 만들며 확인한 점" tone="cream">
                    <ul className="space-y-2">
                      {screen.warnings.map((warning, index) => (
                        <li key={index}>{warning}</li>
                      ))}
                    </ul>
                  </ToriNote>
                )}
                <PlanReviewCard
                  state={state}
                  review={review}
                  requesting={requesting}
                  onRequest={() => requestReview.mutate(screen.planRevision)}
                />
              </section>
            )}
          </aside>
        </div>
      )}
      <StepDetailModal
        step={editing}
        onClose={closeDetail}
        onSaved={() => {
          setSavedId(editing?.id ?? null)
          closeDetail()
          void onReload()
        }}
        onReload={() => {
          closeDetail()
          void onReload()
        }}
      />
    </>
  )
}
