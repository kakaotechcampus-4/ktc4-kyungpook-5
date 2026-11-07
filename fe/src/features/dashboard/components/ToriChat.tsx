import { useEffect, useId, useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { dashboardApi } from '@/features/dashboard/api'
import type { components } from '@/shared/api/schema'
import { ApiError } from '@/shared/api/types'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ChatComposer } from '@/shared/ui/ChatComposer'
import { Tori } from '@/shared/ui/Tori'

type Result = components['schemas']['ToriMessageOut']
type Turn = { id: string; message: string; result: Result }
type PendingClarification = {
  turnId: string
  originalQuestion: string
  question: string
  options: string[]
}
type QueuedMessage = {
  message: string
  clarification: PendingClarification | null
}
const formatTime = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul',
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(value))
    : '시간 미정'
// 질문 한 번에 보낼 수 있는 글자 수.
const MAX_QUESTION = 1000

const examples = [
  '지난 회의의 할 일을 확인하고 싶어요',
  '행사 예산 관련 자료를 찾아줘',
  '새 회의를 시작할게요',
]

function elapsedLabel(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function ThinkingStatus({ message }: { message: string }) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [])
  return (
    <div className="space-y-3 rounded-xl border border-line bg-bg px-4 py-4" role="status">
      <div className="flex items-start gap-3">
        <Tori size={36} thinking />
        <div className="min-w-0 space-y-1">
          <p className="font-semibold text-ink">토리가 답변을 만들고 있어요</p>
          <p className="text-caption leading-5 text-ink2">
            자료와 확정된 할 일을 확인하고 있어요. 답변이 준비되면 바로 보여드릴게요.
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2" aria-hidden>
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="size-[6px] animate-pulse rounded-full bg-blue-300"
            style={{ animationDelay: `${index * 0.25}s` }}
          />
        ))}
        <span className="text-caption text-mute">확인 중</span>
      </div>
      <p className="text-caption tabular-nums text-mute" aria-live="off">
        {elapsedLabel(seconds)} · 요청을 처리하고 있어요
      </p>
      <div className="rounded-lg border border-soft bg-card px-3 py-2">
        <p className="text-[11px] font-semibold text-mute">확인 중인 질문</p>
        <p className="mt-1 whitespace-pre-wrap break-words text-caption text-ink2">{message}</p>
      </div>
    </div>
  )
}

