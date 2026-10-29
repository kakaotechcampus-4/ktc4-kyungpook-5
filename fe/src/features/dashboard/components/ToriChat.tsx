import { useRef, useState, type FormEvent } from 'react'
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
  return (
    <div className="space-y-3 rounded-xl bg-bg p-4 text-caption leading-6">
      <p className="whitespace-pre-wrap">{result.reply}</p>
      {result.records && (
        <div className="space-y-3">
          <p>
            자료 {result.recordTotalCount ?? 0}건{' '}
            {result.recordTotalCount && result.recordTotalCount > result.records.items.length
              ? `중 ${result.records.items.length}건 표시`
              : ''}
          </p>
          {result.records.semanticStatus === 'UNAVAILABLE' && (
            <p role="alert" className="text-failed">
              AI 추천을 불러오지 못해 파일명과 본문 일치 결과만 표시해요.
            </p>
          )}
          {result.records.semanticStatus === 'NO_INDEXED_RECORDS' && (
            <p className="text-mute">
              AI 검색 준비가 된 자료가 없어 파일명과 읽은 본문만 검색했어요.
            </p>
          )}
          {result.records.unindexedCount > 0 && (
            <p className="text-mute">
              {result.records.unindexedCount}개 자료는 AI 검색 준비 전이에요.
            </p>
          )}
          {result.records.semanticStatus === 'AVAILABLE' && (
            <p className="text-mute">
              AI 추천은 상위 {result.records.semanticCandidateLimit}개 청크를 바탕으로 한 후보예요.
            </p>
          )}
          {result.records.items.map((item) => (
            <div key={item.id} className="space-y-2 rounded-lg border border-line bg-card p-3">
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
                      setDownloadError('원본을 받지 못했어요. 권한과 파일 상태를 확인해 주세요.'),
                    )
                    .finally(() => setDownloading(null))
                }}
              >
                {downloading === item.id ? '받는 중…' : '원본 다운로드'}
              </Button>
            </div>
          ))}
          {downloadError && (
            <p role="alert" className="text-failed">
              {downloadError}
            </p>
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
export function ToriChat({ clubId }: { clubId: string | null }) {
  const [draft, setDraft] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const locked = useRef(false)
  const send = async (text: string) => {
    const message = text.trim()
    if (!clubId || !message || locked.current) return
    locked.current = true
    setBusy(true)
    setError('')
    setDraft(message)
    try {
      const result = await dashboardApi.message(clubId, message)
      setTurns((items) => [...items, { id: crypto.randomUUID(), message, result }])
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
    <Card className="flex min-h-[460px] flex-col p-5 sm:p-7">
      <div className="flex items-start gap-4">
        <Tori size={48} />
        <div>
          <h2 className="text-h2">무엇을 도와드릴까요?</h2>
          <p className="mt-2 text-caption leading-6 text-ink2">
            자료와 확인된 할 일을 찾고 회의나 행사 계획을 시작해요.
          </p>
        </div>
      </div>
      <div className="my-5 flex flex-wrap gap-2">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            disabled={!clubId || busy}
            onClick={() => void send(example)}
            className="rounded-xl border border-soft px-3 py-2 text-left text-caption hover:bg-bg disabled:opacity-50"
          >
            {example}
          </button>
        ))}
      </div>
      <div aria-live="polite" className="space-y-4 pb-5">
        {turns.map((turn) => (
          <div key={turn.id} className="space-y-2">
            <p className="ml-auto w-fit max-w-[85%] whitespace-pre-wrap rounded-xl bg-blue-600 p-3 text-caption text-white">
              {turn.message}
            </p>
            <Reply result={turn.result} />
          </div>
        ))}
      </div>
      {busy && (
        <p role="status" className="pb-3 text-caption text-mute">
          토리가 확인하고 있어요…
        </p>
      )}
      {error && (
        <p role="alert" className="pb-3 text-caption text-failed">
          {error}
        </p>
      )}
      <form className="mt-auto space-y-2 border-t border-line pt-4" onSubmit={submit}>
        <Textarea
          label="토리에게 질문"
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
        <p className="text-caption text-mute">
          Enter로 전송 · Shift+Enter로 줄바꿈 · 대화는 새로고침하면 사라져요.
        </p>
        <Button type="submit" disabled={!clubId || busy || !draft.trim()}>
          보내기
        </Button>
      </form>
    </Card>
  )
}
