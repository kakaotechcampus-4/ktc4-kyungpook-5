// L2 행사 상세: 한 행사의 단계 진행, 지금 할 일, 처리 기록을 본다.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { AnswerModal } from '@/features/events/components/AnswerModal'
import { CancelConfirmModal } from '@/features/events/components/CancelConfirmModal'
import { CurrentStepCard } from '@/features/events/components/CurrentStepCard'
import { EventHeaderCard } from '@/features/events/components/EventHeaderCard'
import { OperationCases } from '@/features/events/components/OperationCases'
import { PlanningOverview } from '@/features/events/components/PlanningOverview'
import { useOperationCases } from '@/features/events/operationCasesHooks'
import { ResolvedActionList } from '@/features/events/components/ResolvedActionList'
import { ReviewModal } from '@/features/events/components/ReviewModal'
import { StepDoneMoment, type StepDone } from '@/features/events/components/StepDoneMoment'
import { StepModal } from '@/features/events/components/StepModal'
import { TodoList } from '@/features/events/components/TodoList'
import { currentMark, draftSentences, stepAdvance, todoList, type CurrentMark } from '@/features/events/todo'
import {
  useDemo,
  useEventDetail,
  useEventSteps,
  useResolvedActions,
  useStepActions,
  useTodoActions,
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
  // 「전체 보기」를 누르면 처리 기록을 전부 받아 그 자리에서 펼친다
  const [allResolved, setAllResolved] = useState(false)
  const resolvedQuery = useResolvedActions(shownId, allResolved)
  const resolved = resolvedQuery.data

  // 열린 Step 모달의 단계. 단계를 다시 불러오면 순서가 바뀔 수 있어 id로 기억한다. null이면 닫혀 있다.
  const [openStepId, setOpenStepId] = useState<string | null>(null)
  const openIndex = steps.findIndex((s) => s.id === openStepId)
  const openStep = openIndex >= 0 ? steps[openIndex] : undefined
  // 실행을 마쳤다고 표시한 Action. 서버 연동 전이라 화면에서만 빼 둔다.
  const [finishedIds, setFinishedIds] = useState<string[]>([])
  const stepActionsQuery = useStepActions(shownId, openStep?.id)
  const stepActions = stepActionsQuery.data?.filter((a) => !finishedIds.includes(a.id))

  // 지금 할 일. 시연에서는 처리해도 서버가 없어 화면에서만 뺀다(답한 질문 · 완료 표시한 일).
  const [answeredIds, setAnsweredIds] = useState<string[]>([])
  const todoQuery = useTodoActions(shownId)
  const operationCases = useOperationCases(demo ? undefined : shownId)
  // 운영 상황에서 나온 질문은 그 카드 안에서 답하므로 여기서는 뺀다
  const caseActionIds = new Set((operationCases.data ?? []).flatMap((item) => item.action ? [item.action.id] : []))
  const todoActions = (todoQuery.data ?? []).filter(
    (a) => !answeredIds.includes(a.id) && !finishedIds.includes(a.id) && !caseActionIds.has(a.id),
  )
  const todos = todoList(todoActions, steps)
  const currentStepId = currentIndex >= 0 ? steps[currentIndex].id : undefined
  const currentDraftNotes = draftSentences(todoActions.filter((a) => a.stepId === currentStepId))

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
  // 방금 끝낸 단계. 화면 가운데에 잠깐 띄운 뒤 비운다.
  const [stepDone, setStepDone] = useState<StepDone | null>(null)
  const clearStepDone = useCallback(() => setStepDone(null), [])
  const [reviewing, setReviewing] = useState<EventAction>()
  const answering = reviewing?.type === 'CONFIRMATION' ? reviewing : undefined
  // 검토 모달은 목록의 최신 Action을 본다. 그래야 쓰는 중이던 초안이 도착하면 모달에도 보이고,
  // 승인된 공지를 고쳐 승인 대기로 돌아가면 승인 버튼이 다시 나온다. 입력 중인 글은 모달이 지킨다.
  const deciding =
    reviewing && reviewing.type !== 'CONFIRMATION'
      ? (stepActions?.find((a) => a.id === reviewing.id) ??
        todoActions.find((a) => a.id === reviewing.id) ??
        reviewing)
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

  // 완료 요청이 끝날 때까지 버튼에 도는 표시를 둔다
  const [completingId, setCompletingId] = useState<string | null>(null)
  const completeStep = async (step: EventStep) => {
    setCompletingId(step.id)
    try {
      const result = demo ? null : await completeMutation.mutateAsync(step.id)
      setOpenStepId(null)
      // 완료 카드는 아래 효과가 다시 불러온 단계 목록을 보고 띄운다. 시연은 단계가 바뀌지 않아 여기서 띄운다.
      if (demo) {
        const index = steps.findIndex((s) => s.id === step.id)
        const next = steps.slice(index + 1).find((s) => s.state !== 'DONE')
        setStepDone({
          key: Date.now(),
          done: { position: index + 1, name: step.name },
          next: next && { position: steps.indexOf(next) + 1, name: next.name },
          drafting: false,
        })
      }
      if (result?.pendingActionCount)
        toast.show({
          kind: 'done',
          title: '단계를 완료로 표시했어요',
          desc: `미완료 행동 ${result.pendingActionCount}건이 남아 있어요. 행사 완료 전에 처리해 주세요.`,
        })
    } catch (error) {
      showFailure(error)
    } finally {
      setCompletingId(null)
    }
  }

  // 단계가 넘어간 순간에 완료 카드를 띄운다. 「단계 완료로 표시」뿐 아니라 마지막 일을 끝내 서버가
  // 단계를 자동으로 완료한 경우도 같다. 처음 열었을 때와 다른 행사로 옮겼을 때는 띄우지 않는다.
  const markRef = useRef<CurrentMark | null>(null)
  const refetchTodo = todoQuery.refetch
  useEffect(() => {
    const loaded = stepsQuery.data
    if (!loaded || !eventId) return
    const advance = stepAdvance(markRef.current, eventId, loaded)
    markRef.current = currentMark(eventId, loaded)
    if (!advance) return
    // 끝난 단계의 모달이 열려 있으면 닫는다. 모달은 화면 맨 위 층이라 완료 카드를 가린다.
    setOpenStepId((id) => (id === advance.done.id ? null : id))
    const { done, next } = advance
    // 다음 단계가 시작되면 서버가 응답 전에 공지·발송 초안을 「쓰는 중」으로 바꿔 둔다.
    // 다시 불러온 목록에 다음 단계의 쓰는 중인 글이 있을 때만 토리가 시작했다고 알린다.
    void refetchTodo().then((fresh) =>
      setStepDone({
        key: Date.now(),
        done: { position: done.position, name: done.name },
        next: next && { position: next.position, name: next.name },
        drafting: !!next && (fresh.data ?? []).some((a) => a.stepId === next.id && a.contentStatus === 'DRAFTING'),
      }),
    )
  }, [stepsQuery.data, eventId, refetchTodo])

  const permissionError = [detailQuery, stepsQuery, resolvedQuery, todoQuery, operationCases].some(
    (query) => query.isError && query.error instanceof ApiError && ['UNAUTHORIZED', 'FORBIDDEN'].includes(query.error.code),
  )
  if (permissionError) {
    return <ServerErrorScreen onRetry={() => { void detailQuery.refetch(); void stepsQuery.refetch(); void resolvedQuery.refetch(); void todoQuery.refetch(); void operationCases.refetch() }} onHome={() => navigate('/')} />
  }

  if (detailQuery.isPending) return null
  if (detailQuery.isError && detailQuery.data === undefined) {
    return <ServerErrorScreen onRetry={() => detailQuery.refetch()} onHome={() => navigate('/')} />
  }

  if (event && [stepsQuery, resolvedQuery, todoQuery].some((query) => query.isPending))
    return null
  // 지금 할 일을 못 불러온 경우는 그 카드 안에서 따로 알린다
  if (event && [stepsQuery, resolvedQuery].some((query) => query.isError && query.data === undefined)) {
    return (
      <ServerErrorScreen
        onRetry={() => {
          stepsQuery.refetch()
          resolvedQuery.refetch()
          todoQuery.refetch()
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

      {event && (detailQuery.isError || [stepsQuery, resolvedQuery].some((query) => query.isError) || (todoQuery.isError && todoQuery.data !== undefined)) && (
        <p role="alert" className="text-failed">최신 행사 정보를 불러오지 못해 이전 내용을 표시하고 있어요. <button type="button" className="underline" onClick={() => { void detailQuery.refetch(); void stepsQuery.refetch(); void resolvedQuery.refetch(); void todoQuery.refetch() }}>다시 확인</button></p>
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
          {/* 계획 중에는 운영용 칸(지금 할 일 · 현재 단계 · 운영 상황 · 처리 기록) 대신 계획 요약을 보여 준다(#337) */}
          {event.status === 'PLANNING' ? (
            <PlanningOverview
              event={event}
              steps={steps}
              onContinue={() => navigate(planPath(event.id))}
            />
          ) : (
            <>
              {/* 운영진이 들어와 가장 먼저 찾는 건 내 차례인 일이라 맨 위에 둔다. 좁은 화면에서는 현재 단계가 아래로 간다. */}
              <div className="flex flex-col items-stretch gap-[20px] lg:flex-row lg:items-start">
                {(demo || operationCases.data !== undefined || operationCases.isError) && (
                  <TodoList
                    className="min-w-0 flex-1"
                    items={todos}
                    failed={todoQuery.isError && todoQuery.data === undefined}
                    onRetry={() => void todoQuery.refetch()}
                    onReview={setReviewing}
                    onComplete={finishAction}
                    onResolve={(action, choice) => {
                      if (choice === 'MANUAL') setReviewing(action)
                      else void resolveConfirmation(action, choice)
                    }}
                    onRequestDraft={(action) => void requestDraft(action)}
                    requestingDraftId={draftMutation.isPending ? draftMutation.variables?.id : undefined}
                    onOpenStep={(step) => setOpenStepId(step.id)}
                    readOnly={!demo && event.status !== 'ON_GOING'}
                  />
                )}
                {/* 진행 중인 단계가 없으면(끝난 행사) 오른쪽 칸 없이 왼쪽이 넓어진다 */}
                {currentIndex >= 0 && (
                  <CurrentStepCard
                    className="shrink-0 lg:w-[400px]"
                    step={steps[currentIndex]}
                    position={currentIndex + 1}
                    draftNotes={currentDraftNotes}
                    onOpen={() => setOpenStepId(steps[currentIndex].id)}
                  />
                )}
              </div>
              {!demo && shownId && <OperationCases key={shownId} eventId={shownId} active={event.status === 'ON_GOING'} cases={operationCases.data ?? []} loading={operationCases.isPending} error={operationCases.isError} onReload={() => void operationCases.refetch()} />}
              <ResolvedActionList
                actions={resolved?.items ?? []}
                totalCount={resolved?.totalCount ?? 0}
                expanded={allResolved}
                onExpand={() => setAllResolved(true)}
                loadingMore={allResolved && resolvedQuery.isFetching}
              />
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
              completing={completingId === openStep.id}
              readOnly={!demo && event.status !== 'ON_GOING'}
            />
          )}
          {stepDone && <StepDoneMoment moment={stepDone} onFinish={clearStepDone} />}
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
