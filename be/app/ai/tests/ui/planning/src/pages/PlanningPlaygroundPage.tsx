import { useEffect, useRef, useState } from 'react'
import { PlanChat } from '@/features/planning/components/PlanChat'
import { PlanFacts } from '@/features/planning/components/PlanFacts'
import { AgentReferences } from '@/features/planning/components/AgentReferences'
import { AgentPlanPreview } from '@/features/planning/components/AgentPlanPreview'
import type { ChatMessage } from '@/features/planning/types'
import { testApi, toAgentFacts, TOPIC_LABELS } from '@/features/planning/agent-playground'
import type {
  AgentHealth,
  AgentResult,
  RecordLookup,
  HistoryUsage,
} from '@/features/planning/agent-playground'
import {
  latestToolCalls,
  latestUserMessage,
  newSession,
  previewIsCurrent,
} from '@/features/planning/generation-playground'
import type { GenerationUpdate, PendingRequest } from '@/features/planning/generation-playground'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'

const greeting: ChatMessage = {
  id: 'hello',
  from: '토리',
  text: '안녕하세요! 어떤 행사를 준비하고 계세요? 아직 정하지 못한 부분도 같이 생각해봐요.',
  quickReplies: ['MT', '워크숍', '신환회'],
}
type ApiResponse<T> = {
  result: T
  elapsed_ms: number
  fixture_count: number
  history_usage: HistoryUsage
}
type Work = 'chat' | 'button' | 'records' | 'connect'
const executionLabels: Record<string, string> = {
  applied: '반영',
  unchanged: '유지',
  rejected: '미반영',
  available: '조회 성공',
  not_found: '근거 없음',
  failed: '처리 실패',
  generated: '초안 생성',
  needs_clarification: '추가 확인',
}
async function connect() {
  const health = await testApi<AgentHealth>('health')
  if (!health.record_search || !health.plan_generation)
    throw new Error('계획 생성 기능이 연결된 새 API를 사용하려면 AI 테스트 서버를 재시작해 주세요.')
  return health
}

