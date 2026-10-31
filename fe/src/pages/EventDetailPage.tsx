// L2 행사 상세: 한 행사의 단계 진행과 확인 요청 · 처리된 승인을 본다.
import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { AnswerModal } from '@/features/events/components/AnswerModal'
import { CancelConfirmModal } from '@/features/events/components/CancelConfirmModal'
import { CompleteConfirmModal } from '@/features/events/components/CompleteConfirmModal'
import { ConfirmationList } from '@/features/events/components/ConfirmationList'
import { PendingApprovalList } from '@/features/events/components/PendingApprovalList'
import { CurrentStepCard } from '@/features/events/components/CurrentStepCard'
import { EventHeaderCard } from '@/features/events/components/EventHeaderCard'
import { ResolvedActionList } from '@/features/events/components/ResolvedActionList'
import { ReviewModal } from '@/features/events/components/ReviewModal'
import { StepModal } from '@/features/events/components/StepModal'
import {
  actionErrorMessage,
  useApproveAction,
  useCompleteEvent,
  useCompleteStep,
  useConfirmations,
  usePendingApprovals,
  useDenyAction,
  useEventDetail,
  useEventSteps,
  useMarkActionDone,
  useResolveAction,
  useResolvedActions,
  useStepActions,
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

  const detailQuery = useEventDetail(eventId)
  const event = detailQuery.data
  // 행사가 없으면(초기 화면) 나머지는 부르지 않는다
  const shownId = event ? eventId : undefined
  const steps = useEventSteps(shownId).data ?? []
  const currentIndex = steps.findIndex((s) => s.state === 'CURRENT')
  const resolved = useResolvedActions(shownId).data

  // 열린 Step 모달의 단계. 단계를 다시 불러오면 순서가 바뀔 수 있어 id로 기억한다. null이면 닫혀 있다.
  const [openStepId, setOpenStepId] = useState<string | null>(null)
  const openIndex = steps.findIndex((s) => s.id === openStepId)
  const openStep = openIndex >= 0 ? steps[openIndex] : undefined
  // 실행을 마쳤다고 표시한 Action. 서버 연동 전이라 화면에서만 빼 둔다.
  const [finishedIds, setFinishedIds] = useState<string[]>([])
  const stepActionsQuery = useStepActions(shownId, openStep?.id)
  const stepActions = stepActionsQuery.data?.filter((a) => !finishedIds.includes(a.id))

  // 처리한 확인 요청. 서버 연동 전이라 화면에서만 빼 둔다.
  const pendingApprovals = usePendingApprovals(shownId).data ?? []
  const [answeredIds, setAnsweredIds] = useState<string[]>([])
  const confirmations = (useConfirmations(shownId).data ?? []).filter(
    (a) => !answeredIds.includes(a.id),
  )

  const resolve = useResolveAction(shownId)
  const resolveConfirmation = (action: EventAction, choice: string, manualValue?: string) => {
    setAnsweredIds((ids) => [...ids, action.id])
    void resolve.mutateAsync({ action, choice, manualValue }).then(
      () =>
        toast.show({
          kind: 'done',
          title: choice === 'MANUAL' ? '직접 처리로 넘겼어요' : '처리했어요',
          desc: action.title,
        }),
      (cause) => {
        // 서버가 받지 않았으니 숨겼던 카드를 되돌린다.
        setAnsweredIds((ids) => ids.filter((id) => id !== action.id))
        toast.show({ kind: 'error', title: '처리하지 못했어요', desc: actionErrorMessage(cause) })
      },
    )
  }

  const markDone = useMarkActionDone(shownId)
  const finishAction = (action: EventAction) => {
    setFinishedIds((ids) => [...ids, action.id])
    void markDone.mutateAsync(action).then(
      () => toast.show({ kind: 'done', title: '완료로 표시했어요', desc: action.title }),
      (cause) => {
        setFinishedIds((ids) => ids.filter((id) => id !== action.id))
        toast.show({ kind: 'error', title: '완료로 표시하지 못했어요', desc: actionErrorMessage(cause) })
      },
    )
  }

  // 행사 취소 확인 모달. 확인하면 취소 정리 화면으로 간다.
  const [cancelOpen, setCancelOpen] = useState(false)

  // 행사 완료. 앱이 끝났다고 판단하지 않고 운영진이 직접 표시한다.
  const [completeOpen, setCompleteOpen] = useState(false)
  const complete = useCompleteEvent(shownId)
  const completeEvent = () =>
    void complete.mutateAsync(undefined).then(
      () => {
        setCompleteOpen(false)
        toast.show({ kind: 'done', title: '행사를 완료로 표시했어요' })
      },
      (cause) =>
        toast.show({ kind: 'error', title: '완료하지 못했어요', desc: actionErrorMessage(cause) }),
    )

  // 검토·답변 모달에 띄울 Action. 유형에 따라 둘 중 하나가 열린다.
  const [reviewing, setReviewing] = useState<EventAction>()
  const answering = reviewing?.type === 'CONFIRMATION' ? reviewing : undefined
  const deciding = reviewing && reviewing.type !== 'CONFIRMATION' ? reviewing : undefined

  const approve = useApproveAction(shownId)
  const approveAction = (action: EventAction) => {
    setReviewing(undefined)
    setOpenStepId(null)
    void approve.mutateAsync(action).then(
      () => toast.show({ kind: 'done', title: '승인했어요', desc: action.title }),
      (cause) =>
        toast.show({ kind: 'error', title: '승인하지 못했어요', desc: actionErrorMessage(cause) }),
    )
  }

  const deny = useDenyAction(shownId)
  const denyAction = (action: EventAction, reason: string) => {
    setReviewing(undefined)
    setOpenStepId(null)
    void deny.mutateAsync({ action, reason }).then(
      () =>
        toast.show({
          kind: 'done',
          title: '진행하지 않기로 했어요',
          desc: `${action.title} · ${reason}`,
        }),
      (cause) =>
        toast.show({ kind: 'error', title: '거절하지 못했어요', desc: actionErrorMessage(cause) }),
    )
  }

  const finishStep = useCompleteStep(shownId)
  const completeStep = (step: EventStep) => {
    setOpenStepId(null)
    void finishStep.mutateAsync(step).then(
      (result) =>
        toast.show({
          kind: 'done',
          title: '단계를 완료로 표시했어요',
          // 남은 행동이 있어도 완료는 된다. 그냥 넘기면 뭘 안 했는지 모른 채 지나간다.
          desc: result.pendingActionCount
            ? `${step.name} · 아직 처리하지 않은 일 ${result.pendingActionCount}건이 있어요`
            : step.name,
        }),
      (cause) =>
        toast.show({ kind: 'error', title: '완료로 표시하지 못했어요', desc: actionErrorMessage(cause) }),
    )
  }

  // 처리(승인·거절·답변·완료)는 서버가 운영 중인 행사에서만 받는다. 끝난 행사는
  // 기록을 보러 들어오는 자리라, 누르면 실패할 버튼을 아예 그리지 않는다.
  const operating = detailQuery.data?.status === 'ON_GOING'

  if (detailQuery.isPending) return null
  if (detailQuery.isError) {
    return <ServerErrorScreen onRetry={() => detailQuery.refetch()} onHome={() => navigate('/')} />
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
            onCancelEvent={operating ? () => setCancelOpen(true) : undefined}
            onCompleteEvent={operating ? () => setCompleteOpen(true) : undefined}
          />
          <div className="flex items-start gap-[20px]">
            <div className="flex min-w-0 flex-1 flex-col gap-[20px]">
              <PendingApprovalList
                actions={pendingApprovals}
                onReview={operating ? setReviewing : undefined}
              />
              <ConfirmationList
                actions={confirmations}
                onResolve={operating ? resolveConfirmation : undefined}
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
              onCompleteAction={operating ? finishAction : undefined}
              onReviewAction={operating ? setReviewing : undefined}
              onCompleteStep={operating ? completeStep : undefined}
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
            // TODO(연동): POST /events/{id}/cancel. 취소 Action은 아직 정의 전이다(#73).
            onConfirm={() => navigate(`/events/${eventId}/cancel${search}`)}
          />
          <CompleteConfirmModal
            open={completeOpen}
            event={event}
            remainingSteps={steps.filter((step) => step.state !== 'DONE').length}
            pendingApprovals={pendingApprovals.length}
            pending={complete.isPending}
            onClose={() => setCompleteOpen(false)}
            onConfirm={completeEvent}
          />
          <AnswerModal
            action={answering}
            onClose={() => setReviewing(undefined)}
            onAnswer={(action, choice, manualValue) => {
              setReviewing(undefined)
              resolveConfirmation(action, choice, manualValue)
            }}
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
