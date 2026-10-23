import { useEffect, useState } from 'react'
import { PlanChat } from '@/features/planning/components/PlanChat'
import { PlanFacts } from '@/features/planning/components/PlanFacts'
import type { ChatMessage } from '@/features/planning/types'
import { testApi, toFacts } from '@/features/planning/playground'
import type { Conditions, Fact, QuestionState, TurnResult } from '@/features/planning/playground'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'

const greeting: ChatMessage = {
  id: 'hello',
  from: '토리',
  text: '안녕하세요! 어떤 행사를 준비하시나요?',
  quickReplies: ['MT', '워크숍', '신환회'],
}
const reasons: Record<string, string> = {
  MISSING_EVENT_TYPE: '행사 종류를 알려 주세요.',
  CONDITION_CONFLICT: '충돌한 조건을 확인해 주세요.',
  PENDING_MODIFICATION: '아직 답을 기다리는 수정 요청이 있어요.',
}
type ContextMessage = { id: string; role: 'user' | 'assistant'; text: string }

function SourceFact({ fact }: { fact: Fact }) {
  return (
    <div className="flex flex-col gap-1 border-b border-blue-200 pb-3 last:border-0 last:pb-0">
      <p className="whitespace-pre-wrap text-body text-ink2">{fact.content}</p>
      {fact.sources.map((s) => (
        <span key={`${s.record_id}:${s.location.label}`} className="text-caption text-mute">
          {s.file_name} · {s.location.label}
        </span>
      ))}
    </div>
  )
}