export default function PlanningPlaygroundPage() {
  const [dialogKey, setDialogKey] = useState(() => crypto.randomUUID())
  const [messages, setMessages] = useState<ChatMessage[]>([greeting])
  // 버튼은 generation만 갱신한다. AI가 반환한 SDK 이력은 원형으로 별도 보관한다.
  const [session, setSession] = useState(newSession)
  const [view, setView] = useState<'chat' | 'preview'>('chat')
  const [work, setWork] = useState<Work | null>(null)
  const inFlight = useRef(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState<PendingRequest | null>(null)
  const [health, setHealth] = useState<AgentHealth | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [reference, setReference] = useState<RecordLookup | null>(null)
  const [notice, setNotice] = useState('')
  const [historyUsage, setHistoryUsage] = useState<HistoryUsage | null>(null)
  const [debug, setDebug] = useState<unknown>(null)
  const [stats, setStats] = useState<{
    agent: number
    generation: number
    executions: AgentResult['executions']
    limited: boolean
  } | null>(null)
  const [referenceDate, setReferenceDate] = useState(() =>
    new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' }),
  )
  const busy = work !== null
  const { draft, history, generation } = session
  const current = previewIsCurrent(session)
  const ready = !!draft.conditions.event_type && !generation.condition_change_pending
  const locked = busy || !!pending || !health || history.length > 60

  useEffect(() => {
    let active = true
    connect()
      .then((h) => {
        if (active) setHealth(h)
      })
      .catch((e: unknown) => {
        if (active)
          setError(e instanceof Error ? e.message : 'AI 테스트 서버 연결을 확인해 주세요.')
      })
    return () => {
      active = false
    }
  }, [])

  const begin = (kind: Work) => {
    // 렌더 전에 연속으로 들어온 클릭도 막는다.
    if (inFlight.current) return false
    inFlight.current = true
    setWork(kind)
    setError('')
    setNotice('')
    return true
  }
  const finish = () => {
    inFlight.current = false
    setWork(null)
  }
  const reconnect = async () => {
    if (!begin('connect')) return
    try {
      setHealth(await connect())
    } catch (e) {
      setError(e instanceof Error ? e.message : '연결에 실패했어요.')
    } finally {
      finish()
    }
  }
  const reset = () => {
    if (inFlight.current) return
    setDialogKey(crypto.randomUUID())
    setMessages([greeting])
    setSession(newSession())
    setHistoryUsage(null)
    setView('chat')
    setError('')
    setPending(null)
    setElapsed(null)
    setReference(null)
    setNotice('')
    setDebug(null)
    setStats(null)
  }

  const execute = async (request: PendingRequest) => {
    if (!health || !begin(request.source)) return
    if (request.source === 'chat') {
      const m = request.body.current_message
      setMessages((previous) =>
        previous.some((x) => x.id === m.id)
          ? previous
          : [...previous, { id: m.id, from: '나', text: m.text }],
      )
    }
    try {
      if (request.source === 'chat') {
        const response = await testApi<ApiResponse<AgentResult>>('agent/turn', request.body)
        const result = response.result
        setHistoryUsage(response.history_usage ?? null)
        setSession({ draft: result.draft, history: result.history, generation: result.generation })
        if (result.record_lookup) setReference(result.record_lookup)
        const reply: ChatMessage = {
          id: `${request.body.current_message.id}-reply`,
          from: '토리',
          text: result.reply,
        }
        setMessages((previous) => [...previous.filter((x) => x.id !== reply.id), reply])
        setStats({
          agent: result.model_calls,
          generation: result.generation_model_calls,
          executions: result.executions,
          limited: result.limit_reached,
        })
        // 진단 화면에는 SDK 메타정보·비텍스트 응답 블록을 덤프하지 않는다.
        setDebug({
          source: 'chat',
          draft: result.draft,
          generation: result.generation,
          generation_result: result.generation_result,
          reply: result.reply,
          executions: result.executions,
          history_messages: result.history.length,
          model_calls: result.model_calls,
          generation_model_calls: result.generation_model_calls,
        })
        if (result.generation_result?.status === 'generated' && result.generation.preview)
          setView('preview')
        if (result.generation_result?.status === 'failed')
          setError(result.generation_result.reason ?? '초안을 만들지 못했어요. 다시 만들어 주세요.')
        setElapsed(response.elapsed_ms)
        setHealth((h) => (h ? { ...h, fixture_count: response.fixture_count } : h))
      } else {
        const response = await testApi<ApiResponse<GenerationUpdate>>(
          'agent/generate',
          request.body,
        )
        const update = response.result
        setHistoryUsage(response.history_usage ?? null)
        setSession((previous) => ({ ...previous, generation: update.generation }))
        setStats({
          agent: 0,
          generation: update.result.model_calls,
          executions: [],
          limited: false,
        })
        setDebug({
          source: 'button',
          ...update,
          draft: request.body.draft,
          history_messages: request.body.history.length,
        })
        if (update.result.status === 'generated' && update.generation.preview) setView('preview')
        else
          setError(
            update.result.reason ?? '초안을 만들지 못했어요. 조건을 확인하고 다시 만들어 주세요.',
          )
        setElapsed(response.elapsed_ms)
        setHealth((h) => (h ? { ...h, fixture_count: response.fixture_count } : h))
      }
      setPending(null)
    } catch (e) {
      // 실패한 응답은 채택하지 않는다. 재시도는 요청 전체의 스냅샷과 같은 ID를 쓴다.
      setError(e instanceof Error ? e.message : '연결에 실패했어요.')
      setPending(request)
    } finally {
      finish()
    }
  }
  const send = (text: string) => {
    if (locked) return
    void execute({
      source: 'chat',
      body: structuredClone({
        ...session,
        current_message: { id: crypto.randomUUID(), role: 'user', text },
        reference_date: referenceDate,
        timezone: 'Asia/Seoul',
      }),
    })
  }
  const generate = () => {
    if (locked || !ready) return
    void execute({
      source: 'button',
      body: structuredClone({
        ...session,
        request_id: crypto.randomUUID(),
        reference_date: referenceDate,
        timezone: 'Asia/Seoul',
      }),
    })
  }
  const cancelRetry = () => {
    if (pending?.source === 'chat') {
      const id = pending.body.current_message.id
      setMessages((previous) => previous.filter((m) => m.id !== id))
    }
    setPending(null)
    setError('')
  }
  const loadRecords = async () => {
    if (pending || !health || !begin('records')) return
    try {
      const result = await testApi<{ fixture_count: number }>('records', {})
      setHealth((h) => (h ? { ...h, fixture_count: result.fixture_count } : h))
      setNotice(`샘플 기록 ${result.fixture_count}종을 준비했어요. 과거 행사에 관해 물어보세요.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '기록 준비에 실패했어요.')
    } finally {
      finish()
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-h1">행사 계획</h1>
          <p className="mt-1 text-mute">
            {view === 'chat'
              ? '토리와 편하게 이야기하며 계획을 잡아보세요. 정한 내용은 오른쪽에 모입니다.'
              : '준비할 일과 순서를 확인해 보세요. 저장되지 않는 검토용 초안이에요.'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {view === 'preview' && (
            <Button variant="secondary" disabled={busy} onClick={() => setView('chat')}>
              대화로 돌아가기
            </Button>
          )}
          {view === 'chat' && generation.preview && (
            <Button variant="secondary" disabled={busy} onClick={() => setView('preview')}>
              마지막 초안 보기
            </Button>
          )}
          <Button variant="secondary" disabled={busy} onClick={reset}>
            새 대화
          </Button>
        </div>
      </header>
      <Card className="flex flex-wrap items-center gap-3 border-blue-200 bg-blue-50/40 p-4 text-caption text-blue-800">
        <span className="font-bold">AI 전용 계획 테스트</span>
        <span>브라우저 임시 상태 · 새로고침 시 초기화 · 저장 없음</span>
        {health && (
          <span>
            모델 <code>{health.model}</code>
          </span>
        )}
        <label className="ml-auto flex items-center gap-1">
          날짜 기준
          <input
            type="date"
            aria-label="질문 기준 날짜"
            disabled={busy || !!pending}
            value={referenceDate}
            onChange={(e) => setReferenceDate(e.target.value)}
            className="rounded border border-line bg-card px-2 py-1"
          />
        </label>
        <Button
          variant="secondary"
          size="sm"
          disabled={busy || !!pending || !health || (health.fixture_count ?? 0) > 0}
          onClick={() => void loadRecords()}
        >
          {health?.fixture_count ? `샘플 ${health.fixture_count}종 준비됨` : '샘플 기록 준비'}
        </Button>
      </Card>
      {error && (
        <Card className="flex flex-wrap items-center gap-3 border-failed/30 p-4">
          <p role="alert" className="flex-1 text-caption text-failed">
            {error}
          </p>
          {pending ? (
            <>
              <Button disabled={busy} onClick={() => void execute(pending)}>
                같은 요청 재시도
              </Button>
              <Button variant="secondary" disabled={busy} onClick={cancelRetry}>
                요청 취소
              </Button>
            </>
          ) : (
            !health && (
              <Button disabled={busy} onClick={() => void reconnect()}>
                연결 다시 확인
              </Button>
            )
          )}
        </Card>
      )}
      {notice && (
        <p role="status" className="text-caption text-blue-700">
          {notice}
        </p>
      )}
      {historyUsage?.near_limit && (
        <Card role="status" className="border-amber-200 bg-amber-50 p-4 text-caption">
          대화가 길어지고 있어요. 현재 정한 내용을 확인해 주세요.
        </Card>
      )}
      {history.length > 60 && (
        <p className="text-caption text-failed">
          대화 이력 한도에 도달했어요. 새 대화로 테스트해 주세요.
        </p>
      )}
      {work === 'button' ? (
        <Card
          className="flex min-h-72 flex-col items-center justify-center gap-4 p-8"
          aria-live="polite"
        >
          <span className="size-8 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600" />
          <h2 role="status" className="text-h2">
            계획 초안을 만들고 있어요…
          </h2>
          <p className="text-caption text-mute">
            정한 조건으로 준비 순서를 구성하고 있어요. 기존 조건과 초안은 유지됩니다.
          </p>
        </Card>
      ) : view === 'preview' && generation.preview ? (
        <>
          <div className="flex justify-end">
            <Button disabled={locked || !ready} onClick={generate}>
              현재 조건으로 다시 만들기
            </Button>
          </div>
          <AgentPlanPreview preview={generation.preview} current={current} />
        </>
      ) : (
        <div className="flex flex-col items-start gap-5 lg:flex-row">
          <PlanChat
            key={dialogKey}
            messages={messages}
            onSend={send}
            busy={busy}
            disabled={!health || !!pending || history.length > 60}
            busyLabel={
              work === 'records'
                ? '샘플 기록을 준비하고 있어요…'
                : work === 'connect'
                  ? 'AI 연결을 확인하고 있어요…'
                  : '토리가 요청을 처리하고 있어요…'
            }
            placeholder="자유롭게 이야기해 주세요"
          />
          <aside className="flex w-full flex-col gap-4 lg:w-[360px] lg:shrink-0">
            <PlanFacts
              wide
              facts={toAgentFacts(draft)}
              showProgress={false}
              readyOverride={ready && !locked}
              onNext={generate}
              nextHint={
                generation.condition_change_pending
                  ? '반영하지 못한 조건 변경을 대화에서 먼저 확인해 주세요.'
                  : !draft.conditions.event_type
                    ? '어떤 행사인지 정하면 초안을 만들 수 있어요.'
                    : '날짜와 장소는 미정이어도 괜찮아요. 현재 조건으로 검토할 초안을 만듭니다.'
              }
            />
            <Card className="flex flex-col gap-3 p-5">
              <h2 className="text-h3">계획 메모</h2>
              <p className="text-caption text-ink2">
                잠정은 일단 생각해둔 기준이에요. 대화하면서 바꿀 수 있어요.
              </p>
              <p className="text-caption text-mute">
                {draft.deferred_topics.length
                  ? `나중에 정할 내용: ${draft.deferred_topics.map((topic) => TOPIC_LABELS[topic] ?? topic).join(', ')}`
                  : '보류해 둔 내용은 아직 없어요.'}
              </p>
              {generation.offer?.status === 'deferred' && (
                <p className="text-caption text-ink2">
                  초안 만들기를 잠시 미뤘어요. 원할 때 대화로 요청하거나 다음 버튼을 누를 수 있어요.
                </p>
              )}
              {generation.preview && !current && (
                <p className="text-caption text-failed">
                  이전 초안과 현재 조건이 달라요. 필요하면 다시 만들어 주세요.
                </p>
              )}
              {draft.conditions.budget_total != null && (
                <p className="flex items-center gap-2 text-caption">
                  예산 상한: {draft.conditions.budget_total.toLocaleString()}원
                  {draft.condition_meta.budget_total?.status === 'tentative' && (
                    <Chip tone="pending" size="sm">
                      잠정
                    </Chip>
                  )}
                </p>
              )}
            </Card>
            <AgentReferences lookup={reference} />
          </aside>
        </div>
      )}
      <details className="rounded-xl border border-line bg-card p-4 text-caption">
        <summary className="cursor-pointer text-mute">
          처리 흐름 보기 · {elapsed == null ? '대기' : `${(elapsed / 1000).toFixed(2)}초`}
        </summary>
        {stats && (
          <div className="mt-3 flex flex-col gap-2">
            <p>
              대화 모델 {stats.agent}회 · 생성 모델 {stats.generation}회 · Tool 요청{' '}
              {stats.executions.length}회
            </p>
            {stats.executions.map((execution) => (
              <div key={execution.tool_call_id} className="rounded bg-bg p-2">
                <p>
                  {execution.name} · {executionLabels[execution.result.status]}
                </p>
                {execution.result.reason && <p>{execution.result.reason}</p>}
              </div>
            ))}
            {stats.limited && <p>이번 턴의 Tool 실행 한도에 도달했어요.</p>}
          </div>
        )}
        <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-all">
          {JSON.stringify(
            debug && typeof debug === 'object'
              ? {
                  ...debug,
                  last_user_message: latestUserMessage(history),
                  last_chat_tool_calls: latestToolCalls(history),
                }
              : debug,
            null,
            2,
          )}
        </pre>
      </details>
    </div>
  )
}
