import { useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import {
  usePlanningChat,
  usePlanningDrafts,
  useRequestPlanReview,
  useReviewInFlight,
  useStartEvent,
} from '@/features/planning/hooks'
import { PlanChat } from '@/features/planning/components/PlanChat'
import { PlanFacts } from '@/features/planning/components/PlanFacts'
import { PlanningRecordReferences } from '@/features/planning/components/PlanningRecordReferences'
import { PlanReviewCard } from '@/features/planning/components/PlanReviewCard'
import { reviewCardState, showGenerationWarnings } from '@/features/planning/reviewState'
import type { components } from '@/shared/api/schema'
import { useAuthStore } from '@/shared/auth/store'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { formatDateTime } from '@/shared/lib/format'

type S = components['schemas']

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
            <Button variant="secondary" onClick={() => select(null)}>
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
          <Conversation
            key={`${userId}:${clubId}:${eventId ?? 'new'}`}
            clubId={clubId}
            eventId={eventId}
            onCreated={select}
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
}: {
  clubId: string
  eventId: string | null
  onCreated: (id: string, failedText?: string) => void
  failedText: string
  userId: string | undefined
}) {
  const live = usePlanningChat(clubId, eventId, userId, onCreated)
  const [showFailure, setShowFailure] = useState(Boolean(failedText))
  if (eventId && live.snapshot.isLoading)
    return (
      <Card className="p-5" role="status">
        저장된 계획을 불러오는 중이에요.
      </Card>
    )
  if (eventId && live.snapshot.isError)
    return (
      <Card className="p-5" role="alert">
        저장된 계획을 불러오지 못했어요. 권한과 연결을 확인해 주세요.{' '}
        <button className="underline" onClick={() => void live.snapshot.refetch()}>
          다시 시도
        </button>
      </Card>
    )
  const screen = live.snapshot.data?.screen
  // 단계 수정 화면에서 저장한 구성이 있으면 그걸 반영해 보여준다(#213 전까지 로컬).
  const steps = live.snapshot.data?.steps ?? []
  const readiness = live.view?.generationReadiness ?? screen?.generationReadiness ?? null
  const lastMessage = live.snapshot.data?.messages.at(-1)
  return (
    <>
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
            live.error ||
            (showFailure ? '이전 요청 결과를 확인해 주세요. 서버에 반영됐을 수 있어요.' : '')
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
          <PlanFacts
            facts={live.facts}
            flash={live.factFlash}
            readiness={{ canGenerate: false, reasons: [] }}
            hideNext
            onNext={() => {}}
          />
          <PlanningRecordReferences entries={live.recordHistory} />
          <Card className="space-y-4 p-5">
            <h2 className="text-h2">계획 초안</h2>
            <p role="status" className="text-ink2">
              {!eventId
                ? '어떤 행사를 준비하는지 알려 주시면 초안을 만들 수 있어요.'
                : !readiness
                  ? '진행 가능 상태를 확인하지 못했어요. 대화를 이어가거나 다시 불러와 주세요.'
                  : readiness.canGenerate
                    ? steps.length
                      ? '다시 만들면 지금 단계가 새 결과로 바뀌어요.'
                      : '지금 조건으로 초안을 만들 수 있어요. 행사 시작이나 발송은 하지 않아요.'
                    : readiness.reasons.length
                      ? readiness.reasons
                          .map((reason) => REASONS[reason] ?? '추가 정보를 확인해 주세요.')
                          .join(' ')
                      : '대화를 이어서 필요한 정보를 확인해 주세요.'}
            </p>
            {/* 채팅 답변을 기다리는 동안은 누를 수만 없게 하고, "만드는 중"은 이 버튼으로 생성할 때만 보인다. */}
            <Button
              className="w-full"
              loading={live.generating}
              disabled={!eventId || !readiness?.canGenerate || live.busy}
              onClick={() => void live.generate()}
            >
              {live.generating
                ? '초안을 만드는 중…'
                : steps.length
                  ? '지금 조건으로 다시 만들기'
                  : '지금 조건으로 초안 만들기'}
            </Button>
            {screen && steps.length > 0 && (
              <StepSummaryLine summary={screen.summary} steps={steps} edited={false} />
            )}
            {/* 생성 때 낸 주의사항은 계획을 고친 뒤엔 낡은 정보라 숨긴다. 대신 아래 검토 카드가 안내한다. */}
            {screen &&
              showGenerationWarnings(screen.planRevision, screen.review ?? null) &&
              screen.warnings.map((warning, index) => (
                <p key={index} className="text-mute">
                  {warning}
                </p>
              ))}
            {steps.length > 0 && (
              <ol className="space-y-2">
                {steps.map((step) => (
                  <li key={step.id} className="flex flex-col gap-[2px] rounded bg-bg p-3">
                    <strong>
                      {step.stepOrder}. {step.name}
                    </strong>
                    <span className="text-label text-mute">
                      {step.actor === 'AI'
                        ? 'AI 실행'
                        : step.actor === 'APPROVAL_REQUIRED'
                          ? '승인 필요'
                          : '직접 수행'}{' '}
                      · {step.deadline ? `${formatDateTime(step.deadline)}까지` : '기한 미정'}
                    </span>
                  </li>
                ))}
              </ol>
            )}
            <PlanHandoff eventId={eventId} hasSteps={steps.length > 0} />
          </Card>
          {eventId && screen && <PlanReview eventId={eventId} screen={screen} />}
        </div>
      </div>
    </>
  )
}

