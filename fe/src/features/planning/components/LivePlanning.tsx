import { useEffect, useId, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { usePlanningChat, usePlanningDrafts } from '@/features/planning/hooks'
import { useEventDetail } from '@/features/events/hooks'
import { planningStage } from '../reviewModel'
import { PlanReviewScreen } from './PlanReviewScreen'
import { PlanStageNav } from './PlanStageNav'
import { GenerationScreen } from './GenerationScreen'
import { GenerationFailureNotice } from './GenerationFailureNotice'
import { usePlanningRequestJournal } from '../useGenerationRequest'
import { PlanChat } from '@/features/planning/components/PlanChat'
import { PlanFacts } from '@/features/planning/components/PlanFacts'
import { PlanningRecordReferences } from '@/features/planning/components/PlanningRecordReferences'
import { useAuthStore } from '@/shared/auth/store'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'

const REASONS: Record<string, string> = {
  event_type_missing: '행사 종류를 알려 주세요.',
  dates_unanswered: '일정을 알려 주거나 아직 미정이라고 말해 주세요.',
  headcount_unanswered: '예상 인원을 알려 주거나 아직 미정이라고 말해 주세요.',
  location_unanswered: '장소를 알려 주거나 아직 미정이라고 말해 주세요.',
  condition_change_pending: '반영하지 못한 조건 변경을 먼저 확인해 주세요.',
}

export function LivePlanning() {
  const clubId = useAuthStore((state) => state.clubId)
  const userId = useAuthStore((state) => state.me?.id)
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const failedText = typeof location.state?.failedText === 'string' ? location.state.failedText : ''
  const eventId = params.get('eventId')
  const drafts = usePlanningDrafts(clubId, userId)
  const journal = usePlanningRequestJournal(userId, clubId)
  const [busy, setBusy] = useState(false)
  const blocked = busy || !!journal.raw
  const select = (id: string | null, text?: string) =>
    setParams(id ? { eventId: id } : {}, { state: text ? { failedText: text } : null })
  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="text-h1">행사 계획</h1>
        <p className="text-mute">대화로 조건을 정하고 계획 초안을 확인해요.</p>
      </header>
      {!clubId ? (
        <Card className="p-5">로그인하고 소속을 선택해 주세요.</Card>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line pb-4">
            <label htmlFor="planning-draft" className="text-caption font-medium text-ink2">
              계획 이어보기
            </label>
            <select
              id="planning-draft"
              className="min-h-11 min-w-0 max-w-full flex-1 rounded-lg border border-soft bg-card py-2 pr-8 pl-3 text-caption sm:max-w-[360px]"
              disabled={blocked}
              value={eventId ?? ''}
              onChange={(event) => select(event.target.value || null)}
            >
              <option value="">새 계획</option>
              {drafts.data?.map((draft) => (
                <option key={draft.id} value={draft.id}>
                  {draft.title} · {new Date(draft.createdAt).toLocaleDateString('ko-KR')}
                </option>
              ))}
              {eventId && drafts.data && !drafts.data.some((draft) => draft.id === eventId) && (
                <option value={eventId}>선택한 계획</option>
              )}
            </select>
            <Button variant="secondary" disabled={blocked} onClick={() => select(null)}>
              새 계획
            </Button>
            {drafts.isLoading && <span role="status">계획 목록을 불러오는 중이에요.</span>}
            {drafts.isError && (
              <span role="alert">
                계획 목록을 불러오지 못했어요.{' '}
                <button className="underline" onClick={() => void drafts.refetch()}>
                  다시 시도
                </button>
              </span>
            )}
          </div>
          {journal.raw && !journal.request && (
            <p role="alert" className="text-failed">
              이전 요청 기록을 확인하지 못했어요. 새 요청을 보내기 전에 브라우저의 임시 저장 기능과
              처리 결과를 확인해 주세요.
            </p>
          )}
          {journal.request && journal.request.eventId !== eventId && (
            <p role="status" className="text-ink2">
              다른 계획의 처리 결과를 확인해야 해요. 새 요청은 잠가 두었어요.{' '}
              <Link
                className="font-semibold text-blue-700 underline"
                to={`/planning?${new URLSearchParams({ eventId: journal.request.eventId, stage: 'conditions' })}`}
              >
                요청한 계획 확인하기
              </Link>
            </p>
          )}
          <Conversation
            key={`${userId}:${clubId}:${eventId ?? 'new'}`}
            clubId={clubId}
            onBusy={setBusy}
            eventId={eventId}
            onCreated={(id, text) =>
              setParams(
                { eventId: id, stage: 'conditions' },
                { state: text ? { failedText: text } : null },
              )
            }
            failedText={failedText}
            userId={userId}
          />
        </>
      )}
    </div>
  )
}

