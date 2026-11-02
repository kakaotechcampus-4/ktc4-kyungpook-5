import { Link } from 'react-router-dom'
import { Card } from '@/shared/ui/Card'
import { Tori } from '@/shared/ui/Tori'
import { useDecisionJobs } from '../hooks'
import { meetingAnswers, meetingMicStatus, sourceOf, transcriptTime } from '../timeline'
import type { AudioPhase } from '../audio/useMeetingAudio'
import type { Decision, Meeting, Transcript } from '../types'

const value = (input: unknown) => (typeof input === 'string' ? input : '')

export function MeetingToriPanel({
  meeting,
  phase,
  audioActive,
  transcripts,
  decisions,
  loading,
  error,
  onRefresh,
}: {
  meeting: Meeting
  phase: AudioPhase
  audioActive: boolean
  transcripts: Transcript[]
  decisions: Decision[]
  loading: boolean
  error: boolean
  onRefresh: () => void
}) {
  const answers = meetingAnswers(transcripts, decisions)
  const jobs = useDecisionJobs(transcripts)
  const latest = transcripts
    .filter((item) => item.final)
    .sort(
      (a, b) => b.seq - a.seq || b.createdAt.localeCompare(a.createdAt) || b.id.localeCompare(a.id),
    )[0]
  const jobTranscripts = transcripts.filter((item) => item.final && item.decisionJobId)
  const latestJob = latest?.decisionJobId
    ? jobs[jobTranscripts.findIndex((item) => item.id === latest.id)]
    : undefined
  const latestNoLookup =
    latest &&
    decisions.some(
      (decision) =>
        decision.kind === 'NO_LOOKUP' &&
        decision.status === 'SUCCEEDED' &&
        sourceOf(decision, transcripts)?.id === latest.id,
    )
  const latestProcessing =
    latestJob &&
    !latestJob.isError &&
    (!latestJob.data || latestJob.data.status === 'QUEUED' || latestJob.data.status === 'RUNNING')
  const processing = jobs.some(
    (job) => job.data?.status === 'QUEUED' || job.data?.status === 'RUNNING',
  )
  const failed = jobs.some((job) => job.data?.status === 'FAILED' || job.isError)
  return (
    <Card className="flex h-[320px] min-w-0 flex-col p-5 sm:h-[340px]">
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-line pb-3">
        <div className="flex min-w-0 items-center gap-3">
          <Tori size={40} />
          <div className="min-w-0">
            <h2 className="text-h2">회의를 함께 듣는 토리</h2>
            <p className="mt-1 text-caption text-ink2" role="status">
              {meetingMicStatus(meeting.status, phase)}
            </p>
          </div>
        </div>
        {!audioActive ? (
          <Link
            className="shrink-0 text-caption font-semibold text-blue-700 underline underline-offset-4"
            to="/meetings"
          >
            다른 회의 보기
          </Link>
        ) : (
          <span className="shrink-0 text-caption text-mute">마이크 종료와 처리 후 회의 이동</span>
        )}
      </div>
      <div
        className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain pt-4"
        role="region"
        aria-label="토리의 회의 자료 답변"
        tabIndex={0}
      >
        {error && (
          <p role="alert" className="text-caption text-failed">
            전사 또는 자료 답변을 갱신하지 못했어요.{' '}
            <button className="underline" onClick={onRefresh}>
              다시 확인
            </button>
          </p>
        )}
        {latestProcessing && latest && (
          <p role="status" className="text-caption text-ink2">
            최근 발화 ({transcriptTime(latest, meeting.startedAt)})를 처리하고 있어요.
          </p>
        )}
        {!latestProcessing && latestNoLookup && latest && (
          <p className="text-caption text-mute">
            최근 발화 ({transcriptTime(latest, meeting.startedAt)})는 자료 검색 없이 처리됐어요.
          </p>
        )}
        {processing && !latestProcessing && (
          <p role="status" className="text-caption text-ink2">
            들은 내용을 처리하고 있어요.
          </p>
        )}
        {failed && (
          <p role="alert" className="text-caption text-failed">
            일부 발화의 처리를 확인하지 못했어요.{' '}
            <button
              className="underline"
              onClick={() => {
                jobs.forEach((job) => void job.refetch())
                onRefresh()
              }}
            >
              상태 다시 확인
            </button>
          </p>
        )}
        {loading && !answers.length && (
          <p role="status" className="text-caption text-mute">
            회의 내용을 불러오고 있어요.
          </p>
        )}
        {!loading && !answers.length && !error && (
          <p className="text-caption leading-6 text-mute">
            자료 답변이 생기면 질문과 함께 여기에 표시돼요.
          </p>
        )}
        {answers.map(({ decision, transcript }) => (
          <article key={decision.id} className="border-b border-line pb-4 last:border-0">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <p className="min-w-0 whitespace-pre-wrap break-words text-caption font-semibold text-ink2">
                원 발화 · {transcript.text.trim() || '(알아듣지 못했어요)'}
              </p>
              <time className="shrink-0 text-caption text-mute">
                {transcriptTime(transcript, meeting.startedAt)}
              </time>
            </div>
            <p className="mt-2 whitespace-pre-wrap break-words leading-6">
              {decision.kind === 'NOT_FOUND'
                ? '검색한 자료에서 답을 확인하지 못했어요.'
                : decision.output || '답변 내용이 없습니다.'}
            </p>
            {decision.status === 'PARTIAL' && (
              <p className="mt-2 text-caption text-failed">
                일부 처리가 완료되지 않았어요. 아래 전사와 후보 상태를 확인해 주세요.
              </p>
            )}
            {!!decision.citations?.length && (
              <ul className="mt-2 space-y-1" aria-label="답변 출처">
                {decision.citations.map((citation, i) => (
                  <li className="text-caption text-mute" key={i}>
                    출처 · {value(citation.fileName) || value(citation.title) || '등록 자료'}{' '}
                    {value((citation.location as Record<string, unknown> | null)?.label)}
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))}
      </div>
    </Card>
  )
}