export default function PlanningPlaygroundPage() {
  const [eventId, setEventId] = useState(() => `play-${crypto.randomUUID()}`)
  const [messages, setMessages] = useState<ChatMessage[]>([greeting])
  const [context, setContext] = useState<ContextMessage[]>([])
  const [conditions, setConditions] = useState<Conditions>({})
  const [questionState, setQuestionState] = useState<QuestionState>({ event_id: eventId })
  const [pending, setPending] = useState<unknown[]>([])
  const [version, setVersion] = useState(0)
  const [last, setLast] = useState<TurnResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [retryText, setRetryText] = useState('')
  const [health, setHealth] = useState<{ model: string; fixture_count: number } | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [notice, setNotice] = useState('')
  const [referenceDate, setReferenceDate] = useState(() =>
    new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' }),
  )

  useEffect(() => {
    let active = true
    testApi<{ model: string; fixture_count: number }>('health')
      .then((h) => {
        if (active) setHealth(h)
      })
      .catch(() => {
        if (active) setError('AI 테스트 서버가 연결되지 않았어요. 실행 방법을 확인해 주세요.')
      })
    return () => {
      active = false
    }
  }, [])

  const reset = () => {
    const id = `play-${crypto.randomUUID()}`
    setEventId(id)
    setMessages([greeting])
    setContext([])
    setConditions({})
    setQuestionState({ event_id: id })
    setPending([])
    setVersion(0)
    setLast(null)
    setError('')
    setRetryText('')
    setElapsed(null)
    setNotice('')
  }

  const send = async (text: string, retry = false) => {
    if (busy) return
    if (
      context.length > 20 ||
      context.reduce((sum, m) => sum + m.text.length, text.length) > 40000
    ) {
      setError('AI 입력 문맥 한도에 도달했어요. 새 대화로 테스트해 주세요.')
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    const id = crypto.randomUUID()
    if (!retry) setMessages((previous) => [...previous, { id, from: '나', text }])
    try {
      // 화면의 임시 상태를 매번 전달한다. 성공한 결과만 다음 턴의 기준으로 채택한다.
      const response = await testApi<{
        result: TurnResult
        elapsed_ms: number
        fixture_count: number
      }>('turn', {
        club_id: 'clb_keunnamu',
        question_state: questionState,
        pending_clarifications: pending,
        extraction_input: {
          event_id: eventId,
          request_id: id,
          base_version: version,
          conditions,
          current_message: { id, role: 'user', text },
          context_messages: context,
          reference_date: referenceDate,
          timezone: 'Asia/Seoul',
        },
      })
      const result = response.result
      setConditions(result.collected)
      setQuestionState(result.next_question_state)
      setPending(result.pending_clarifications)
      setLast(result)
      setElapsed(response.elapsed_ms)
      setHealth((current) =>
        current ? { ...current, fixture_count: response.fixture_count } : current,
      )
      setContext((previous) => [
        ...previous,
        { id, role: 'user', text },
        { id: `${id}-reply`, role: 'assistant', text: result.reply },
      ])
      setMessages((previous) => [
        ...previous,
        {
          id: `${id}-reply`,
          from: '토리',
          text: result.reply,
          quickReplies: result.question?.quick_replies,
        },
      ])
      setVersion((v) => v + 1)
      setRetryText('')
    } catch (e) {
      setError(e instanceof Error ? e.message : '연결에 실패했어요.')
      setRetryText(text)
    } finally {
      setBusy(false)
    }
  }

  const loadRecords = async () => {
    setBusy(true)
    setError('')
    setNotice('샘플 기록을 준비하고 있어요…')
    try {
      const result = await testApi<{ fixture_count: number }>('records', {})
      const current = await testApi<{ model: string; fixture_count: number }>('health')
      setHealth(current)
      setNotice(`샘플 기록 ${result.fixture_count}종을 준비했어요. 과거 행사 내용을 물어보세요.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '기록 준비에 실패했어요.')
      setNotice('')
    } finally {
      setBusy(false)
    }
  }
  const found = last?.record_lookup.result
  const hint = last?.readiness.ready_to_generate
    ? 'AI는 현재 조건으로 초안을 만들 수 있다고 판단했어요.'
    : last?.readiness.reasons.map((r) => reasons[r] ?? r).join(' ') ||
      '어떤 종류의 행사인지 먼저 알려 주세요.'

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-h1">행사 계획</h1>
          <p className="mt-1 text-mute">
            토리와 대화하면서 큰 틀을 잡습니다. 정해진 건 오른쪽에 쌓입니다.
          </p>
        </div>
        <Button variant="secondary" disabled={busy} onClick={reset}>
          새 대화
        </Button>
      </header>
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-caption text-blue-700">
        <span className="font-bold">FE · AI 테스트</span>
        <span>브라우저 임시 상태 · 새로고침 시 초기화 · 저장 없음</span>
        <span>{health ? `모델 ${health.model}` : 'AI 연결 확인 중'}</span>
        <label>
          날짜 기준{' '}
          <input
            aria-label="상대 날짜 기준"
            className="rounded border border-blue-200 bg-card px-2 py-1"
            type="date"
            value={referenceDate}
            disabled={busy || context.length > 0}
            onChange={(e) => setReferenceDate(e.target.value)}
          />
        </label>
        <Button
          size="sm"
          variant="secondary"
          disabled={busy || !!health?.fixture_count}
          onClick={() => void loadRecords()}
        >
          {health?.fixture_count ? `샘플 ${health.fixture_count}종 준비됨` : '샘플 기록 준비'}
        </Button>
      </div>
      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-xl bg-failed-bg p-4 text-failed"
        >
          <span>{error}</span>
          {retryText && (
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() => void send(retryText, true)}
            >
              같은 요청 다시 보내기
            </Button>
          )}
        </div>
      )}
      {notice && (
        <p role="status" className="text-caption text-blue-700">
          {notice}
        </p>
      )}
      <div className="flex flex-col items-start gap-5 lg:flex-row">
        <PlanChat
          key={eventId}
          messages={messages}
          onSend={(text) => void send(text)}
          busy={busy}
        />
        <aside className="flex w-full flex-col gap-4 lg:w-[360px] lg:shrink-0">
          <PlanFacts
            wide
            facts={toFacts(conditions)}
            readyOverride={!busy && !error && !!last?.readiness.ready_to_generate}
            nextLabel="초안 생성 가능 여부 확인"
            nextHint={
              error
                ? '최근 요청이 실패해 이전 조건을 표시하고 있어요. 재시도하거나 새 대화로 시작해 주세요.'
                : hint
            }
            onNext={() =>
              setNotice('초안 생성 가능 상태입니다. 이 테스트는 P1 채팅까지만 연결되어 있어요.')
            }
          />
          <Card className="flex flex-col gap-3 border-blue-200 bg-blue-50 p-5">
            <h2 className="text-h3 text-blue-700">참고한 과거 기록</h2>
            {!last || last.record_lookup.status === 'SKIPPED' ? (
              <p className="text-caption text-ink2">
                아직 조회하지 않았어요.{' '}
                {health?.fixture_count
                  ? '“작년 봄 MT 장소는?”처럼 물어보세요.'
                  : '샘플 기록을 준비하면 합성 기록에서 조회할 수 있어요.'}
              </p>
            ) : null}
            {last?.record_lookup.status === 'FAILED' && (
              <p className="text-caption text-failed">검색에 실패했어요. 현재 조건은 유지됩니다.</p>
            )}
            {last?.record_lookup.status === 'NEEDS_CLARIFICATION' && (
              <p className="text-caption">조회할 대상을 확인하고 있어요.</p>
            )}
            {found?.cards.map((fact, i) => (
              <SourceFact key={i} fact={fact} />
            ))}
            {found?.conflicts.map((conflict, i) => (
              <div key={i} className="flex flex-col gap-2">
                <p className="font-bold text-pending">자료 차이: {conflict.description}</p>
                {conflict.values.map((fact, j) => (
                  <SourceFact key={j} fact={fact} />
                ))}
              </div>
            ))}
            {!!found?.not_found.length && (
              <p className="text-caption text-ink2">
                이번 검색에서 미확인: {found.not_found.join(', ')}
              </p>
            )}
            {last && last.record_lookup.status !== 'SKIPPED' && (
              <span className="text-label text-mute">마지막 성공 요청의 조회 결과</span>
            )}
          </Card>
          <details className="rounded-xl border border-line bg-card p-4 text-caption">
            <summary className="cursor-pointer text-mute">
              개발 확인용 응답 · {elapsed == null ? '대기' : `${(elapsed / 1000).toFixed(2)}초`}
            </summary>
            <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-all">
              {JSON.stringify(last, null, 2)}
            </pre>
          </details>
        </aside>
      </div>
    </div>
  )
}
