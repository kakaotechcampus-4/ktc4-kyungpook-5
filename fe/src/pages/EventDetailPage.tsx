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
  useEventDetail,
  useEventSteps,
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
  const [answeredIds, setAnsweredIds] = useState<string[]>([])
  const confirmations = (useConfirmations(shownId).data ?? []).filter(
    (a) => !answeredIds.includes(a.id),
  )

  // TODO(연동): POST /actions/{id}/resolve 에 { choice } 로 보낸다
  const resolveConfirmation = (action: EventAction, choice: string) => {
    setAnsweredIds((ids) => [...ids, action.id])
    toast.show({
      kind: 'done',
      title: choice === 'MANUAL' ? '직접 처리로 넘겼어요' : '처리했어요',
      desc: action.title,
    })
  }

  // TODO(연동): 실행을 마쳤다는 기록 API가 명세에 없다
  const finishAction = (action: EventAction) => {
    setFinishedIds((ids) => [...ids, action.id])
    toast.show({ kind: 'done', title: '완료로 표시했어요', desc: action.title })
  }

  // 행사 취소 확인 모달. 확인하면 취소 정리 화면으로 간다.
  const [cancelOpen, setCancelOpen] = useState(false)

  // 검토·답변 모달에 띄울 Action. 유형에 따라 둘 중 하나가 열린다.
  const [reviewing, setReviewing] = useState<EventAction>()
  const answering = reviewing?.type === 'CONFIRMATION' ? reviewing : undefined
  const deciding = reviewing && reviewing.type !== 'CONFIRMATION' ? reviewing : undefined

  // TODO(연동): POST /actions/{id}/approve
  const approveAction = (action: EventAction) => {
    setReviewing(undefined)
    setOpenStepId(null)
    toast.show({ kind: 'done', title: '승인했어요', desc: action.title })
  }

  // TODO(연동): POST /actions/{id}/deny 에 { reason } 으로 보낸다
  const denyAction = (action: EventAction, reason: string) => {
    setReviewing(undefined)
    setOpenStepId(null)
    toast.show({
      kind: 'done',
      title: '진행하지 않기로 했어요',
      desc: `${action.title} · ${reason}`,
    })
  }

  // TODO(연동): POST /steps/{stepId}/complete. 미처리 Action이 남아 있으면 먼저 확인을 받는다(명세).
  const completeStep = (step: EventStep) => {
    setOpenStepId(null)
    toast.show({ kind: 'done', title: '단계를 완료로 표시했어요', desc: step.name })
  }

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
            onEditPlan={() => navigate(`/planning/steps${search}`)}
            onCancelEvent={() => setCancelOpen(true)}
          />
          <div className="flex items-start gap-[20px]">
            <div className="flex min-w-0 flex-1 flex-col gap-[20px]">
              <ConfirmationList actions={confirmations} onResolve={resolveConfirmation} />
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
          <AnswerModal
            action={answering}
            onClose={() => setReviewing(undefined)}
            onAnswer={(action, answer) => {
              setReviewing(undefined)
              resolveConfirmation(action, answer)
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
