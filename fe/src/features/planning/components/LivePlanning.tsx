import { useLocation, useSearchParams } from 'react-router-dom'
import { usePlanningChat, usePlanningDrafts } from '@/features/planning/hooks'
import { PlanChat } from '@/features/planning/components/PlanChat'
import { PlanFacts } from '@/features/planning/components/PlanFacts'
import { useAuthStore } from '@/shared/auth/store'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'

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
          <Card className="flex flex-wrap items-center gap-3 p-4">
            <label htmlFor="planning-draft">계획 이어보기</label>
            <select
              id="planning-draft"
              className="rounded border border-line p-2"
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
          </Card>
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
  const steps = live.snapshot.data?.steps ?? []
  const lookup = live.view?.recordLookup
  return (
    <>
      <div className="flex flex-col items-start gap-5 lg:flex-row">
        <PlanChat
          messages={live.messages}
          onSend={live.send}
          busy={live.busy}
          error={
            live.error ||
            (failedText ? '이전 요청 결과를 확인해 주세요. 서버에 반영됐을 수 있어요.' : '')
          }
          persisted={!!eventId}
          initialDraft={failedText}
        />
        <PlanFacts
          facts={live.facts}
          readiness={{ canGenerate: false, reasons: [] }}
          hideNext
          onNext={() => {}}
        />
      </div>
      {lookup && (
        <p role="status" className="text-mute">
          {lookup.status === 'available'
            ? '관련 자료를 참고했어요.'
            : lookup.status === 'not_found'
              ? '관련 자료를 찾지 못했어요.'
              : lookup.status === 'failed'
                ? '자료 검색에 실패했어요.'
                : '자료 조회를 진행하지 못했어요.'}
        </p>
      )}
      <Card className="space-y-4 p-5">
        <h2 className="text-h2">계획 초안</h2>
        <p className="text-mute">
          생성하면 기존 초안 단계가 새 결과로 바뀝니다. 행사 시작이나 발송은 진행되지 않아요.
        </p>
        <Button
          disabled={
            !eventId ||
            live.busy ||
            (live.view ? !live.view.generationReadiness.canGenerate : false)
          }
          onClick={() => void live.generate()}
        >
          {live.busy ? '처리 중…' : '현재 조건으로 초안 생성'}
        </Button>
        {screen && (
          <p className="text-mute">
            전체 {screen.summary.totalSteps}단계 · AI {screen.summary.aiSteps} · 승인 필요{' '}
            {screen.summary.approvalSteps} · 직접 수행 {screen.summary.manualSteps}
          </p>
        )}
        {screen?.warnings.map((warning, index) => (
          <p key={index} className="text-mute">
            {warning}
          </p>
        ))}
        {steps.length > 0 ? (
          <ol className="space-y-2">
            {steps.map((step) => (
              <li key={step.id} className="rounded bg-bg p-3">
                <strong>
                  {step.stepOrder}. {step.name}
                </strong>{' '}
                ·{' '}
                {step.actor === 'AI'
                  ? 'AI 실행'
                  : step.actor === 'APPROVAL_REQUIRED'
                    ? '승인 필요'
                    : '직접 수행'}{' '}
                · {step.deadline ? new Date(step.deadline).toLocaleString('ko-KR') : '기한 미정'}
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-mute">아직 생성된 단계가 없어요.</p>
        )}
        <p className="text-mute">단계 수정과 행사 시작은 준비 중입니다.</p>
      </Card>
    </>
  )
}
