import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Tori } from '@/shared/ui/Tori'
import { cn } from '@/shared/lib/cn'
import {
  askedAgo,
  lookupFailed,
  sourceOf,
  toriResults,
  transcriptTime,
  utteranceAt,
  type ToriResult,
} from '../timeline'
import type { Decision, Transcript } from '../types'

const str = (value: unknown) => (typeof value === 'string' ? value : '')

// memo: the workspace re-renders on every microphone level update while recording.
export const TranscriptColumn = memo(function TranscriptColumn({
  transcripts,
  decisions,
  startedAt,
  live,
  countLabel,
  className,
}: {
  transcripts: Transcript[]
  decisions: Decision[]
  startedAt?: string | null
  live: boolean
  countLabel?: string
  className?: string
}) {
  const items = useMemo(
    () => transcripts.filter((t) => t.final).sort((a, b) => a.seq - b.seq),
    [transcripts],
  )
  // Lines Tori looked up (answered or failed) get the side bar.
  const answeredIds = useMemo(
    () =>
      new Set(
        decisions.flatMap((decision) => {
          const source = decision.kind === 'NO_LOOKUP' ? undefined : sourceOf(decision, transcripts)
          return source ? [source.id] : []
        }),
      ),
    [decisions, transcripts],
  )
  const scroller = useRef<HTMLDivElement>(null)
  // Follow new lines only while the reader is at the bottom.
  const pinned = useRef(true)
  useEffect(() => {
    const element = scroller.current
    if (element && pinned.current) element.scrollTop = element.scrollHeight
  }, [items.length])
  return (
    <Card className={cn('flex min-h-0 flex-col', className)}>
      <div className="flex items-baseline gap-2 border-b border-line px-6 py-5">
        <h2 className="text-h2">들은 말</h2>
        {countLabel && <span className="text-caption text-ink2">{countLabel}</span>}
      </div>
      <div
        ref={scroller}
        role="log"
        aria-label="들은 말"
        tabIndex={0}
        onScroll={(event) => {
          const element = event.currentTarget
          pinned.current = element.scrollHeight - element.scrollTop - element.clientHeight < 40
        }}
        className="min-h-0 flex-1 overflow-y-auto px-6 py-4 focus-visible:outline-2 focus-visible:outline-blue-600"
      >
        {!items.length && (
          <p className="text-caption text-mute">아직 들은 말이 없어요. 말하면 여기에 적혀요.</p>
        )}
        <ol className="space-y-3">
          {items.map((transcript, index) => {
            const text = transcript.text.trim()
            return (
              <li
                key={transcript.id}
                className={cn(
                  'flex gap-3 border-l-[3px] pl-3',
                  answeredIds.has(transcript.id) ? 'border-blue-400' : 'border-transparent',
                )}
              >
                <time className="w-11 shrink-0 pt-px text-caption font-medium text-ink2">
                  {transcriptTime(transcript, startedAt)}
                </time>
                <p
                  className={cn(
                    'min-w-0 whitespace-pre-wrap break-words leading-6',
                    !text && 'text-mute',
                    live && text && index === items.length - 1 && 'font-bold',
                  )}
                >
                  {text || '(알아듣지 못했어요)'}
                </p>
              </li>
            )
          })}
        </ol>
      </div>
    </Card>
  )
})

function KindChip({ item }: { item: ToriResult }) {
  if (lookupFailed(item.decision)) return <Chip tone="failed">찾지 못함</Chip>
  if (item.decision.route === 'LLM' && item.decision.citations?.some((c) => str(c.type) === 'web')) {
    return <Chip tone="done">웹 검색</Chip>
  }
  if (item.decision.kind === 'NOT_FOUND') return <Chip>기록에 없음</Chip>
  return <Chip tone="done">찾음</Chip>
}

function summary(item: ToriResult) {
  if (lookupFailed(item.decision)) return '찾지 못했어요. 조회가 실패했어요.'
  return (
    item.decision.output?.trim().split('\n')[0] ||
    (item.decision.kind === 'NOT_FOUND' ? '기록에서 찾지 못했어요.' : '답변 내용이 없어요.')
  )
}

