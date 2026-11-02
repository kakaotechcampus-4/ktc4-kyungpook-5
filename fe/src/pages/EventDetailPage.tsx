// L2 행사 상세: 한 행사의 단계 진행과 확인 요청 · 처리된 승인을 본다.
import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { AnswerModal } from '@/features/events/components/AnswerModal'
import { CancelConfirmModal } from '@/features/events/components/CancelConfirmModal'
import { ConfirmationList } from '@/features/events/components/ConfirmationList'
import { CurrentStepCard } from '@/features/events/components/CurrentStepCard'
import { EventHeaderCard } from '@/features/events/components/EventHeaderCard'
import { ResolvedActionList } from '@/features/events/components/ResolvedActionList'
import { ReviewModal } from '@/features/events/components/ReviewModal'
import { StepModal } from '@/features/events/components/StepModal'
import {
  useConfirmations,
  useDemo,
  useEventDetail,
  useEventSteps,
  useResolvedActions,
  useStepActions,
  useApproveAction,
  useCompleteStep,
  useCompleteEvent,
  useBeginCancellation,
  useDenyAction,
  useMarkActionDone,
  useResolveAction,
  useStartEvent,
} from '@/features/events/hooks'
import type { EventAction, EventStep } from '@/features/events/types'
import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/Button'
import { EmptyState } from '@/shared/ui/EmptyState'
import { ServerErrorScreen } from '@/shared/ui/StateScreen'