function Conversation({
  clubId,
  eventId,
  onCreated,
  failedText,
  userId,
  onBusy,
}: {
  clubId: string
  eventId: string | null
  onCreated: (id: string, failedText?: string) => void
  failedText: string
  userId: string | undefined
  onBusy: (busy: boolean) => void
}) {
  const navigate = useNavigate()
  const generationDescriptionId = useId()
  const live = usePlanningChat(clubId, eventId, userId, onCreated, (id, count, key) => {
    navigate(`/planning?${new URLSearchParams({ eventId: id, stage: 'review' })}`, {
      replace: true,
      state: { generated: count > 0 ? { count, key } : undefined, focusPlan: true },
    })
  })
  useEffect(() => {
    onBusy(live.busy)
  }, [live.busy, onBusy])
  const [params] = useSearchParams()
  const event = useEventDetail(eventId ?? undefined)
  const [showFailure, setShowFailure] = useState(Boolean(failedText))
  if (live.generationFlow)
    return (
      <>
        <PlanStageNav current="conditions" />
        <GenerationScreen
          flow={live.generationFlow}
          onReload={live.reloadGenerated}
          onViewCurrent={live.viewCurrentPlan}
        />
      </>
    )
  if (eventId && (live.snapshot.isLoading || event.isPending))
    return (
      <Card className="p-5" role="status">
        저장된 계획을 불러오는 중이에요.
      </Card>
    )
  if (eventId && (live.snapshot.isError || event.isError))
    return (
      <Card className="p-5" role="alert">
        저장된 계획을 불러오지 못했어요. 권한과 연결을 확인해 주세요.{' '}
        <button
          className="underline"
          onClick={() => {
            void live.snapshot.refetch()
            void event.refetch()
          }}
        >
          다시 시도
        </button>
      </Card>
    )
  const screen = live.snapshot.data?.screen
  // P2와 편집기는 같은 행사에 저장된 최신 단계를 사용한다.
  const steps = live.snapshot.data?.steps ?? []
  const stage = params.get('stage')
  if (eventId && event.data && event.data.status !== 'PLANNING') {
    return <Navigate replace to={`/events/${encodeURIComponent(eventId)}`} />
  }
  // 최초 주소 해석과 생성 성공 이동은 구분한다. 성공은 검증된 스냅샷을 받은 뒤 replace한다.
  if (
    eventId &&
    screen &&
    ((stage !== 'review' && stage !== 'conditions') || (stage === 'review' && !steps.length))
  ) {
    return (
      <Navigate
        replace
        to={`/planning?${new URLSearchParams({ eventId, stage: planningStage(stage, steps.length > 0) })}`}
      />
    )
  }
  if (eventId && screen && stage === 'review') {
    return (
      <PlanReviewScreen
        eventId={eventId}
        screen={screen}
        steps={steps}
        messages={live.snapshot.data?.messages ?? []}
        onReload={() => live.snapshot.refetch()}
      />
    )
  }
  const readiness = live.view?.generationReadiness ?? screen?.generationReadiness ?? null
  const lastMessage = live.snapshot.data?.messages.at(-1)
  const generationFailure = live.generationFailure
  return (
    <>
      <PlanStageNav current="conditions" />
      {stage === 'review' && !eventId && (
        <p role="status" className="text-mute">
          먼저 행사 조건을 정하고 초안을 만들어 주세요.
        </p>
      )}
      {eventId && !steps.length && params.get('stage') === 'conditions' && (
        <p className="text-mute">저장된 초안이 없어요. 조건을 정한 뒤 초안을 만들 수 있어요.</p>
      )}
      {generationFailure && !live.busy && (
        <GenerationFailureNotice result={generationFailure} hasPrevious={steps.length > 0} />
      )}
      <div className="flex flex-col items-start gap-5 lg:flex-row">
        <PlanChat
          messages={live.messages}
          onSend={async (text) => {
            const success = await live.send(text)
            if (success) setShowFailure(false)
            return success
          }}
          busy={live.busy}
          pendingText={live.pendingText}
          progress={live.progress}
          pendingReply={live.pendingReply}
          notice={live.notice}
          error={
            (!generationFailure ? live.error : '') ||
            (showFailure ? '이전 요청 결과를 확인해 주세요. 서버에 반영됐을 수 있어요.' : '')
          }
          onReload={
            eventId ? () => Promise.all([live.snapshot.refetch(), event.refetch()]) : undefined
          }
          persisted={!!eventId}
          initialDraft={failedText}
        />
        <div className="flex w-full min-w-0 flex-col gap-4 lg:w-[340px] lg:shrink-0">
          {lastMessage?.role === 'USER' && !live.busy && (
            <p role="alert" className="text-failed">
              마지막 답변에 대한 질문을 받지 못했어요. 연결 상태를 확인해 주세요.
            </p>
          )}
          {/* 현재 조건과 과거 기록을 분리한다. 진행 줄은 이번 턴의 작업,
              아래 참고 카드는 저장된 사실과 출처를 보여준다. */}
          <PlanFacts facts={live.facts} flash={live.factFlash}>
            <p
              id={generationDescriptionId}
              role="status"
              className="text-caption leading-relaxed text-ink2"
            >
              {!eventId
                ? '어떤 행사를 준비하는지 토리에게 알려 주세요.'
                : !readiness
                  ? '생성 가능 상태를 확인하지 못했어요. 대화를 이어가거나 다시 불러와 주세요.'
                  : readiness.canGenerate
                    ? steps.length
                      ? '다시 만들면 기존 단계와 직접 수정한 내용이 새 초안으로 바뀌어요.'
                      : '이 조건으로 초안을 만들 수 있어요. 만든 뒤 단계와 일정을 수정할 수 있어요.'
                    : readiness.reasons.length
                      ? readiness.reasons
                          .map((reason) => REASONS[reason] ?? '추가 정보를 확인해 주세요.')
                          .join(' ')
                      : '대화를 이어서 필요한 정보를 확인해 주세요.'}
            </p>
            {/* 상담·검색 대기는 누르기만 잠근다. 실제 생성 전환은 #338의 흐름을 유지한다. */}
            <Button
              className="min-h-11 w-full whitespace-normal break-keep"
              aria-describedby={generationDescriptionId}
              loading={live.generating}
              disabled={!eventId || !readiness?.canGenerate || live.busy}
              onClick={() => void live.generate()}
            >
              {live.generating
                ? '초안을 만드는 중…'
                : steps.length
                  ? '이 조건으로 다시 만들기'
                  : '이 조건으로 초안 만들기'}
            </Button>
            {eventId && steps.length > 0 && (
              <Link
                className="self-center rounded-lg px-2 py-2 text-caption font-semibold text-blue-700 underline underline-offset-4 hover:bg-blue-50"
                to={`/planning?${new URLSearchParams({ eventId, stage: 'review' })}`}
              >
                기존 초안 검토하기
              </Link>
            )}
          </PlanFacts>
          <PlanningRecordReferences entries={live.recordHistory} />
        </div>
      </div>
    </>
  )
}