function Reply({ result }: { result: Result }) {
  const [downloadError, setDownloadError] = useState('')
  const [downloading, setDownloading] = useState<string | null>(null)
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [selectedSources, setSelectedSources] = useState<number[]>([])
  const sourceListId = useId()
  const answer = result.recordAnswer
  const sourceItems = [
    ...(answer?.facts ?? []),
    ...(answer?.conflicts ?? []).flatMap((item) => item.values),
  ].flatMap((item) => item.sources)
  const sources = Array.from(
    new Map(
      sourceItems.map((source) => [
        JSON.stringify([source.recordId, source.location?.label]),
        source,
      ]),
    ).values(),
  )
  const sourceNumbers = (items: typeof sources) => [
    ...new Set(
      items.map(
        (source) =>
          sources.findIndex(
            (item) =>
              item.recordId === source.recordId && item.location?.label === source.location?.label,
          ) + 1,
      ),
    ),
  ]
  const references = (items: typeof sources) => {
    const numbers = sourceNumbers(items)
    return (
      <button
        type="button"
        className="ml-2 text-caption font-semibold text-blue-700 underline"
        onClick={() => {
          setSelectedSources(numbers)
          setSourcesOpen(true)
          requestAnimationFrame(() =>
            document.getElementById(sourceListId)?.scrollIntoView({ block: 'nearest' }),
          )
        }}
        aria-label={`출처 ${numbers.join(', ')} 보기`}
      >
        [{numbers.slice(0, 3).join(', ')}
        {numbers.length > 3 ? ` 외 ${numbers.length - 3}곳` : ''}]
      </button>
    )
  }
  return (
    <div className="min-w-0 space-y-4 text-[14px] leading-6">
      <p role={answer?.status === 'failed' ? 'alert' : undefined} className="whitespace-pre-wrap">
        {result.reply}
      </p>
      {answer && (
        <div className="space-y-3">
          {answer.facts?.map((fact, index) => (
            <p key={index} className="whitespace-pre-wrap break-words">
              {fact.text}
              {references(fact.sources)}
            </p>
          ))}
          {answer.conflicts?.map((conflict, index) => (
            <div key={index} className="space-y-1">
              <p className="font-semibold">자료 간 내용이 달라요: {conflict.description}</p>
              {conflict.values.map((value, valueIndex) => (
                <p key={valueIndex} className="break-words">
                  {value.text}
                  {references(value.sources)}
                </p>
              ))}
            </div>
          ))}
          {sources.length > 0 && (
            <details
              id={sourceListId}
              open={sourcesOpen}
              onToggle={(event) => setSourcesOpen(event.currentTarget.open)}
              className="border-t border-line pt-2"
            >
              <summary className="cursor-pointer text-caption font-semibold text-blue-700">
                답변 출처 {sources.length}곳
              </summary>
              <ol className="mt-2 space-y-2">
                {sources.map((source, index) => (
                  <li
                    key={JSON.stringify([source.recordId, source.location?.label])}
                    className="text-caption"
                  >
                    <span className="break-all">
                      [{index + 1}] {source.fileName}
                    </span>{' '}
                    · {source.location?.label ?? '위치 정보 없음'}{' '}
                    {selectedSources.includes(index + 1) && (
                      <span className="font-semibold text-blue-700">이 내용의 출처 · </span>
                    )}
                    <button
                      type="button"
                      className="text-blue-700 underline"
                      disabled={!!downloading}
                      onClick={() => {
                        setDownloading(source.recordId)
                        setDownloadError('')
                        void dashboardApi
                          .download(source.recordId, source.fileName)
                          .catch(() =>
                            setDownloadError(
                              '원본을 받지 못했어요. 권한과 파일 상태를 확인해 주세요.',
                            ),
                          )
                          .finally(() => setDownloading(null))
                      }}
                    >
                      {downloading === source.recordId ? '받는 중…' : '원본 다운로드'}
                    </button>
                  </li>
                ))}
              </ol>
            </details>
          )}
          {(answer.status !== 'answered' ||
            answer.semanticStatus !== 'AVAILABLE' ||
            answer.unindexedCount > 0 ||
            answer.candidateLimitReached ||
            answer.lexicalOmitted ||
            answer.filenameOnlyUnanalyzedCount > 0 ||
            !!answer.notFound?.length) && (
            <details className="text-caption text-ink2">
              <summary className="cursor-pointer font-semibold">답변 확인 사항</summary>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {answer.status === 'partial' && <li>일부 내용만 확인했어요.</li>}
                {answer.status === 'insufficient' && (
                  <li>검색된 자료만으로는 답을 확인하기 어려워요.</li>
                )}
                {answer.status === 'failed' && <li>자료를 바탕으로 답변을 만들지 못했어요.</li>}
                {answer.semanticStatus === 'UNAVAILABLE' && (
                  <li>답변을 위한 AI 검색을 사용할 수 없었어요.</li>
                )}
                {answer.semanticStatus === 'NO_INDEXED_RECORDS' && (
                  <li>AI 색인이 준비된 자료가 없어요.</li>
                )}
                {answer.unindexedCount > 0 && (
                  <li>AI 색인이 준비되지 않은 자료가 {answer.unindexedCount}개 있어요.</li>
                )}
                {answer.candidateLimitReached && <li>검색 후보 한도에 도달했어요.</li>}
                {answer.lexicalOmitted && (
                  <li>일치하는 본문 중 일부를 답변에 사용하지 못했어요.</li>
                )}
                {answer.filenameOnlyUnanalyzedCount > 0 && (
                  <li>
                    파일명으로 찾은 자료 중 {answer.filenameOnlyUnanalyzedCount}개는 답변 분석에
                    포함되지 않았어요. 원본을 확인해 주세요.
                  </li>
                )}
                {answer.notFound?.map((item, index) => (
                  <li key={index}>확인하지 못한 내용: {item}</li>
                ))}
              </ul>
            </details>
          )}
          {answer.semanticStatus === 'UNAVAILABLE' && (
            <p role="alert" className="text-caption text-failed">
              AI 검색을 사용할 수 없어 답변이 제한될 수 있어요.
            </p>
          )}
        </div>
      )}
      {downloadError && (
        <p role="alert" className="text-failed">
          {downloadError}
        </p>
      )}
      {result.records && (
        <div className="space-y-3">
          <p className="border-t border-line pt-4 text-caption font-semibold text-ink2">
            검색된 자료 {result.recordTotalCount ?? 0}건{' '}
            {result.recordTotalCount && result.recordTotalCount > result.records.items.length
              ? `중 ${result.records.items.length}건 표시`
              : ''}
          </p>
          {result.records.semanticStatus === 'UNAVAILABLE' &&
            answer?.semanticStatus !== 'UNAVAILABLE' && (
              <p
                role="alert"
                className="rounded-lg border border-failed-line bg-failed-bg px-3 py-2 text-failed"
              >
                AI 추천을 불러오지 못해 파일명과 본문 일치 결과만 표시해요.
              </p>
            )}
          {!answer && result.records.semanticStatus === 'NO_INDEXED_RECORDS' && (
            <p className="rounded-lg bg-bg px-3 py-2 text-ink2">
              AI 검색 준비가 된 자료가 없어 파일명과 읽은 본문만 검색했어요.
            </p>
          )}
          {!answer && result.records.unindexedCount > 0 && (
            <p className="text-mute">
              {result.records.unindexedCount}개 자료는 AI 검색 준비 전이에요.
            </p>
          )}
          {!answer && result.records.semanticStatus === 'AVAILABLE' && (
            <p className="text-mute">
              AI 추천은 상위 {result.records.semanticCandidateLimit}개 청크를 바탕으로 한 후보예요.
            </p>
          )}
          {result.records.items.length === 0 ? (
            <p className="text-mute">
              {result.records.semanticStatus === 'UNAVAILABLE'
                ? '파일명과 본문 일치 결과가 없어요. AI 추천은 확인하지 못했어요.'
                : result.records.semanticStatus === 'NO_INDEXED_RECORDS'
                  ? '파일명과 본문 일치 결과가 없어요. AI 검색 준비가 된 자료는 없어요.'
                  : '검색 조건에 맞는 자료를 찾지 못했어요.'}
            </p>
          ) : (
            <details className="rounded-lg border border-line bg-card p-3">
              <summary className="cursor-pointer font-semibold">
                검색된 자료 보기 ({result.records.items.length}건)
              </summary>
              <div className="mt-3 space-y-3">
                {result.records.items.map((item) => (
                  <div
                    key={item.id}
                    className="space-y-2 rounded-lg border border-line bg-card p-4"
                  >
                    <p className="break-all font-bold">{item.fileName}</p>
                    <p className="text-mute">
                      {item.matchTypes
                        .map((type) =>
                          type === 'SEMANTIC'
                            ? 'AI 추천'
                            : type === 'CONTENT'
                              ? '본문 일치'
                              : '파일명 일치',
                        )
                        .join(' · ')}
                    </p>
                    {item.excerpts.map((excerpt, index) => (
                      <p key={index} className="whitespace-pre-wrap break-words">
                        {excerpt.text}
                        <span className="block text-mute">
                          {excerpt.location?.label ?? '위치 정보 없음'}
                        </span>
                      </p>
                    ))}
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={!!downloading}
                      onClick={() => {
                        setDownloading(item.id)
                        setDownloadError('')
                        void dashboardApi
                          .download(item.id, item.fileName)
                          .catch(() =>
                            setDownloadError(
                              '원본을 받지 못했어요. 권한과 파일 상태를 확인해 주세요.',
                            ),
                          )
                          .finally(() => setDownloading(null))
                      }}
                    >
                      {downloading === item.id ? '받는 중…' : '원본 다운로드'}
                    </Button>
                  </div>
                ))}
              </div>
            </details>
          )}
          <Link className="text-blue-700 underline" to="/records">
            자료함에서 검색하기
          </Link>
        </div>
      )}
      {result.tasks && (
        <div className="space-y-2">
          <p>
            {result.tasks.scope === 'self' ? '내 계정에 배정된' : '팀의'}{' '}
            {result.tasks.kind === 'schedule'
              ? '일정'
              : result.tasks.kind === 'task'
                ? '할 일'
                : '일정과 할 일'}{' '}
            · {result.tasks.dateFrom ?? '처음'} ~ {result.tasks.dateTo ?? '전체'} · 한국시간
          </p>
          {result.tasks.items.length ? (
            <ul className="space-y-2">
              {result.tasks.items.map((item) => (
                <li key={item.id} className="rounded-lg bg-card p-2">
                  <strong>{item.title}</strong>
                  <span className="block text-mute">
                    {item.kind === 'SCHEDULE' ? '일정' : '할 일'} ·{' '}
                    {item.assigneeName ?? '담당자 미정'} ·{' '}
                    {formatTime(item.kind === 'SCHEDULE' ? item.scheduledAt : item.dueAt)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p>해당하는 확정 항목이 없어요.</p>
          )}
          {result.tasks.hasMore && <p>최대 20건을 표시했어요.</p>}
          <Link className="text-blue-700 underline" to="/meetings">
            회의에서 확인하기
          </Link>
        </div>
      )}
      {result.navigation && (
        <Link className="inline-block font-bold text-blue-700 underline" to={result.navigation}>
          {result.navigation === '/meetings' ? '회의 화면으로 이동' : '행사 계획으로 이동'}
        </Link>
      )}
    </div>
  )
}
export function ToriChat({
  clubId,
  onConversationStarted,
}: {
  clubId: string | null
  onConversationStarted?: () => void
}) {
  const [draft, setDraft] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [pending, setPending] = useState<{
    turnId: string
    originalQuestion: string
    question: string
    options: string[]
  } | null>(null)
  const [busy, setBusy] = useState(false)
  const [activeQuestion, setActiveQuestion] = useState('')
  const [queuedQuestions, setQueuedQuestions] = useState<string[]>([])
  const [error, setError] = useState('')
  const queue = useRef<QueuedMessage[]>([])
  const processing = useRef(false)
  const pendingRef = useRef<PendingClarification | null>(null)
  const conversationStarted = useRef(false)
  const conversation = useRef<HTMLDivElement>(null)
  const latestReply = useRef<HTMLDivElement>(null)
  const followLatest = useRef(true)
  const [hasUnseenReply, setHasUnseenReply] = useState(false)

  useLayoutEffect(() => {
    const element = conversation.current
    if (!element || !turns.length) return
    if (followLatest.current) {
      const reply = latestReply.current
      if (reply && reply.offsetHeight > element.clientHeight) {
        element.scrollTop += reply.getBoundingClientRect().top - element.getBoundingClientRect().top
      } else {
        element.scrollTop = element.scrollHeight
      }
    } else {
      setHasUnseenReply(true)
    }
  }, [turns])
  pendingRef.current = pending

  const processQueue = async () => {
    if (!clubId || processing.current) return
    processing.current = true
    setBusy(true)
    try {
      while (queue.current.length > 0) {
        const item = queue.current.shift()
        if (!item) break
        setQueuedQuestions(queue.current.map(({ message }) => message))
        setActiveQuestion(item.message)
        setError('')
        try {
          const result = await dashboardApi.message(clubId, {
            message: item.message,
            ...(item.clarification
              ? {
                  clarificationContext: {
                    originalQuestion: item.clarification.originalQuestion,
                    question: item.clarification.question,
                    options: item.clarification.options,
                  },
                }
              : {}),
          })
          const id = crypto.randomUUID()
          setTurns((items) => [...items, { id, message: item.message, result }])
          if (item.clarification && result.recordAnswer?.status === 'failed') continue
          const nextPending = result.clarification
            ? {
                turnId: id,
                originalQuestion: result.clarification.originalQuestion,
                question: result.clarification.question,
                options: result.clarification.options ?? [],
              }
            : null
          pendingRef.current = nextPending
          setPending(nextPending)
        } catch (cause) {
          setError(
            cause instanceof ApiError && cause.code === 'AI_MISCONFIGURED'
              ? '토리 대화 설정을 확인하고 있어요. 잠시 후 다시 시도해 주세요.'
              : '답변을 가져오지 못했어요. 연결을 확인하고 다시 시도해 주세요.',
          )
        }
      }
    } finally {
      processing.current = false
      setBusy(false)
      setActiveQuestion('')
      setQueuedQuestions([])
    }
  }

  const send = (text: string) => {
    const message = text.trim()
    if (!clubId || !message) return
    if (!conversationStarted.current) {
      conversationStarted.current = true
      onConversationStarted?.()
    }
    queue.current.push({ message, clarification: pendingRef.current })
    setQueuedQuestions(queue.current.map(({ message: queuedMessage }) => queuedMessage))
    setDraft('')
    void processQueue()
  }
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void send(draft)
  }
  return (
    <Card className="flex h-[max(460px,calc(100dvh-180px))] min-w-0 flex-col overflow-hidden border-0 bg-transparent p-0 lg:h-full lg:min-h-0">
      <div className="flex shrink-0 items-start gap-4 border-b border-line pb-5">
        <Tori size={48} />
        <div>
          <p className="mb-1 text-caption text-ink2">토리가 함께할게요.</p>
          <h2 className="text-h2">무엇을 도와드릴까요?</h2>
          <p className="mt-2 text-caption leading-6 text-ink2">
            자료와 확인된 할 일을 찾고 회의나 행사 계획을 시작해요.
          </p>
        </div>
      </div>
      {turns.length === 0 && !busy && (
        <div className="mt-5 flex flex-wrap gap-2">
          {examples.map((example) => (
            <button
              key={example}
              type="button"
              disabled={!clubId || busy}
              onClick={() => void send(example)}
              className="rounded-lg border border-soft px-3 py-2 text-left text-caption text-ink2 hover:bg-bg focus-visible:outline-2 disabled:opacity-50"
            >
              {example}
            </button>
          ))}
        </div>
      )}
      <div
        ref={conversation}
        aria-live="polite"
        aria-label="토리 대화 내용"
        tabIndex={0}
        onScroll={(event) => {
          const element = event.currentTarget
          const atBottom = element.scrollHeight - element.clientHeight - element.scrollTop < 24
          followLatest.current = atBottom
          if (atBottom) setHasUnseenReply(false)
        }}
        className="my-5 min-h-0 min-w-0 flex-1 space-y-5 overflow-y-auto overscroll-contain pr-1"
      >
        {turns.map((turn) => (
          <div key={turn.id} className="space-y-4">
            <p className="ml-auto w-fit max-w-[90%] whitespace-pre-wrap break-words rounded-xl bg-blue-900 px-4 py-3 text-[14px] leading-6 text-white sm:max-w-[80%]">
              {turn.message}
            </p>
            <div
              ref={turn.id === turns[turns.length - 1]?.id ? latestReply : undefined}
              className="flex min-w-0 items-start gap-3"
            >
              <Tori size={32} />
              <div className="min-w-0 flex-1 space-y-1">
                <p className="text-caption font-semibold text-ink2">토리</p>
                <Reply result={turn.result} />
                {turn.result.clarification && (
                  <div className="flex flex-wrap gap-2 pt-2">
                    {turn.result.clarification.options?.map((option) => (
                      <button
                        key={option}
                        type="button"
                        disabled={busy || pending?.turnId !== turn.id}
                        onClick={() => void send(option)}
                        className="rounded-lg border border-soft px-3 py-2 text-left text-caption text-blue-700 hover:bg-bg focus-visible:outline-2 disabled:opacity-50"
                      >
                        {option}
                      </button>
                    ))}
                    {!turn.result.clarification.options?.some(
                      (option) => option.replace(/\s/g, '') === '전체요약',
                    ) && (
                      <button
                        type="button"
                        disabled={busy || pending?.turnId !== turn.id}
                        onClick={() => void send('전체 요약')}
                        className="px-2 py-2 text-caption font-semibold text-blue-700 underline underline-offset-4 focus-visible:outline-2 disabled:opacity-50"
                      >
                        전체 요약
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      {hasUnseenReply && (
        <button
          type="button"
          className="mb-3 self-end text-caption font-semibold text-blue-700 underline"
          onClick={() => {
            const element = conversation.current
            if (element) element.scrollTop = element.scrollHeight
            followLatest.current = true
            setHasUnseenReply(false)
          }}
        >
          최신 답변 보기
        </button>
      )}
      {busy && (
        <div className="pb-4">
          <ThinkingStatus message={activeQuestion} />
        </div>
      )}
      {error && (
        <p
          role="alert"
          className="mb-3 rounded-lg border border-failed-line bg-failed-bg px-3 py-2 text-caption text-failed"
        >
          {error}
        </p>
      )}
      {/* 대시보드는 묻고 답을 받는 화면이라 입력 상자가 화면의 주 입력이다. 행사 계획 대화와
          같은 상자·보내기 버튼·단축키 말풍선을 쓰되, 두 줄 높이의 흰 상자로 띄운다. */}
      <form className="shrink-0 space-y-2" onSubmit={submit}>
        {pending && (
          <div className="flex items-center justify-between gap-3 px-1 text-caption text-ink2">
            <span>이어서 답하기</span>
            <button
              type="button"
              className="text-blue-700 underline"
              disabled={busy}
              onClick={() => {
                pendingRef.current = null
                setPending(null)
                setError('')
              }}
            >
              새 질문하기
            </button>
          </div>
        )}
        <ChatComposer
          tone="raised"
          minRows={2}
          maxRows={6}
          aria-label="토리에게 질문"
          maxLength={MAX_QUESTION}
          disabled={!clubId}
          placeholder={clubId ? '토리에게 물어보세요' : '로그인하고 소속을 선택해 주세요'}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key !== 'Enter' ||
              event.shiftKey ||
              event.altKey ||
              event.ctrlKey ||
              event.metaKey ||
              event.nativeEvent.isComposing ||
              event.keyCode === 229
            )
              return
            event.preventDefault()
            if (!event.repeat) event.currentTarget.form?.requestSubmit()
          }}
          // 답을 기다리는 동안에도 다음 질문을 받아 차례로 처리한다. 그래서 도는 표시 대신 그대로 둔다.
          sendLabel={busy ? '질문 추가' : '보내기'}
          sendDisabled={!clubId || !draft.trim()}
        />
        <div className="flex items-start justify-between gap-3 px-1 text-[12px] leading-[18px] text-mute">
          <p>
            {queuedQuestions.length > 0
              ? `질문 ${queuedQuestions.length}개가 순서대로 처리돼요.`
              : '대화는 새로고침하면 사라져요.'}
          </p>
          {/* 글자 수는 한도에 가까워질 때만 보인다. */}
          {draft.length >= MAX_QUESTION - 200 && (
            <p
              className={cn('shrink-0 tabular-nums', draft.length >= MAX_QUESTION && 'text-failed')}
            >
              {draft.length} / {MAX_QUESTION}자
            </p>
          )}
        </div>
      </form>
    </Card>
  )
}
