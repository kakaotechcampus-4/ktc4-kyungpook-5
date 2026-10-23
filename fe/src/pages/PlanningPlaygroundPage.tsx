import { useEffect, useState } from 'react'
import { PlanChat } from '@/features/planning/components/PlanChat'
import { PlanFacts } from '@/features/planning/components/PlanFacts'
import type { ChatMessage } from '@/features/planning/types'
import { testApi, toAgentFacts, TOPIC_LABELS } from '@/features/planning/agent-playground'
import type { AgentDraft, AgentHealth, AgentResult } from '@/features/planning/agent-playground'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'

const greeting: ChatMessage = {
  id: 'hello',
  from: '토리',
  text: '안녕하세요! 어떤 행사를 준비하고 계세요? 아직 정하지 못한 부분도 같이 생각해봐요.',
  quickReplies: ['MT', '워크숍', '신환회'],
}
const emptyDraft: AgentDraft = { conditions: {}, condition_meta: {}, deferred_topics: [] }
const executionLabels = { applied: '반영', unchanged: '유지', rejected: '미반영' }

async function connect() {
  const health = await testApi<AgentHealth>('health')
  if (!health.agent_version)
    throw new Error('새 Agent API를 사용하려면 AI 테스트 서버를 재시작해 주세요.')
  return health
}

