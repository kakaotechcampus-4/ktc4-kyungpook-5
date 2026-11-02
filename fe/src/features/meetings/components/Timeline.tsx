import { useState } from 'react'
import { Card } from '@/shared/ui/Card'
import { Button } from '@/shared/ui/Button'
import { Tori } from '@/shared/ui/Tori'
import { reconcileTimeline, transcriptTime } from '../timeline'
import { useDecisionJobs } from '../hooks'
import type { Decision, Transcript } from '../types'
const str = (value: unknown) => (typeof value === 'string' ? value : '')
function TranscriptText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const content = text.trim() || '(알아듣지 못했어요)'
  const lines = content.split('\n')
  const preview = Array.from(lines.slice(0, 3).join('\n')).slice(0, 160).join('')
  const long = lines.length > 3 || Array.from(content).length > 160
  return (
    <>
      <p className="mt-2 whitespace-pre-wrap break-words leading-7">
        {expanded || !long ? content : `${preview}…`}
      </p>
      {long && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
          className="mt-2 text-caption font-semibold text-blue-700 underline underline-offset-4"
        >
          {expanded ? '접기' : '전체 보기'}
        </button>
      )}
    </>
  )
}
export function Timeline({
  transcripts,
  decisions,
  startedAt,
  onRefresh,
}: {
  transcripts: Transcript[]
  decisions: Decision[]
  startedAt?: string | null
  onRefresh: () => void
}) {
  const visibleEntries = reconcileTimeline([], transcripts, decisions)
  const jobs = useDecisionJobs(transcripts)
  return (
    <div className="space-y-4" aria-label="확정 전사 타임라인" role="log">
      {visibleEntries.map((entry) => {
        if (entry.type === 'transcript') {
          const t = transcripts.find((t) => t.id === entry.id)!
          return (
            <article
              key={`t:${t.id}`}
              className="rounded-lg border border-line bg-card px-4 py-4 sm:px-5"
            >
              <time className="text-caption text-mute">{transcriptTime(t, startedAt)}</time>
              <TranscriptText text={t.text} />
            </article>
          )
        }
        const d = decisions.find((d) => d.id === entry.id)!
        return (
          <article
            key={`d:${d.id}`}
            className="ml-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-4 sm:ml-6 sm:px-5"
          >
            <div className="flex items-center gap-2 text-caption font-bold text-blue-700">
              <Tori size={24} />
              <span>토리 · 자료 답변</span>
            </div>
            <p className="mt-2 whitespace-pre-wrap leading-6">
              {d.kind === 'NOT_FOUND'
                ? '기록에 없음 · 등록된 자료에서 답을 찾지 못했어요.'
                : d.output || '답변 내용이 없습니다.'}
            </p>
            {!!d.citations?.length && (
              <ul className="mt-3 space-y-2" aria-label="답변 출처">
                {d.citations.map((c, i) => (
                  <li key={i} className="rounded-lg bg-card p-3 text-caption">
                    <strong className="break-words">
                      {str(c.fileName) || str(c.title) || '등록 자료'}
                    </strong>
                    <p>{str((c.location as Record<string, unknown> | null)?.label)}</p>
                    <p className="mt-1 whitespace-pre-wrap break-words text-ink2">{str(c.text)}</p>
                  </li>
                ))}
              </ul>
            )}
          </article>
        )
      })}
      {jobs.map((job, index) =>
        job.data?.status === 'FAILED' ? (
          <Card key={index} className="border-failed-line p-4">
            <p className="text-failed">
              {JSON.stringify(job.data.error?.features ?? []).includes('meeting.lookup')
                ? '찾지 못했어요 · 자료 조회 도구에 오류가 생겼습니다.'
                : JSON.stringify(job.data.error?.features ?? []).includes('tasks.extract')
                  ? '일정·할 일 후보 추출에 오류가 생겼습니다. 자료 답변과 전사는 확인할 수 있습니다.'
                  : '자료 조회 또는 후보 추출 처리가 완료되지 않았습니다.'}
            </p>
            <Button
              className="mt-3"
              variant="secondary"
              onClick={() => {
                void job.refetch()
                onRefresh()
              }}
            >
              상태 다시 확인
            </Button>
          </Card>
        ) : null,
      )}
      {!visibleEntries.length && (
        <Card className="p-8 text-center text-mute">
          확정된 전사가 여기에 쌓입니다. 자료 답변과 일정·할 일 후보는 처리된 뒤 표시됩니다.
        </Card>
      )}
    </div>
  )
}