export default function EventDetailPage() {
  const { eventId } = useParams()
  // ?demo 같은 주소 뒤쪽을 행사 목록으로 돌아갈 때도 이어 붙인다
  const { search } = useLocation()
  const navigate = useNavigate()
  const toList = `/events${search}`

  const demo = useDemo()
  const startMutation = useStartEvent()
  const completeMutation = useCompleteStep()
  const completeEventMutation = useCompleteEvent()
  const cancelMutation = useBeginCancellation()
  const resolveMutation = useResolveAction()
  const approveMutation = useApproveAction()
  const denyMutation = useDenyAction()
  const doneMutation = useMarkActionDone()
  const detailQuery = useEventDetail(eventId)
  const event = detailQuery.data
  // 행사가 없으면(초기 화면) 나머지는 부르지 않는다
  const shownId = event ? eventId : undefined
  const stepsQuery = useEventSteps(shownId)
  const steps = stepsQuery.data ?? []
  const currentIndex = steps.findIndex((s) => s.state === 'CURRENT')
  const resolvedQuery = useResolvedActions(shownId)
  const resolved = resolvedQuery.data

  // 열린 Step 모달의 단계. 단계를 다시 불러오면 순서가 바뀔 수 있어 id로 기억한다. null이면 닫혀 있다.
  const [openStepId, setOpenStepId] = useState<string | null>(null)
  const openIndex = steps.findIndex((s) => s.id === openStepId)
  const openStep = openIndex >= 0 ? steps[openIndex] : undefined
  // 실행을 마쳤다고 표시한 Action. 서버 연동 전이라 화면에서만 빼 둔다.
  const [finishedIds, setFinishedIds] = useState<string[]>([])
  const stepActionsQuery = useStepActions(shownId, openStep?.id)
  const stepActions = stepActionsQuery.data?.filter((a) => !finishedIds.includes(a.id))

  // 처리한 확인 요청. 서버 연동 전이라 화면에서만 빼 둔다.
  const [answeredIds, setAnsweredIds] = useState<string[]>([])
  const confirmationsQuery = useConfirmations(shownId)
  const confirmations = (confirmationsQuery.data ?? []).filter((a) => !answeredIds.includes(a.id))

  const run = async (operation: () => Promise<unknown>, title: string, desc?: string) => {
    try {
      if (!demo) await operation()
      toast.show({ kind: 'done', title, desc })
      return true
    } catch (error) {
      toast.show({ kind: 'error', title: '처리하지 못했어요', desc: error instanceof Error ? error.message : '잠시 후 다시 시도해 주세요.' })
      return false
    }
  }

  const resolveConfirmation = async (action: EventAction, choice: string, manualValue?: string) => {
    if (await run(() => resolveMutation.mutateAsync({ action, choice, manualValue }), '처리했어요', action.title)) {
      if (demo) setAnsweredIds((ids) => [...ids, action.id])
      setReviewing(undefined)
    }
  }

  const finishAction = async (action: EventAction) => {
    if (await run(() => doneMutation.mutateAsync(action), '완료로 표시했어요', action.title) && demo) {
      setFinishedIds((ids) => [...ids, action.id])
    }
  }

  const [cancelOpen, setCancelOpen] = useState(false)
  const [reviewing, setReviewing] = useState<EventAction>()
  const answering = reviewing?.type === 'CONFIRMATION' ? reviewing : undefined
  const deciding = reviewing && reviewing.type !== 'CONFIRMATION' ? reviewing : undefined

  const approveAction = async (action: EventAction) => {
    if (await run(() => approveMutation.mutateAsync(action), '승인했어요', action.title)) {
      setReviewing(undefined)
      setOpenStepId(null)
    }
  }

  const denyAction = async (action: EventAction, reason: string) => {
    if (await run(() => denyMutation.mutateAsync({ action, reason }), '진행하지 않기로 했어요', action.title)) {
      setReviewing(undefined)
      setOpenStepId(null)
    }
  }

  const completeStep = async (step: EventStep) => {
    if (await run(() => completeMutation.mutateAsync(step.id), '단계를 완료로 표시했어요', step.name)) setOpenStepId(null)
  }

  if (detailQuery.isPending) return null
  if (detailQuery.isError) {
    return <ServerErrorScreen onRetry={() => detailQuery.refetch()} onHome={() => navigate('/')} />
  }

  if (event && [stepsQuery, resolvedQuery, confirmationsQuery].some((query) => query.isPending))
    return null
  if (event && [stepsQuery, resolvedQuery, confirmationsQuery].some((query) => query.isError)) {
    return (
      <ServerErrorScreen
        onRetry={() => {
          stepsQuery.refetch()
          resolvedQuery.refetch()
          confirmationsQuery.refetch()
        }}
        onHome={() => navigate('/')}
      />
    )
  }

  return (
    <div className="flex flex-col gap-[20px]">
      <nav aria-label="이동 경로" className="flex items-center gap-[8px] text-[12px]">
        <Link
          to={toList}
          aria-label="행사 목록으로"
          className="rounded-[8px] border border-soft bg-card px-[9px] py-[5px] font-medium text-ink2 hover:bg-bg"
        >
          ‹
        </Link>
        <span className="text-mute">행사 목록</span>
        {event && (
          <>
            <span className="text-mute">/</span>
            <span className="font-bold">{event.title}</span>
          </>
        )}
      </nav>

      {event ? (
        <>
          <EventHeaderCard
            event={event}
            steps={steps}
            onSelectStep={(step) => setOpenStepId(step.id)}
            onCancelEvent={() => setCancelOpen(true)}
            onViewCancellation={() => navigate(`/events/${event.id}/cancel${search}`)}
            onEditPlan={() => navigate(demo ? '/planning/steps?demo' : `/planning/steps?eventId=${encodeURIComponent(event.id)}&from=event`)}
            onStartEvent={demo ? undefined : () => void run(() => startMutation.mutateAsync(event.id), '행사를 시작했어요')}
            onCompleteEvent={demo ? undefined : () => {
              if (window.confirm('행사를 완료하시겠어요? 완료 후에는 할 일을 처리할 수 없습니다.')) {
                void run(() => completeEventMutation.mutateAsync(event.id), '행사를 완료했어요')
              }
            }}
          />
          <div className="flex items-start gap-[20px]">
            <div className="flex min-w-0 flex-1 flex-col gap-[20px]">
              <ConfirmationList
                actions={confirmations}
                onResolve={(action, choice) => {
                  if (choice === 'MANUAL') setReviewing(action)
                  else void resolveConfirmation(action, choice)
                }}
                readOnly={!demo && event.status !== 'ON_GOING'}
              />
              <ResolvedActionList
                actions={resolved?.items ?? []}
                totalCount={resolved?.totalCount ?? 0}
              />
            </div>
            {/* 진행 중인 단계가 없으면(계획 중 · 끝난 행사) 오른쪽 칸 없이 왼쪽이 넓어진다 */}
            {currentIndex >= 0 && (
              <CurrentStepCard
                className="w-[400px] shrink-0"
                step={steps[currentIndex]}
                position={currentIndex + 1}
                onOpen={() => setOpenStepId(steps[currentIndex].id)}
              />
            )}
          </div>
          {openStep && (
            <StepModal
              step={openStep}
              position={openIndex + 1}
              actions={stepActions}
              actionsFailed={stepActionsQuery.isError}
              onRetryActions={() => stepActionsQuery.refetch()}
              onClose={() => setOpenStepId(null)}
              onCompleteAction={finishAction}
              onReviewAction={setReviewing}
              onCompleteStep={completeStep}
              readOnly={!demo && event.status !== 'ON_GOING'}
            />
          )}
          <ReviewModal
            action={deciding}
            onClose={() => setReviewing(undefined)}
            onApprove={approveAction}
            onDeny={denyAction}
          />
          <CancelConfirmModal
            open={cancelOpen}
            event={event}
            onClose={() => setCancelOpen(false)}
            pending={cancelMutation.isPending}
            onConfirm={() => {
              if (demo) navigate(`/events/${eventId}/cancel${search}`)
              else if (eventId) void run(() => cancelMutation.mutateAsync(eventId), '취소 정리를 시작했어요')
                .then((success) => { if (success) navigate(`/events/${eventId}/cancel${search}`) })
            }}
          />
          <AnswerModal
            action={answering}
            onClose={() => setReviewing(undefined)}
            onAnswer={(action, choice, manualValue) => void resolveConfirmation(action, choice, manualValue)}
          />
        </>
      ) : (
        <EmptyState
          title="아직 등록된 행사가 없어요"
          desc="행사를 만들면 여기서 단계 진행과 승인 기록을 볼 수 있어요."
          action={
            <div className="flex gap-[9px]">
              <Button size="lg" className="text-[13px]" onClick={() => navigate('/planning')}>
                행사 만들기
              </Button>
              <Button variant="secondary" size="lg" onClick={() => navigate(toList)}>
                행사 목록으로
              </Button>
            </div>
          }
        />
      )}
    </div>
  )
}