export default function PlanningPlaygroundPage() {
  const [dialogKey, setDialogKey] = useState(() => crypto.randomUUID())
  const [messages, setMessages] = useState<ChatMessage[]>([greeting])
  const [last, setLast] = useState<AgentResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [retryRequest, setRetryRequest] = useState<{ id: string; text: string } | null>(null)
  const [health, setHealth] = useState<AgentHealth | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [referenceDate, setReferenceDate] = useState(() =>
    new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' }),
  )
  // 하나의 성공 응답에서 초안과 Tool 이력을 함께 채택한다. 말풍선에서 값을 추출하지 않는다.
  const draft = last?.draft ?? emptyDraft
  const history = last?.history ?? []

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

  const reconnect = async () => {
    setBusy(true)
    setError('')
    try {
      setHealth(await connect())
    } catch (e) {
      setError(e instanceof Error ? e.message : '연결에 실패했어요.')
    } finally {
      setBusy(false)
    }
  }

  const reset = () => {
    setDialogKey(crypto.randomUUID())
    setMessages([greeting])
    setLast(null)
    setError('')
    setRetryRequest(null)
    setElapsed(null)
  }

  const send = async (text: string, retry = false) => {
    if (busy || !health || (retryRequest && !retry)) return
    if (history.length > 60) {
      setError('대화 이력 한도에 도달했어요. 새 대화로 테스트해 주세요.')
      return
    }
    setBusy(true)
    setError('')
    const id = retry && retryRequest ? retryRequest.id : crypto.randomUUID()
    if (!retry) setMessages((previous) => [...previous, { id, from: '나', text }])
    try {
      const response = await testApi<{ result: AgentResult; elapsed_ms: number }>('agent/turn', {
        draft,
        history,
        current_message: { id, role: 'user', text },
        reference_date: referenceDate,
        timezone: 'Asia/Seoul',
      })
      setLast(response.result)
      setElapsed(response.elapsed_ms)
      setMessages((previous) => [
        ...previous,
        {
          id: `${id}-reply`,
          from: '토리',
          text: response.result.reply,
        },
      ])
      setRetryRequest(null)
    } catch (e) {
      // 실패한 응답은 초안·이력에 반영하지 않는다. 재시도는 같은 말풍선·메시지 ID를 사용한다.
      setError(e instanceof Error ? e.message : '연결에 실패했어요.')
      setRetryRequest({ id, text })
    } finally {
      setBusy(false)
    }
  }

  const budget = draft.conditions.budget_total
  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-h1">행사 계획</h1>
          <p className="mt-1 text-mute">
            토리와 편하게 이야기하며 계획을 잡아보세요. 정한 내용은 오른쪽에 모입니다.
          </p>
        </div>
        <Button variant="secondary" disabled={busy} onClick={reset}>
          새 대화
        </Button>
      </header>
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-caption text-blue-700">
        <span className="font-bold">FE · AI 대화 테스트</span>
        <span>브라우저 임시 상태 · 새로고침 시 초기화 · 저장 없음</span>
        <span>{health ? `모델 ${health.model}` : 'AI 연결 확인 중'}</span>
        <label>
          날짜 기준{' '}
          <input
            aria-label="상대 날짜 기준"
            className="rounded border border-blue-200 bg-card px-2 py-1"
            type="date"
            value={referenceDate}
            disabled={busy || history.length > 0}
            onChange={(e) => setReferenceDate(e.target.value)}
          />
        </label>
      </div>
      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-xl bg-failed-bg p-4 text-failed"
        >
          <span>{error}</span>
          {retryRequest ? (
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() => void send(retryRequest.text, true)}
            >
              같은 요청 다시 보내기
            </Button>
          ) : !health ? (
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => void reconnect()}>
              연결 다시 확인
            </Button>
          ) : null}
        </div>
      )}
      {history.length > 60 && (
        <p role="alert" className="text-caption text-failed">
          대화 이력 한도에 도달했어요. 새 대화로 테스트해 주세요.
        </p>
      )}
      <div className="flex flex-col items-start gap-5 lg:flex-row">
        <PlanChat
          key={dialogKey}
          messages={messages}
          onSend={(text) => void send(text)}
          busy={busy}
          disabled={!health || !!retryRequest || history.length > 60}
          busyLabel="토리가 이야기를 읽고 있어요…"
          placeholder="자유롭게 이야기해 주세요"
        />
        <aside className="flex w-full flex-col gap-4 lg:w-[360px] lg:shrink-0">
          <PlanFacts
            wide
            facts={toAgentFacts(draft)}
            showProgress={false}
            showNext={false}
            onNext={() => {}}
          />
          {error && last && (
            <p className="text-caption text-failed">
              오른쪽에는 마지막으로 성공한 요청의 조건을 표시하고 있어요.
            </p>
          )}
          <Card className="flex flex-col gap-3 p-5">
            <h2 className="text-h3">계획 메모</h2>
            <p className="text-caption text-ink2">
              잠정은 일단 생각해둔 기준이에요. 대화하면서 바꿀 수 있어요.
            </p>
            {draft.deferred_topics.length > 0 ? (
              <p className="text-caption text-ink2">
                나중에 정할 내용:{' '}
                {draft.deferred_topics.map((topic) => TOPIC_LABELS[topic] ?? topic).join(', ')}
              </p>
            ) : (
              <p className="text-caption text-mute">보류해 둔 내용은 아직 없어요.</p>
            )}
            {budget != null && (
              <p className="flex items-center gap-2 text-caption">
                예산 상한: {budget.toLocaleString()}원
                {draft.condition_meta.budget_total?.status === 'tentative' && (
                  <Chip tone="pending" size="sm">
                    잠정
                  </Chip>
                )}
              </p>
            )}
          </Card>
          <details className="rounded-xl border border-line bg-card p-4 text-caption">
            <summary className="cursor-pointer text-mute">
              처리 흐름 보기 · {elapsed == null ? '대기' : `${(elapsed / 1000).toFixed(2)}초`}
            </summary>
            {last && (
              <div className="mt-3 flex flex-col gap-2">
                <p>
                  모델 판단·답변 {last.model_calls}회 · Tool 요청 {last.executions.length}회
                </p>
                {last.executions.length === 0 && <p>Tool 없이 대화로 답했어요.</p>}
                {last.executions.map((execution) => (
                  <div key={execution.tool_call_id} className="rounded bg-bg p-2">
                    <p>
                      {execution.name} · {executionLabels[execution.result.status]}
                    </p>
                    {execution.result.reason && <p>{execution.result.reason}</p>}
                  </div>
                ))}
                {last.limit_reached && <p>이번 턴의 Tool 실행 한도에 도달했어요.</p>}
              </div>
            )}
            <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-all">
              {JSON.stringify(last, null, 2)}
            </pre>
          </details>
        </aside>
      </div>
    </div>
  )
}
