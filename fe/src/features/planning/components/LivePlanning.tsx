import { useEffect, useId, useRef, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { CHECKING_NOTICE, usePlanningChat, usePlanningDrafts } from '@/features/planning/hooks'
import { useEventDetail, usePrefetchEventDetail } from '@/features/events/hooks'
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

// 대화로 돌아가 있는 동안 끝난 생성(#327). P2로 옮기지 않고 P1에 안내만 남긴다.
interface GenerationReady {
  eventId: string
  count: number
  key: string
}

export function LivePlanning() {
  const clubId = useAuthStore((state) => state.clubId)
  const userId = useAuthStore((state) => state.me?.id)
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const failedText = typeof location.state?.failedText === 'string' ? location.state.failedText : ''
  // 새 계획은 생성이 끝나며 이 계획 주소로 넘어가 대화 영역이 새로 그려지므로 안내를 여기 둔다.
  const [ready, setReady] = useState<GenerationReady | null>(null)
  const eventId = params.get('eventId')
  // 탭 기록은 행사마다 따로 둔다(#342). 이 행사의 결과를 확인하는 동안에도 다른 계획은 열 수 있다.
  const journal = usePlanningRequestJournal(userId, clubId, eventId)
  const [busy, setBusy] = useState(false)
  // 첫 저장으로 ID가 붙어도 같은 대화를 유지한다. 새 계획을 선택할 때만 새 세션을 만든다.
  const [newSession, setNewSession] = useState<{ key: string; eventId: string | null }>(() => ({
    key: crypto.randomUUID(),
    eventId: null,
  }))
  const blocked = busy
  const select = (id: string | null, text?: string) => {
    if (!id) setNewSession({ key: crypto.randomUUID(), eventId: null })
    setParams(id ? { eventId: id } : {}, { state: text ? { failedText: text } : null })
  }
  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="shrink-0 text-h1">행사 계획</h1>
        {clubId && (
          <div className="ml-auto flex items-center gap-2">
            {eventId && (
              <Button size="sm" variant="ghost" disabled={blocked} onClick={() => select(null)}>
                새 계획
              </Button>
            )}
            <PlanningDraftPicker
              key={`${userId}:${clubId}`}
              clubId={clubId}
              userId={userId}
              eventId={eventId}
              disabled={blocked}
              onSelect={select}
            />
          </div>
        )}
      </header>
      {!clubId ? (
        <Card className="space-y-3 p-5">
          <h2 className="text-h3">로그인과 소속 선택이 필요합니다.</h2>
          <p className="text-caption text-mute">행사 계획은 선택한 소속의 자료와 함께 저장됩니다.</p>
          <Link to="/login?next=%2Fplanning" className="text-caption font-semibold text-blue-700 underline">
            로그인·소속 선택
          </Link>
        </Card>
      ) : (
        <>
          {/* 글자가 든 채 새로 붙는 알림 영역은 낭독기가 놓칠 수 있다. 새 계획은 완료와 함께
              대화 영역이 새로 그려지므로, 그 바깥에 늘 붙여 두고 글자만 바꾼다. */}
          <p role="status" className="sr-only">
            {ready?.eventId === eventId
              ? '초안이 준비됐어요. 계획 검토하기에서 확인할 수 있어요.'
              : ''}
          </p>
          {journal.raw && !journal.request && (
            <p role="alert" className="text-failed">
              이전 요청 기록을 확인하지 못했어요. 새 요청을 보내기 전에 브라우저의 임시 저장 기능과
              처리 결과를 확인해 주세요.
            </p>
          )}
          <Conversation
            key={`${userId}:${clubId}:${!eventId || eventId === newSession.eventId ? newSession.key : eventId}`}
            clubId={clubId}
            onBusy={setBusy}
            eventId={eventId}
            onCreated={(id, text) => {
              setNewSession((session) => ({ ...session, eventId: id }))
              setParams(
                { eventId: id, stage: 'conditions' },
                { replace: true, state: text ? { failedText: text } : null },
              )
            }}
            failedText={failedText}
            userId={userId}
            ready={ready?.eventId === eventId ? ready : null}
            onReady={setReady}
          />
        </>
      )}
    </div>
  )
}

