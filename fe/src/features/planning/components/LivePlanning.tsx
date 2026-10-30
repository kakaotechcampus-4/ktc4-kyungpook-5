import { useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { usePlanningChat, usePlanningDrafts, useStartEvent } from '@/features/planning/hooks'
import { PlanChat } from '@/features/planning/components/PlanChat'
import { PlanFacts } from '@/features/planning/components/PlanFacts'
import { useAuthStore } from '@/shared/auth/store'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Modal } from '@/shared/ui/Modal'

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
  const [showFailure, setShowFailure] = useState(Boolean(failedText))
  const [confirmRegenerate, setConfirmRegenerate] = useState(false)
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
            <p role="status" className="text-ink2">
              {!eventId
                ? '먼저 어떤 행사를 준비하는지 알려 주세요.'
                : !readiness
                  ? '진행 가능 상태를 확인하지 못했어요. 대화를 이어가거나 다시 불러와 주세요.'
                  : readiness.canGenerate
                    ? '초안을 만들 준비가 됐어요. 아래 버튼을 눌러 진행해 주세요.'
                    : readiness.reasons.length
                      ? readiness.reasons
                          .map((reason) => REASONS[reason] ?? '추가 정보를 확인해 주세요.')
                          .join(' ')
                      : '대화를 이어서 필요한 정보를 확인해 주세요.'}
            </p>
            <Button
              disabled={!eventId || live.busy || !readiness?.canGenerate}
              onClick={() => (steps.length ? setConfirmRegenerate(true) : void live.generate())}
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
                    ·{' '}
                    {step.deadline ? new Date(step.deadline).toLocaleString('ko-KR') : '기한 미정'}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-mute">아직 생성된 단계가 없어요.</p>
            )}
            <PlanHandoff eventId={eventId} hasSteps={steps.length > 0} />
          </Card>
          <PlanFacts
            facts={live.facts}
            readiness={{ canGenerate: false, reasons: [] }}
            hideNext
            onNext={() => {}}
          />
        </div>
      </div>
      <Modal
        open={live.editedPlanAt !== null}
        onClose={live.dismissReplacement}
        title="수정한 계획을 교체할까요?"
        footer={
          <>
            <Button variant="secondary" onClick={live.dismissReplacement}>
              취소
            </Button>
            <Button
              disabled={live.busy}
              onClick={() => {
                if (live.editedPlanAt) void live.generate(live.editedPlanAt)
              }}
            >
              수정 내용 덮고 다시 생성
            </Button>
          </>
        }
      >
        <p>
          직접 수정한 단계와 작업이 있습니다. 다시 생성하면 수정 내용이 사라집니다. 취소하고 계획
          내용을 충분히 확인하거나, 교체에 동의할 때만 계속해 주세요.
        </p>
        <ul>
          {steps.map((step) => (
            <li key={step.id}>
              {step.name} · 작업 {step.actions.length}개
            </li>
          ))}
        </ul>
      </Modal>
      <Modal
        open={confirmRegenerate}
        onClose={() => setConfirmRegenerate(false)}
        title="초안을 다시 생성할까요?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmRegenerate(false)}>
              취소
            </Button>
            <Button
              disabled={live.busy}
              onClick={() => {
                setConfirmRegenerate(false)
                void live.generate()
              }}
            >
              확인하고 다시 생성
            </Button>
          </>
        }
      >
        <p>
          기존 단계와 작업 및 직접 수정한 내용이 새 초안으로 바뀔 수 있어요. 계속하기 전에 내용을
          확인해 주세요.
        </p>
      </Modal>
    </>
  )
}

// 단계 수정 화면으로 보내고, 계획을 진행 중으로 옮긴다.
function PlanHandoff({ eventId, hasSteps }: { eventId: string | null; hasSteps: boolean }) {
  const start = useStartEvent(eventId)
  const [error, setError] = useState('')
  const [confirmStart, setConfirmStart] = useState(false)
  if (!eventId || !hasSteps) return null
  // 시작하면 이 행사는 더 이상 계획 초안이 아니라 「계획 이어보기」 목록에서도 빠진다.
  const started = start.isSuccess
  return (
    <div className="space-y-3 border-t border-line pt-4">
      {error && (
        <p role="alert" className="text-failed">
          {error}
        </p>
      )}
      {started ? (
        <p role="status" className="font-bold text-ink">
          진행 중인 행사가 됐어요.{' '}
          <Link to="/events" className="text-blue-700 underline">
            행사 목록에서 보기
          </Link>
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Link to={`/planning/steps?eventId=${encodeURIComponent(eventId)}`}>
            <Button variant="secondary">단계 수정</Button>
          </Link>
          <Button disabled={start.isPending} onClick={() => setConfirmStart(true)}>
            {start.isPending ? '처리 중…' : '행사 시작'}
          </Button>
        </div>
      )}
      <Modal
        open={confirmStart}
        onClose={() => setConfirmStart(false)}
        title="행사를 시작할까요?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmStart(false)}>
              취소
            </Button>
            <Button
              disabled={start.isPending}
              onClick={() => {
                setConfirmStart(false)
                setError('')
                void start
                  .mutateAsync()
                  .catch(() =>
                    setError('시작 결과를 확인하지 못했어요. 행사 목록에서 상태를 확인해 주세요.'),
                  )
              }}
            >
              행사 시작
            </Button>
          </>
        }
      >
        <p>계획을 확인한 뒤 진행 중 행사로 전환합니다.</p>
      </Modal>
    </div>
  )
}
