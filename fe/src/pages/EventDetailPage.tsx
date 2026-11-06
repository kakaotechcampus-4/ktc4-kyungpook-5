// L2 행사 상세: 한 행사의 단계 진행과 확인 요청 · 처리된 승인을 본다.
import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { AnswerModal } from '@/features/events/components/AnswerModal'
import { CancelConfirmModal } from '@/features/events/components/CancelConfirmModal'
import { ConfirmationList } from '@/features/events/components/ConfirmationList'
import { CurrentStepCard } from '@/features/events/components/CurrentStepCard'
import { EventHeaderCard } from '@/features/events/components/EventHeaderCard'
import { OperationCases } from '@/features/events/components/OperationCases'
import { PlanningOverview } from '@/features/events/components/PlanningOverview'
import { useOperationCases } from '@/features/events/operationCasesHooks'
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
  useRequestActionDraft,
  useResolveAction,
  useUpdateActionContent,
} from '@/features/events/hooks'
import { outcomeOf, redraftNotice, type ActionOutcome } from '@/features/events/actionDraft'
import { eventError, isConflict } from '@/features/events/errors'
import type { EventAction, EventStep } from '@/features/events/types'
import { toast } from '@/shared/lib/toast'
import { ApiError } from '@/shared/api/types'
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
  // 계획 화면. 초안이 없으면 조건 화면, 있으면 P2로 간다(#325).
  const planPath = (id: string) =>
    demo ? '/planning/steps?demo' : `/planning?eventId=${encodeURIComponent(id)}`
  const completeMutation = useCompleteStep()
  const completeEventMutation = useCompleteEvent()
  const cancelMutation = useBeginCancellation()
  const resolveMutation = useResolveAction()
  const approveMutation = useApproveAction()
  const denyMutation = useDenyAction()
  const doneMutation = useMarkActionDone()
  const draftMutation = useRequestActionDraft()
  const contentMutation = useUpdateActionContent()
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
  const operationCases = useOperationCases(demo ? undefined : shownId)
  const caseActionIds = new Set((operationCases.data ?? []).flatMap((item) => item.action ? [item.action.id] : []))
  const confirmations = (confirmationsQuery.data ?? []).filter((a) => !answeredIds.includes(a.id) && !caseActionIds.has(a.id))

  const run = async (operation: () => Promise<unknown>, title: string, desc?: string) => {
    try {
      if (!demo) await operation()
      toast.show({ kind: 'done', title, desc })
      return true
    } catch (error) {
      showFailure(error)
      return false
    }
  }

  // 409는 다시 눌러도 같은 결과다. "다시 시도"를 권하지 않고 바뀐 내용을 보게 한다.
  // 훅이 onSettled로 목록을 다시 받은 뒤라 화면은 이미 최신이다(#375).
  const showFailure = (error: unknown) => {
    toast.show({
      kind: 'error',
      title: isConflict(error) ? '처리할 수 없어요' : '처리하지 못했어요',
      desc: eventError(error),
    })
  }

  const resolveConfirmation = async (action: EventAction, choice: string, manualValue?: string) => {
    const success = await run(() => resolveMutation.mutateAsync({ action, choice, manualValue }), '처리했어요', action.title)
    if (success) {
      if (demo) setAnsweredIds((ids) => [...ids, action.id])
      setReviewing(undefined)
    }
    return success
  }

  const finishAction = async (action: EventAction) => {
    if (await run(() => doneMutation.mutateAsync(action), '완료로 표시했어요', action.title) && demo) {
      setFinishedIds((ids) => [...ids, action.id])
    }
  }

  const [cancelOpen, setCancelOpen] = useState(false)
  const [reviewing, setReviewing] = useState<EventAction>()
  const answering = reviewing?.type === 'CONFIRMATION' ? reviewing : undefined
  // 검토 모달은 목록의 최신 Action을 본다. 그래야 쓰는 중이던 초안이 도착하면 모달에도 보이고,
  // 승인된 공지를 고쳐 승인 대기로 돌아가면 승인 버튼이 다시 나온다. 입력 중인 글은 모달이 지킨다.
  const deciding =
    reviewing && reviewing.type !== 'CONFIRMATION'
      ? (stepActions?.find((a) => a.id === reviewing.id) ?? reviewing)
      : undefined

  // 결정 검토 모달만 닫고 Step 모달은 남긴다. 한 단계에 검토할 일이 여럿이라
  // 같이 닫으면 한 건 처리할 때마다 단계를 다시 열어야 한다. 처리하면 쿼리가
  // 무효화돼 열린 Step 모달의 목록이 그 자리에서 갱신된다.
  // 승인하려는 사이 초안이 도착하면(409 VERSION_CONFLICT) 목록을 다시 불러오고 모달에서 확인하게 한다
  const approveAction = async (action: EventAction): Promise<ActionOutcome> => {
    try {
      if (!demo) await approveMutation.mutateAsync(action)
      toast.show({ kind: 'done', title: '승인했어요', desc: action.title })
      setReviewing(undefined)
      return 'ok'
    } catch (error) {
      const outcome = outcomeOf(error)
      if (outcome === 'failed') toast.show({ kind: 'error', title: '처리하지 못했어요', desc: eventError(error) })
      return outcome
    }
  }

  // 본문 저장(#335). 성공·충돌 모두 목록을 다시 불러온 뒤 돌아온다(useUpdateActionContent).
  const saveContent = async (action: EventAction, content: string, expectedVersion: number | undefined): Promise<ActionOutcome> => {
    try {
      await contentMutation.mutateAsync({ action, content, expectedVersion })
      toast.show({ kind: 'done', title: '고친 내용을 저장했어요', desc: action.title })
      return 'ok'
    } catch (error) {
      const outcome = outcomeOf(error)
      if (outcome === 'failed') toast.show({ kind: 'error', title: '저장하지 못했어요', desc: eventError(error) })
      return outcome
    }
  }

  // 토리 초안 다시 받기. 409면 다시 불러온 최신 상태를 보고 다시 누르게 한다.
  const requestDraft = async (action: EventAction) => {
    try {
      await draftMutation.mutateAsync(action)
      toast.show({ kind: 'done', title: '토리에게 초안을 다시 부탁했어요', desc: action.title })
    } catch (error) {
      const notice = redraftNotice(error)
      toast.show({ kind: 'error', title: notice?.title ?? '처리하지 못했어요', desc: notice?.desc ?? eventError(error) })
    }
  }

  const denyAction = async (action: EventAction, reason: string) => {
    const success = await run(() => denyMutation.mutateAsync({ action, reason }), '진행하지 않기로 했어요', action.title)
    if (success) setReviewing(undefined)
    return success
  }

  const completeStep = async (step: EventStep) => {
    try {
      const result = demo ? null : await completeMutation.mutateAsync(step.id)
      toast.show({
        kind: 'done',
        title: '단계를 완료로 표시했어요',
        desc: result?.pendingActionCount
          ? `미완료 행동 ${result.pendingActionCount}건이 남아 있어요. 행사 완료 전에 처리해 주세요.`
          : step.name,
      })
      setOpenStepId(null)
    } catch (error) {
      showFailure(error)
    }
  }

  const permissionError = [detailQuery, stepsQuery, resolvedQuery, confirmationsQuery, operationCases].some(
    (query) => query.isError && query.error instanceof ApiError && ['UNAUTHORIZED', 'FORBIDDEN'].includes(query.error.code),
  )
  if (permissionError) {
    return <ServerErrorScreen onRetry={() => { void detailQuery.refetch(); void stepsQuery.refetch(); void resolvedQuery.refetch(); void confirmationsQuery.refetch(); void operationCases.refetch() }} onHome={() => navigate('/')} />
  }

  if (detailQuery.isPending) return null
  if (detailQuery.isError && detailQuery.data === undefined) {
    return <ServerErrorScreen onRetry={() => detailQuery.refetch()} onHome={() => navigate('/')} />
  }

  if (event && [stepsQuery, resolvedQuery, confirmationsQuery].some((query) => query.isPending))
    return null
  if (event && [stepsQuery, resolvedQuery, confirmationsQuery].some((query) => query.isError && query.data === undefined)) {
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

      {event && (detailQuery.isError || [stepsQuery, resolvedQuery, confirmationsQuery].some((query) => query.isError)) && (
        <p role="alert" className="text-failed">최신 행사 정보를 불러오지 못해 이전 내용을 표시하고 있어요. <button type="button" className="underline" onClick={() => { void detailQuery.refetch(); void stepsQuery.refetch(); void resolvedQuery.refetch(); void confirmationsQuery.refetch() }}>다시 확인</button></p>
      )}

      {event ? (
        <>
          <EventHeaderCard
            event={event}
            steps={steps}
            onSelectStep={(step) => setOpenStepId(step.id)}
            onCancelEvent={() => setCancelOpen(true)}
            onViewCancellation={() => navigate(`/events/${event.id}/cancel${search}`)}
            onEditPlan={() => navigate(planPath(event.id))}
            onCompleteEvent={demo ? undefined : () => {
              if (window.confirm('행사를 완료하시겠어요? 완료 후에는 할 일을 처리할 수 없습니다.')) {
                void run(() => completeEventMutation.mutateAsync(event.id), '행사를 완료했어요')
              }
            }}
          />
          {/* 계획 중에는 운영용 칸(운영 상황 · 확인 요청 · 처리된 승인 · 현재 단계) 대신 계획 요약을 보여 준다(#337) */}
          {event.status === 'PLANNING' ? (
            <PlanningOverview
              event={event}
              steps={steps}
              onContinue={() => navigate(planPath(event.id))}
            />
          ) : (
            <>
            {!demo && shownId && <OperationCases key={shownId} eventId={shownId} active={event.status === 'ON_GOING'} cases={operationCases.data ?? []} loading={operationCases.isPending} error={operationCases.isError} onReload={() => void operationCases.refetch()} />}
            <div className="flex items-start gap-[20px]">
              <div className="flex min-w-0 flex-1 flex-col gap-[20px]">
                {(demo || operationCases.data !== undefined) && <ConfirmationList
                  actions={confirmations}
                  onResolve={(action, choice) => {
                    if (choice === 'MANUAL') setReviewing(action)
                    else void resolveConfirmation(action, choice)
                  }}
                  readOnly={!demo && event.status !== 'ON_GOING'}
                />}
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
            </>
          )}
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
              onRequestDraft={(action) => void requestDraft(action)}
              requestingDraftId={draftMutation.isPending ? draftMutation.variables?.id : undefined}
              onCompleteStep={completeStep}
              readOnly={!demo && event.status !== 'ON_GOING'}
            />
          )}
          <ReviewModal
            action={deciding}
            onClose={() => setReviewing(undefined)}
            onApprove={approveAction}
            onDeny={denyAction}
            onSaveContent={saveContent}
            pending={approveMutation.isPending || denyMutation.isPending}
            saving={contentMutation.isPending}
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
            onAnswer={resolveConfirmation}
            pending={resolveMutation.isPending}
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
