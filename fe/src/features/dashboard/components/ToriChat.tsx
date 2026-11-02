import { useId, useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { dashboardApi } from '@/features/dashboard/api'
import type { components } from '@/shared/api/schema'
import { ApiError } from '@/shared/api/types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Textarea } from '@/shared/ui/Input'
import { Tori } from '@/shared/ui/Tori'

type Result = components['schemas']['ToriMessageOut']
type Turn = { id: string; message: string; result: Result }
const formatTime = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul',
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(value))
    : '시간 미정'
const examples = [
  '지난 회의의 할 일을 확인하고 싶어요',
  '행사 예산 관련 자료를 찾아줘',
  '새 회의를 시작할게요',
]

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
  const [pending, setPending] = useState<{ turnId: string; originalQuestion: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const locked = useRef(false)
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
  const send = async (text: string) => {
    const message = text.trim()
    if (!clubId || !message || locked.current) return
    locked.current = true
    if (turns.length === 0) onConversationStarted?.()
    setBusy(true)
    setError('')
    setDraft(message)
    try {
      const result = await dashboardApi.message(clubId, {
        message,
        ...(pending
          ? { clarificationContext: { originalQuestion: pending.originalQuestion } }
          : {}),
      })
      const id = crypto.randomUUID()
      setTurns((items) => [...items, { id, message, result }])
      if (pending && result.recordAnswer?.status === 'failed') return
      setPending(
        result.clarification
          ? { turnId: id, originalQuestion: pending?.originalQuestion ?? message }
          : null,
      )
      setDraft('')
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.code === 'AI_MISCONFIGURED'
          ? '토리 대화 설정을 확인하고 있어요. 잠시 후 다시 시도해 주세요.'
          : '답변을 가져오지 못했어요. 연결을 확인하고 다시 시도해 주세요.',
      )
    } finally {
      locked.current = false
      setBusy(false)
    }
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
        <div className="space-y-3 pb-4">
          <p className="ml-auto w-fit max-w-[90%] whitespace-pre-wrap break-words rounded-xl bg-blue-900 px-4 py-3 text-[14px] leading-6 text-white">
            {draft}
          </p>
          <p role="status" className="text-caption text-ink2">
            토리가 확인하고 있어요…
          </p>
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
      <form
        className="shrink-0 space-y-2 rounded-xl border border-soft bg-bg p-4"
        onSubmit={submit}
      >
        {pending && (
          <div className="flex items-center justify-between gap-3 text-caption text-ink2">
            <span>이어서 답하기</span>
            <button
              type="button"
              className="text-blue-700 underline"
              disabled={busy}
              onClick={() => {
                setPending(null)
                setError('')
              }}
            >
              새 질문하기
            </button>
          </div>
        )}
        <Textarea
          label="토리에게 질문"
          className="min-h-[72px] bg-card text-[16px] sm:text-[14px]"
          rows={2}
          maxLength={1000}
          disabled={!clubId || busy}
          placeholder={clubId ? '궁금한 내용을 입력해 주세요' : '로그인하고 소속을 선택해 주세요'}
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
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-caption text-mute">
            Enter로 전송 · Shift+Enter로 줄바꿈
            <br />
            대화는 새로고침하면 사라져요.
          </p>
          <Button type="submit" disabled={!clubId || busy || !draft.trim()}>
            {busy ? '확인 중…' : '보내기'}
          </Button>
        </div>
      </form>
    </Card>
  )
}