// 계획 수정 후 AI 검토 (#177). 단계 수정 화면에서 바뀐 채로 저장하면 그 화면이 검토를 요청하고,
// 여기서는 진행 중·결과·「다시 검토」를 보여준다. 세부 수정만 했으면 「다시 필요」로 바뀐다.
function PlanReview({ eventId, screen }: { eventId: string; screen: S['PlanScreenOut'] }) {
  const requestReview = useRequestPlanReview(eventId)
  const requesting = useReviewInFlight(eventId)
  const review = screen.review ?? null
  return (
    <PlanReviewCard
      state={reviewCardState({ planRevision: screen.planRevision, review, requesting })}
      review={review}
      requesting={requesting}
      onRequest={() => requestReview.mutate(screen.planRevision)}
    />
  )
}

// 단계 수정 화면으로 보내고, 행사를 시작으로 표시한다.
function PlanHandoff({ eventId, hasSteps }: { eventId: string | null; hasSteps: boolean }) {
  const start = useStartEvent(eventId)
  const [started, setStarted] = useState(false)
  if (!eventId || !hasSteps) return null
  return (
    <div className="space-y-3 border-t border-line pt-4">
      {started ? (
        <p role="status" className="font-bold text-ink">
          시작한 행사로 표시했어요.{' '}
          <Link to="/events" className="text-blue-700 underline">
            행사 목록에서 보기
          </Link>
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Link to={`/planning/steps?eventId=${encodeURIComponent(eventId)}`}>
            <Button variant="secondary">단계 수정</Button>
          </Link>
          <Button
            disabled={start.isPending}
            onClick={() => void start.mutateAsync().then(() => setStarted(true))}
          >
            {start.isPending ? '처리 중…' : '행사 시작'}
          </Button>
        </div>
      )}
    </div>
  )
}

// 단계를 빼고 나면 서버가 보낸 개수와 화면에 보이는 목록이 어긋난다.
// 저장한 구성이 있을 때만 보이는 목록에서 다시 센다(#213 전까지 로컬).
function StepSummaryLine({
  summary,
  steps,
  edited,
}: {
  summary: S['PlanSummaryOut']
  steps: S['PlannedStepOut'][]
  edited: boolean
}) {
  const counted = edited
    ? {
        totalSteps: steps.length,
        aiSteps: steps.filter((step) => step.actor === 'AI').length,
        approvalSteps: steps.filter((step) => step.actor === 'APPROVAL_REQUIRED').length,
        manualSteps: steps.filter((step) => step.actor === 'MANUAL').length,
      }
    : summary
  return (
    <p className="text-mute">
      전체 {counted.totalSteps}단계 · AI {counted.aiSteps} · 승인 필요 {counted.approvalSteps} ·
      직접 수행 {counted.manualSteps}
    </p>
  )
}