function PlanningDraftPicker({
  clubId,
  userId,
  eventId,
  disabled,
  onSelect,
}: {
  clubId: string
  userId: string | undefined
  eventId: string | null
  disabled: boolean
  onSelect: (id: string) => void
}) {
  const drafts = usePlanningDrafts(clubId, userId)
  const popoverId = useId()
  const anchorRef = useRef<HTMLDivElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    if (disabled) {
      popoverRef.current?.hidePopover()
      return
    }
    const close = () => popoverRef.current?.hidePopover()
    window.addEventListener('resize', close)
    window.addEventListener('scroll', close, { passive: true })
    return () => {
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', close)
    }
  }, [open, disabled])

  return (
    <div ref={anchorRef}>
      <Button
        size="sm"
        variant="secondary"
        disabled={disabled}
        popoverTarget={popoverId}
        aria-expanded={open}
        aria-controls={popoverId}
        onClick={() => {
          const anchor = anchorRef.current?.getBoundingClientRect()
          const popover = popoverRef.current
          if (!anchor || !popover) return
          popover.style.top = `${anchor.bottom + 8}px`
          popover.style.right = `${Math.max(16, window.innerWidth - anchor.right)}px`
          popover.style.maxHeight = `${Math.max(0, window.innerHeight - anchor.bottom - 24)}px`
        }}
      >
        이전 계획
        <svg
          aria-hidden
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d={open ? 'm6 15 6-6 6 6' : 'm6 9 6 6 6-6'} />
        </svg>
      </Button>
      <div
        ref={popoverRef}
        id={popoverId}
        popover="auto"
        role="region"
        aria-label="이전 계획"
        onToggle={(event) => setOpen(event.newState === 'open')}
        style={{ width: 'min(320px, calc(100vw - 32px))' }}
        className="fixed inset-auto m-0 overflow-y-auto rounded-xl border border-line bg-card p-2 text-ink"
      >
        {drafts.isLoading ? (
          <p role="status" className="px-3 py-4 text-caption text-mute">
            계획 목록을 불러오는 중이에요.
          </p>
        ) : drafts.isError ? (
          <div role="alert" className="space-y-2 px-3 py-4 text-caption text-ink2">
            <p>계획 목록을 불러오지 못했어요.</p>
            <Button size="sm" variant="secondary" onClick={() => void drafts.refetch()}>
              다시 시도
            </Button>
          </div>
        ) : drafts.data?.length ? (
          <ul className="divide-y divide-line">
            {drafts.data.map((draft) => (
              <li key={draft.id}>
                <button
                  type="button"
                  disabled={disabled}
                  aria-current={draft.id === eventId ? 'true' : undefined}
                  className="flex w-full flex-col gap-1 rounded-lg px-3 py-3 text-left hover:bg-bg focus-visible:outline-2 focus-visible:outline-blue-600 aria-current:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => {
                    popoverRef.current?.hidePopover()
                    onSelect(draft.id)
                  }}
                >
                  <span className="w-full break-words text-caption font-medium">{draft.title}</span>
                  <span className="text-[12px] text-mute">
                    {new Date(draft.savedAt ?? draft.createdAt).toLocaleDateString('ko-KR')}
                    {draft.savedAt ? ' 저장' : ' 생성'}
                    {draft.id === eventId && ' · 현재 계획'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-3 py-4 text-caption text-mute">아직 저장된 계획이 없어요.</p>
        )}
      </div>
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
  ready,
  onReady,
}: {
  clubId: string
  eventId: string | null
  onCreated: (id: string, failedText?: string) => void
  failedText: string
  userId: string | undefined
  onBusy: (busy: boolean) => void
  ready: GenerationReady | null
  onReady: (ready: GenerationReady | null) => void
}) {
  const navigate = useNavigate()
  const generationDescriptionId = useId()
  // 생성 중 「대화로 돌아가기」(#327). 화면만 바꾸고 요청은 이 훅에서 계속 받는다.
  // 완료 콜백은 요청을 보낸 렌더의 것이 불리므로 지금 보고 있는 화면은 ref로 읽는다.
  const [away, setAway] = useState(false)
  const awayRef = useRef(false)
  const showChat = (value: boolean) => {
    awayRef.current = value
    setAway(value)
  }
  const awayNote = useRef<HTMLParagraphElement>(null)
  useEffect(() => {
    if (away) awayNote.current?.focus()
  }, [away])
  const prefetchEventDetail = usePrefetchEventDetail()
  const chat = usePlanningChat(
    clubId,
    eventId,
    userId,
    onCreated,
    (id, count, key) => {
      if (awayRef.current) {
        onReady({ eventId: id, count, key })
        if (!eventId) onCreated(id)
        return
      }
      navigate(`/planning?${new URLSearchParams({ eventId: id, stage: 'review' })}`, {
        replace: true,
        state: { generated: count > 0 ? { count, key } : undefined, focusPlan: true },
      })
    },
    prefetchEventDetail,
  )
  // 대화로 돌아가 있으면 생성 화면 대신 P1을 그린다. 잠금은 chat.busy가 그대로 건다.
  const live = away ? { ...chat, generationFlow: null } : chat
  // 새 요청은 생성 화면부터 보이고, 지난 완료 안내는 내린다.
  const beginRequest = () => {
    showChat(false)
    onReady(null)
  }
  useEffect(() => {
    onBusy(live.streaming)
  }, [live.streaming, onBusy])
  const [params] = useSearchParams()
  const event = useEventDetail(eventId ?? undefined)
  // 확인 중에 행사 상세를 못 불러왔다면 확인이 끝난 뒤 다시 불러온다(#368). 대화는 조회가 끝날 때
  // 다시 불러오지만 행사 상세는 따로 불러야 한다.
  const checking = live.checking
  const reloadEvent = event.refetch
  const eventMissing = event.isError && event.data === undefined
  useEffect(() => {
    if (!checking && eventMissing) void reloadEvent()
  }, [checking, eventMissing, reloadEvent])
  const [showFailure, setShowFailure] = useState(Boolean(failedText))
  // 끊긴 첫 메시지가 저장된 것으로 확인되면 "결과를 확인해 주세요" 안내를 내린다(#342).
  if (showFailure && live.settled === 'saved') setShowFailure(false)
  if (live.generationFlow)
    return (
      <>
        <PlanStageNav current="conditions" />
        <GenerationScreen
          flow={live.generationFlow}
          onReload={live.reloadGenerated}
          onViewCurrent={live.viewCurrentPlan}
          onBackToChat={() => showChat(true)}
        />
      </>
    )
  // 끊긴 채팅을 확인하는 중인데 서버가 아직 응답하지 않아 저장된 대화를 못 불러온 경우(#368).
  // 예: 배포 중 새로고침. 오류 카드 대신 확인 중임을 알리고, 확인이 끝나면 다시 불러온다.
  if (eventId && live.checking && (!live.snapshot.data || event.data === undefined))
    return (
      <>
        <PlanStageNav current="conditions" />
        <Card className="p-5" role="status">
          {CHECKING_NOTICE}
        </Card>
      </>
    )
  if (eventId && (live.snapshot.isLoading || event.isPending))
    return (
      <Card className="p-5" role="status">
        저장된 계획을 불러오는 중이에요.
      </Card>
    )
  // 이미 불러온 계획이 있으면 다시 불러오기가 실패해도 대화를 그대로 보인다. 끊긴 채팅을 확인하는
  // 동안(#368) 서버가 응답하지 않아도 대화 화면이 오류 카드로 바뀌지 않게 한다.
  if (
    eventId &&
    ((live.snapshot.isError && !live.snapshot.data) || (event.isError && event.data === undefined))
  )
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
  const flow = chat.generationFlow
  return (
    <>
      <PlanStageNav current="conditions" />
      {away && flow && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl bg-blue-50 px-4 py-3">
          <p ref={awayNote} tabIndex={-1} className="break-keep text-ink focus:outline-none">
            {['requesting', 'generating', 'verifying', 'loading'].includes(flow.phase)
              ? '초안을 만들고 있어요. 생성은 계속되고, 끝날 때까지 새 대화와 생성은 잠가 둘게요.'
              : '초안 생성 결과를 확인해야 해요.'}
          </p>
          <Button size="sm" variant="secondary" onClick={() => showChat(false)}>
            생성 화면 보기
          </Button>
        </div>
      )}
      {ready && eventId && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl bg-blue-50 px-4 py-3">
          <p className="break-keep font-semibold text-ink">초안이 준비됐어요.</p>
          <Link
            className="rounded-lg px-2 py-2 text-caption font-semibold text-blue-700 underline underline-offset-4 hover:bg-blue-100"
            to={`/planning?${new URLSearchParams({ eventId, stage: 'review' })}`}
            state={{
              generated: ready.count > 0 ? { count: ready.count, key: ready.key } : undefined,
              focusPlan: true,
            }}
            onClick={() => onReady(null)}
          >
            계획 검토하기
          </Link>
        </div>
      )}
      {stage === 'review' && !eventId && (
        <p role="status" className="text-mute">
          먼저 행사 조건을 정하고 초안을 만들어 주세요.
        </p>
      )}
      {generationFailure && !live.busy && (
        <GenerationFailureNotice result={generationFailure} hasPrevious={steps.length > 0} />
      )}
      <div className="flex flex-col items-start gap-5 lg:flex-row">
        <PlanChat
          messages={live.messages}
          onSend={async (text) => {
            beginRequest()
            const success = await live.send(text)
            if (success) setShowFailure(false)
            return success
          }}
          busy={live.busy}
          pendingText={live.pendingText}
          progress={live.progress}
          pendingReply={live.pendingReply}
          notice={live.notice}
          historyUsage={live.view?.historyUsage ?? screen?.historyUsage ?? null}
          error={
            // 끊긴 채팅을 확인하는 동안에는 확인 중 안내(notice)만 보인다(#368). 결과가 나오면
            // 저장됨·저장 안 됨에 맞는 문구로 바뀐다.
            live.checking
              ? ''
              : (!generationFailure ? live.error : '') ||
                (showFailure ? '이전 요청 결과를 확인해 주세요. 서버에 반영됐을 수 있어요.' : '')
          }
          onReload={
            eventId ? () => Promise.all([live.snapshot.refetch(), event.refetch()]) : undefined
          }
          persisted={!!eventId}
          initialDraft={
            // 결과 확인 화면 뒤에 입력창이 다시 그려진다. 저장되지 않았으면 원래 문장을 되돌리고,
            // 저장된 것으로 확인됐으면 다시 보내지 않게 비운다(#342).
            live.retryText || (live.settled === 'saved' ? '' : failedText)
          }
          // 대화 화면에서 확인한 채팅은 입력창이 다시 그려지지 않아 이 값으로 맞춘다(#368).
          draftReset={live.draftReset}
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
              onClick={() => {
                beginRequest()
                void live.generate()
              }}
            >
              {live.generating
                ? '초안을 만드는 중…'
                : steps.length
                  ? '이 조건으로 다시 만들기'
                  : '이 조건으로 초안 만들기'}
            </Button>
            {/* 생성 중에는 지난 초안으로 가는 길을 닫고, 완료 안내가 있으면 그 링크 하나만 둔다. */}
            {eventId && steps.length > 0 && !flow && !live.checking && !ready && (
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
