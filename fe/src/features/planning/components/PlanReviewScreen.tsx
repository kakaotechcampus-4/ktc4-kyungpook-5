import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import type { components } from '@/shared/api/schema'
import { useRequestPlanReview, useReviewInFlight, useStartEvent } from '../hooks'
import { currentExcluded, reviewGroups } from '../reviewModel'
import { reviewCardState, showGenerationWarnings } from '../reviewState'
import { PlanReviewCard } from './PlanReviewCard'
import { PlanStageNav } from './PlanStageNav'
import { StepDetailModal } from './StepDetailModal'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Modal } from '@/shared/ui/Modal'
import { ToriNote } from '@/shared/ui/ToriNote'
import { formatDateRange, formatMonthDay } from '@/shared/lib/format'
import { ApiError } from '@/shared/api/types'

type S = components['schemas']
const actorLabel = (actor: string) =>
  ({ AI: 'AI 실행', APPROVAL_REQUIRED: '승인 필요', MANUAL: '직접 수행' })[actor] ?? actor

export function PlanReviewScreen({
  eventId,
  screen,
  steps,
  messages,
  onReload,
}: {
  eventId: string
  screen: S['PlanScreenOut']
  steps: S['PlannedStepOut'][]
  messages: S['PlanMessageOut'][]
  onReload: () => Promise<unknown>
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [conversationOpen, setConversationOpen] = useState(false)
  // 편집 중 재조회가 원본 버전을 바꾸지 않도록 선택한 스냅샷을 유지한다.
  const [editing, setEditing] = useState<S['PlannedStepOut'] | null>(null)
  const returnFocus = useRef<HTMLButtonElement | null>(null)
  const [savedId, setSavedId] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const start = useStartEvent(eventId)
  const requestReview = useRequestPlanReview(eventId)
  const requesting = useReviewInFlight(eventId)
  const review = screen.review ?? null
  const state = reviewCardState({ planRevision: screen.planRevision, review, requesting })
  const conditions = screen.draft.conditions
  const excluded = currentExcluded(steps)
  const knownCodes = new Set<string>(steps.map((step) => step.code))
  const closeDetail = () => {
    setEditing(null)
    requestAnimationFrame(() => returnFocus.current?.focus())
  }
  const begin = async () => {
    setNotice('')
    try {
      await start.mutateAsync()
      await queryClient.invalidateQueries({ queryKey: ['events'] })
      navigate(`/events/${encodeURIComponent(eventId)}`)
    } catch (cause) {
      setNotice(
        cause instanceof ApiError && ['VALIDATION_FAILED', 'PLAN_INCOMPLETE'].includes(cause.code)
          ? '운영을 시작하려면 행사 시작일과 하나 이상의 단계가 필요해요. 행사 조건을 확인해 주세요.'
          : cause instanceof ApiError && cause.code === 'EVENT_NOT_PLANNING'
            ? '행사 상태가 바뀌었어요. 행사 상세에서 현재 상태를 확인해 주세요.'
            : '운영 시작 결과를 확인하지 못했어요. 행사 상세에서 현재 상태를 확인한 뒤 다시 시도해 주세요.',
      )
    }
  }
  return (
    <>
      <PlanStageNav current="review" />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[21px] font-bold [overflow-wrap:anywhere]">
              {conditions.title || '행사 계획'}
            </h2>
            <Chip tone="approved">계획 중</Chip>
          </div>
          <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-caption text-ink2">
            <span>
              {conditions.startDate
                ? formatDateRange(conditions.startDate, conditions.endDate)
                : '행사 일정 미정'}
            </span>
            <span>{conditions.location || '장소 미정'}</span>
            <span>
              {conditions.headcount === null
                ? '인원 미정'
                : `${conditions.headcount.toLocaleString('ko-KR')}명`}
            </span>
            <span>
              {conditions.feePerPerson === null
                ? '참가비 미정'
                : conditions.feePerPerson === 0
                  ? '참가비 무료'
                  : `1인 ${conditions.feePerPerson.toLocaleString('ko-KR')}원`}
            </span>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            onClick={() =>
              navigate(`/planning?${new URLSearchParams({ eventId, stage: 'conditions' })}`)
            }
          >
            행사 조건 수정
          </Button>
          <Button variant="secondary" onClick={() => setConversationOpen(true)}>
            이전 대화 보기
          </Button>
          <Link
            className="self-center rounded-lg px-2 py-2 text-caption text-ink2 underline underline-offset-4"
            to={`/events/${encodeURIComponent(eventId)}`}
          >
            행사 상세
          </Link>
        </div>
      </div>
      <div className="grid min-w-0 grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_272px]">
        <Card className="min-w-0 p-4 sm:p-6">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-h2">준비 순서</h2>
              <p className="mt-1 text-label text-mute">
                포함 단계 {steps.length}개 · 포함하지 않은 단계 {excluded.length}개
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                navigate(`/planning/steps?${new URLSearchParams({ eventId, from: 'review' })}`)
              }
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
                      className="grid scroll-mt-6 grid-cols-[42px_minmax(0,1fr)] gap-2 sm:grid-cols-[52px_minmax(0,1fr)] sm:gap-3"
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
                      <div
                        className={`min-w-0 rounded-xl p-3 sm:p-4 ${savedId === step.id ? 'bg-blue-50' : 'bg-bg'}`}
                      >
                        <div className="flex flex-wrap items-start justify-between gap-x-2 gap-y-1">
                          <div className="min-w-0">
                            <h4 className="font-semibold [overflow-wrap:anywhere]">{step.name}</h4>
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
                              <span className="text-mute">
                                {step.startsAt || step.deadline
                                  ? `${step.startsAt ? formatMonthDay(step.startsAt) : '시작 미정'} – ${step.deadline ? formatMonthDay(step.deadline) : '마감 미정'}`
                                  : '일정 미정'}
                              </span>
                            </div>
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={!step.editable}
                            aria-label={`${step.name} 일정·내용 수정`}
                            onClick={(event) => {
                              returnFocus.current = event.currentTarget
                              setEditing(step)
                            }}
                          >
                            일정·내용 수정
                          </Button>
                        </div>
                        {step.actions.length ? (
                          <ul className="mt-2 space-y-1 text-caption text-ink2 [overflow-wrap:anywhere]">
                            {step.actions.map((action) => (
                              <li key={action.id}>{action.title}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-2 text-caption text-mute">등록된 작업이 없어요.</p>
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
          <section aria-label="확인할 점" className="min-w-0 space-y-3 [overflow-wrap:anywhere]">
            <h2 className="text-h3">확인할 점</h2>
            {showGenerationWarnings(screen.planRevision, review) && screen.warnings.length > 0 && (
              <ToriNote title="초안을 만들며 확인한 점" tone="cream">
                <ul className="space-y-2">
                  {screen.warnings.map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              </ToriNote>
            )}
            {state === 'hidden' && (
              <ToriNote title="준비 순서를 확인해 주세요">
                일정과 내용을 고친 뒤 AI 검토를 받을 수 있어요.
              </ToriNote>
            )}
            <PlanReviewCard
              state={state}
              review={review}
              requesting={requesting}
              onRequest={() => requestReview.mutate(screen.planRevision)}
            />
          </section>
          <Card className="p-5">
            <h2 className="text-h3">계획 요약</h2>
            <dl className="mt-4 space-y-3 text-caption tabular-nums">
              {(
                [
                  ['전체 단계', screen.summary.totalSteps],
                  ['AI 실행', screen.summary.aiSteps],
                  ['승인 필요', screen.summary.approvalSteps],
                  ['직접 수행', screen.summary.manualSteps],
                ] as const
              ).map(([label, count]) => (
                <div key={label} className="flex justify-between gap-3">
                  <dt className="text-ink2">{label}</dt>
                  <dd className="font-semibold">{count}개</dd>
                </div>
              ))}
            </dl>
          </Card>
          <Card className="space-y-3 p-5">
            <Button
              className="w-full"
              loading={start.isPending}
              disabled={!conditions.startDate || !steps.length}
              onClick={() => void begin()}
            >
              운영 시작
            </Button>
            <p className="text-label leading-relaxed text-mute">
              행사를 진행 중으로 전환해요. 실행·발송은 별도 승인이 필요해요.
            </p>
            {!conditions.startDate && (
              <p className="text-label text-pending">행사 조건 수정에서 시작일을 정해 주세요.</p>
            )}
            {notice && (
              <p role="alert" className="text-caption text-failed">
                {notice}
              </p>
            )}
          </Card>
        </aside>
      </div>
      <Modal
        open={conversationOpen}
        onClose={() => setConversationOpen(false)}
        title="이전 대화"
        subtitle="읽기 전용이에요. 새 대화는 행사 조건 수정에서 이어갈 수 있어요."
        footer={
          <Button variant="secondary" onClick={() => setConversationOpen(false)}>
            닫기
          </Button>
        }
      >
        <ol className="planning-conversation flex flex-col gap-4">
          {messages.map((message) => (
            <li
              key={message.id}
              className={`max-w-[92%] rounded-xl px-4 py-3 ${message.role === 'USER' ? 'self-end bg-blue-50 text-blue-900' : 'self-start bg-bg'}`}
            >
              <p className="mb-1 text-label font-semibold">
                {message.role === 'USER' ? '나' : '토리'}
              </p>
              <p className="whitespace-pre-wrap text-body [overflow-wrap:anywhere]">
                {message.content}
              </p>
            </li>
          ))}
        </ol>
        {!messages.length && <p className="text-mute">저장된 이전 대화가 없어요.</p>}
      </Modal>
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