function AnswerCard({
  item,
  startedAt,
  ongoing,
  now,
  isNew,
  onClose,
  onRetry,
}: {
  item: ToriResult
  startedAt?: string | null
  ongoing: boolean
  now: number
  isNew: boolean
  onClose?: () => void
  onRetry: () => void
}) {
  const { transcript } = item
  const failed = lookupFailed(item.decision)
  // judgment.question is the search query; when lookup failed there is none, so show the utterance.
  const question = failed ? '' : item.decision.question?.trim()
  const asked = `${transcriptTime(transcript, startedAt)}에 ${question ? '물은 것' : '나온 말'}${
    ongoing ? ` · ${askedAgo(utteranceAt(transcript, startedAt), now)}` : ''
  }`
  const citations = failed ? [] : (item.decision.citations ?? [])
  return (
    <article
      className={cn(
        'rounded-[12px] border p-6',
        failed
          ? 'border-failed-line bg-card'
          : isNew
            ? 'border-2 border-blue-600 bg-blue-50'
            : 'border-blue-200 bg-blue-50',
      )}
    >
      <div className="flex items-center gap-3">
        <Tori size={40} />
        <span className="text-caption font-bold text-blue-700">토리</span>
        <KindChip item={item} />
        {isNew && (
          <span className="rounded-[8px] bg-blue-600 px-[11px] py-[6px] text-[11.5px] font-bold text-white">
            새 답
          </span>
        )}
        {onClose && (
          <button
            type="button"
            aria-label="이 답 닫기"
            onClick={onClose}
            className="ml-auto rounded-[8px] px-2 py-1 text-ink2 hover:bg-card"
          >
            ✕
          </button>
        )}
      </div>
      <div className="mt-4 border-l-[3px] border-soft pl-3">
        <p className="text-caption font-medium text-ink2">{asked}</p>
        <p className="mt-0.5 break-words">
          {question || transcript.text.trim() || '(알아듣지 못했어요)'}
        </p>
      </div>
      {failed ? (
        <>
          <p className="mt-4 text-[22px] leading-8 font-bold text-failed">
            찾지 못했어요. 기록이 없는 게 아니라 조회가 실패했어요.
          </p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 text-caption font-bold text-blue-700"
          >
            상태 다시 확인 ›
          </button>
        </>
      ) : (
        <>
          <p className="mt-4 text-[22px] leading-8 font-bold whitespace-pre-wrap break-words">
            {item.decision.output?.trim() || summary(item)}
          </p>
          {item.decision.kind === 'NOT_FOUND' && (
            <p className="mt-3 text-caption text-ink2">자료는 자료함에서 올릴 수 있어요.</p>
          )}
          {item.decision.status === 'PARTIAL' && (
            <p className="mt-3 text-caption text-failed">일부 처리가 끝나지 않았어요.</p>
          )}
          {citations.length > 0 && (
            <ul aria-label="답변 출처" className="mt-4 space-y-2">
              {citations.map((citation, index) => (
                <li key={index} className="rounded-[10px] bg-card px-4 py-3 text-caption">
                  <p className="font-medium break-words text-blue-700">
                    {[
                      str(citation.fileName) || str(citation.title) || '등록 자료',
                      str((citation.location as Record<string, unknown> | null)?.label),
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                      {str(citation.url) && (
                        <a
                          className="mt-0.5 block break-all text-blue-700 underline"
                          href={str(citation.url)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          출처 열기
                        </a>
                      )}
                  {str(citation.text) && (
                    <p className="mt-0.5 break-words text-ink2">“{str(citation.text)}”</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </article>
  )
}

export const ToriColumn = memo(function ToriColumn({
  transcripts,
  decisions,
  startedAt,
  ongoing,
  now,
  loading,
  error,
  onRefresh,
  className,
}: {
  transcripts: Transcript[]
  decisions: Decision[]
  startedAt?: string | null
  // 회의가 아직 끝나지 않았다. 끝나면 답을 발화 순서로 보이고 '새 답'과 닫기를 숨긴다.
  ongoing: boolean
  now: number
  loading: boolean
  error: boolean
  onRefresh: () => void
  className?: string
}) {
  const items = useMemo(
    () => toriResults(transcripts, decisions, ongoing ? 'arrival' : 'seq'),
    [transcripts, decisions, ongoing],
  )
  const [dismissed, setDismissed] = useState<string[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)
  // Answers already present when the screen opened are not announced as new.
  const seen = useRef<Set<string> | null>(null)
  if (seen.current === null && !loading)
    seen.current = new Set(items.map((item) => item.decision.id))
  const visible = items.filter((item) => !dismissed.includes(item.decision.id))
  const [latest, ...rest] = visible
  const isNew =
    ongoing &&
    !!latest &&
    !!seen.current &&
    !seen.current.has(latest.decision.id) &&
    now - Date.parse(latest.decision.createdAt) < 60_000
  return (
    <Card className={cn('flex min-h-0 flex-col', className)}>
      <div className="flex items-baseline gap-2 border-b border-line px-6 py-5">
        <h2 className="text-h2">토리가 찾은 것</h2>
        {!ongoing && items.length > 0 && (
          <span className="text-caption text-ink2">이 회의에서 토리가 답한 {items.length}건</span>
        )}
      </div>
      {/* Announce only a newly arrived answer, not every minute's "N분 전" change. */}
      <p role="status" className="sr-only">
        {isNew && latest ? `토리가 새 답을 찾았어요. ${summary(latest)}` : ''}
      </p>
      <div
        role="region"
        aria-label="토리가 찾은 것"
        tabIndex={0}
        className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-5 focus-visible:outline-2 focus-visible:outline-blue-600"
      >
        {error && (
          <p role="alert" className="text-caption text-failed">
            들은 말이나 토리 답을 새로 불러오지 못했어요.{' '}
            <button type="button" className="font-bold underline" onClick={onRefresh}>
              다시 불러오기
            </button>
          </p>
        )}
        {loading && !items.length && (
          <p role="status" className="text-caption text-mute">
            회의 내용을 불러오고 있어요.
          </p>
        )}
        {!loading && !visible.length && (
          <p className="text-caption leading-6 text-mute">
            기록에서 찾을 만한 말이 나오면 토리가 찾아서 여기에 보여 줘요.
          </p>
        )}
        {latest && (
          <AnswerCard
            item={latest}
            startedAt={startedAt}
            ongoing={ongoing}
            now={now}
            isNew={isNew}
            onClose={
              ongoing ? () => setDismissed((ids) => [...ids, latest.decision.id]) : undefined
            }
            onRetry={onRefresh}
          />
        )}
        {rest.length > 0 && (
          <section aria-label={ongoing ? '지난 답' : '다른 답'}>
            <h3 className="mb-1 text-caption font-bold">
              {ongoing ? '지난 답' : `다른 답 ${rest.length}`}
            </h3>
            <ul className="border-t border-line">
              {rest.map((item) => {
                const id = item.decision.id
                const open = expanded === id
                return (
                  <li key={id} className="border-b border-line">
                    <button
                      type="button"
                      aria-expanded={open}
                      onClick={() => setExpanded(open ? null : id)}
                      className="flex w-full items-center gap-3 px-1 py-3 text-left hover:bg-bg"
                    >
                      <span className="w-11 shrink-0 text-caption text-ink2">
                        {transcriptTime(item.transcript, startedAt)}
                      </span>
                      <span
                        className={cn(
                          'min-w-0 flex-1 truncate',
                          item.decision.kind === 'NOT_FOUND' && 'text-mute',
                          lookupFailed(item.decision) && 'text-failed',
                        )}
                      >
                        {summary(item)}
                      </span>
                      <span aria-hidden className="text-ink2">
                        {open ? '⌄' : '›'}
                      </span>
                    </button>
                    {open && (
                      <div className="pb-3">
                        <AnswerCard
                          item={item}
                          startedAt={startedAt}
                          ongoing={ongoing}
                          now={now}
                          isNew={false}
                          onRetry={onRefresh}
                        />
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>
        )}
      </div>
    </Card>
  )
})
