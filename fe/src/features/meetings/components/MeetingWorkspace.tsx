import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useBlocker, useLocation, useNavigate } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { useMeetingData } from '../hooks'
import { useMeetingAudio } from '../audio'
import { useRecordingLock } from '@/shared/lib/recordingLock'
import { MeetingList } from './MeetingList'
import { MeetingStart, type MeetingEventOption } from './MeetingStart'
import { MeetingBanner, MeetingHeader, StatusPill } from './MeetingHeader'
import { ToriColumn, TranscriptColumn } from './MeetingColumns'
import { meetingError } from '../errors'
import {
  clockTime,
  extractionFailed,
  meetingAnswers,
  meetingProcessingSteps,
  meetingView,
  recordedClock,
} from '../timeline'
import { CandidatesModal, ConfirmedTasks } from './Suggestions'
import { MeetingEnded } from './MeetingEnded'
import { EndMeetingModal, LeaveMeetingModal } from './MeetingConfirm'
const EMPTY: never[] = []
const SILENCE_MS = 10_000
// 입력이 사실상 0(음소거·고장)일 때만 알린다. 잡음 억제가 켜진 조용한 방도 0은 아니다.
const SILENT_LEVEL = 0.001

function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [active])
  return now
}

export function MeetingWorkspace({
  clubId,
  meetingId,
  highlightTaskId,
  events,
  notifications,
}: {
  clubId: string
  meetingId?: string
  highlightTaskId?: string
  events: MeetingEventOption[]
  notifications: ReactNode
}) {
  const location = useLocation()
  const navigate = useNavigate()
  const data = useMeetingData(clubId, meetingId)
  const meeting = data.meeting.data
  const [justEnded, setJustEnded] = useState(false)
  const [hiddenWarning, setHiddenWarning] = useState<string | null>(null)
  const [candidatesOpen, setCandidatesOpen] = useState(false)
  const [endOpen, setEndOpen] = useState(false)
  const audio = useMeetingAudio({
    meetingId: meetingId ?? '',
    onCompleted: () => setJustEnded(true),
    onRefresh: () => void data.refresh(),
  })
  const view = meeting ? meetingView(meeting.status, audio.phase, justEnded) : null
  const live = view === 'connecting' || view === 'recording' || view === 'paused'
  const now = useNow(live || view === 'finalizing' || view === 'stopped' || view === 'dropped')
  const [lastSoundAt, setLastSoundAt] = useState(() => Date.now())
  useEffect(() => setLastSoundAt(Date.now()), [audio.phase])
  useEffect(() => {
    if (audio.inputLevel <= SILENT_LEVEL) return
    const at = Date.now()
    // At most once a second, so speech does not add a render per level update.
    setLastSoundAt((previous) => (at - previous > 1000 ? at : previous))
  }, [audio.inputLevel])
  const transcripts = data.transcripts.data?.items ?? EMPTY
  const decisions = data.decisions.data ?? EMPTY
  const answers = useMemo(() => meetingAnswers(transcripts, decisions), [transcripts, decisions])
  const heard = transcripts.filter((t) => t.final).length
  const processingSteps = useMemo(
    () => meetingProcessingSteps({
      transcriptCount: heard,
      transcriptPending: data.transcripts.isPending,
      transcriptError: data.transcripts.isError,
      answerCount: answers.length,
      answerPending: data.decisions.isPending,
      answerError:
        data.decisions.isError ||
        decisions.some((d) => d.status !== 'STALE' && String(d.kind) === 'FAILED'),
      candidateCount: data.suggestions.length,
      candidateSavedCount: data.suggestions.filter((suggestion) => suggestion.status === 'ACCEPTED').length,
      candidatePending: data.suggestionsQuery.isPending,
      candidateError: data.suggestionsQuery.isError,
      extractionError: extractionFailed(decisions),
    }),
    [
      answers.length,
      data.decisions.isError,
      data.decisions.isPending,
      data.suggestions,
      data.suggestionsQuery.isError,
      data.suggestionsQuery.isPending,
      data.transcripts.isError,
      data.transcripts.isPending,
      decisions,
      heard,
    ],
  )

  // Leaving the page stops the microphone, so ask first (in-app links) or let the
  // browser warn (reload, tab close).
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      live && currentLocation.pathname !== nextLocation.pathname,
  )
  const guardUnload = live || view === 'finalizing'
  useEffect(() => {
    if (!guardUnload) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [guardUnload])
  // Switching club remounts this screen and would cut the recording without asking.
  const setRecording = useRecordingLock((state) => state.setRecording)
  useEffect(() => {
    setRecording(guardUnload)
    return () => setRecording(false)
  }, [guardUnload, setRecording])

  // The start card navigates here with autoStart; start, then drop the flag so a reload
  // never tries to restart a meeting that already has audio. No once-only ref: StrictMode
  // cancels the first start, and start() itself ignores a second call while busy.
  const autoStart = (location.state as { autoStart?: boolean } | null)?.autoStart === true
  const startAudio = audio.start
  useEffect(() => {
    if (!autoStart || meeting?.status !== 'RECORDING') return
    navigate(location.pathname, { replace: true })
    void startAudio()
  }, [autoStart, meeting?.status, navigate, location.pathname, startAudio])

  if (meeting && meeting.clubId !== clubId)
    return (
      <Card className="space-y-3 p-6">
        <h1 className="text-h2">다른 소속의 회의입니다.</h1>
        <p>회의의 소속을 확인한 뒤 열어 주세요.</p>
        <Link
          className="text-blue-700 underline"
          to={`/meetings/${encodeURIComponent(meeting.id)}?clubId=${encodeURIComponent(meeting.clubId)}`}
        >
          이 회의의 소속으로 열기
        </Link>
      </Card>
    )
  if (!meetingId)
    return (
      <div className="mx-auto max-w-[1040px] space-y-6">
        <h1 className="text-h1">회의</h1>
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] xl:grid-cols-[minmax(0,1fr)_400px]">
          <MeetingStart clubId={clubId} events={events} />
          <MeetingList clubId={clubId} />
        </div>
        <div className="grid items-start gap-6 border-t border-line pt-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] xl:grid-cols-[minmax(0,1fr)_400px]">
          <ConfirmedTasks clubId={clubId} highlightTaskId={highlightTaskId} />
          {notifications}
        </div>
      </div>
    )
  if (data.meeting.isError && !meeting)
    return (
      <div className="mx-auto max-w-[1240px]">
        <MeetingBanner
          tone="failed"
          title="회의를 열지 못했어요"
          action={
            <Button variant="secondary" size="sm" onClick={() => void data.refresh()}>
              다시 확인
            </Button>
          }
        >
          {meetingError(data.meeting.error)}
        </MeetingBanner>
      </div>
    )
  if (!meeting || !view)
    return (
      <p role="status" className="text-caption text-mute">
        회의를 불러오는 중이에요.
      </p>
    )

  const ended = view === 'ended' || view === 'record' || view === 'failed'
  const when = meeting.startedAt
    ? ended && meeting.endedAt
      ? `${clockTime(meeting.startedAt)} – ${clockTime(meeting.endedAt)}`
      : `${clockTime(meeting.startedAt)} 시작`
    : '시작 전'
  const meta = `${when} · 후보 ${data.suggestions.length}건 · 토리 ${answers.length}번`
  const candidates = (
    <CandidatesModal
      open={candidatesOpen}
      onClose={() => setCandidatesOpen(false)}
      clubId={clubId}
      suggestions={data.suggestions}
      onSaved={() => void data.refresh()}
    />
  )
  if (view === 'ended')
    return (
      <>
        <MeetingEnded
          summary={`${meeting.title || '회의'} · ${when} · 들은 말 ${heard}개 · 토리 ${answers.length}번`}
          suggestions={data.suggestions}
          suggestionsError={data.suggestionsQuery.isError}
          extractionFailed={extractionFailed(decisions)}
          onRetry={() => void data.refresh()}
          onOpenCandidates={() => setCandidatesOpen(true)}
          onOpenRecord={() => setJustEnded(false)}
          review={data.review.data}
          clubId={clubId}
          onStartReview={() => data.startReview.mutate()}
          onSubmitReview={() => data.submitReview.mutate()}
          onSaveReviewNames={(version, names, members) => data.updateReviewSpeakers.mutateAsync({ version, names, members })}
          onCreateReviewDraft={(version) => data.createReviewDraft.mutate(version)}
          onSaveReviewCandidates={(version, requestId, candidates) => data.saveReviewCandidates.mutateAsync({ version, clientRequestId: requestId, candidates })}
          reviewBusy={data.startReview.isPending || data.submitReview.isPending || data.updateReviewSpeakers.isPending || data.createReviewDraft.isPending || data.saveReviewCandidates.isPending}
          reviewError={data.review.error || data.startReview.error || data.submitReview.error || data.updateReviewSpeakers.error || data.createReviewDraft.error || data.saveReviewCandidates.error}
          processingSteps={processingSteps}
        />
        {candidates}
      </>
    )
  const openCandidates = data.suggestions.length > 0 && (
    <Button onClick={() => setCandidatesOpen(true)}>후보 확인하기</Button>
  )
  const time = recordedClock(audio.recordedMs)
  const silent = view === 'recording' && now - lastSoundAt > SILENCE_MS
  const finish = () => data.finish.mutate(undefined, { onSuccess: () => setJustEnded(true) })
  const askToEnd = () => setEndOpen(true)
  const endMeeting = () => {
    setEndOpen(false)
    if (view === 'recording' || view === 'paused') void audio.stop()
    else finish()
  }

  const pills = {
    connecting: <StatusPill kind="connecting">연결하는 중</StatusPill>,
    recording: (
      <>
        <StatusPill kind="recording">
          녹음 중 <span className="tabular-nums">{time}</span>
        </StatusPill>
        {silent && (
          <StatusPill kind="silent">소리가 들리지 않아요 · 마이크를 확인해 주세요</StatusPill>
        )}
      </>
    ),
    paused: (
      <StatusPill kind="paused">
        일시정지 <span className="tabular-nums">{time}</span>
      </StatusPill>
    ),
    stopped: <StatusPill kind="off">마이크 꺼짐</StatusPill>,
    dropped: <StatusPill kind="off">마이크 꺼짐</StatusPill>,
    finalizing: (
      <StatusPill kind="finalizing">
        마무리하는 중{audio.recordedMs > 0 ? ` · ${time} 녹음` : ''}
      </StatusPill>
    ),
    ended: <StatusPill kind="ended">끝남</StatusPill>,
    record: <StatusPill kind="ended">끝남</StatusPill>,
    failed: <StatusPill kind="failed">마무리하지 못했어요 · 저장된 내용은 남아 있어요</StatusPill>,
  }[view]

  const actions = {
    connecting: (
      <Button variant="secondary" onClick={audio.abort}>
        시작 취소
      </Button>
    ),
    recording: (
      <>
        <Button variant="secondary" onClick={audio.pause}>
          일시정지
        </Button>
        <Button onClick={askToEnd}>회의 끝내기</Button>
      </>
    ),
    paused: (
      <>
        <Button onClick={audio.resume}>다시 녹음</Button>
        <Button variant="secondary" onClick={askToEnd}>
          회의 끝내기
        </Button>
      </>
    ),
    stopped: (
      <>
        {!transcripts.length && (
          <Button variant="secondary" onClick={() => void audio.start()}>
            녹음 시작
          </Button>
        )}
        <Button disabled={data.finish.isPending} onClick={askToEnd}>
          회의 끝내기
        </Button>
      </>
    ),
    dropped: audio.sentFrames === 0 && (
      <Button variant="secondary" disabled={data.finish.isPending} onClick={askToEnd}>
        회의 끝내기
      </Button>
    ),
    finalizing: audio.phase === 'idle' && (
      <Button variant="secondary" onClick={() => void data.refresh()}>
        다시 확인
      </Button>
    ),
    ended: null,
    record: openCandidates,
    failed: (
      <>
        <Button variant="secondary" onClick={() => void data.refresh()}>
          다시 확인
        </Button>
        {openCandidates}
      </>
    ),
  }[view]

  const audioError = audio.phase === 'error' ? audio.error : null
  const banners = (
    <>
      {view === 'paused' && (
        <MeetingBanner tone="pending">! 일시정지한 동안 한 말은 기록되지 않아요.</MeetingBanner>
      )}
      {view === 'stopped' && (
        <MeetingBanner tone="pending">
          {transcripts.length
            ? '! 이 회의는 녹음이 멈춰서 더 녹음할 수 없어요. 계속하려면 새 회의를 시작해 주세요.'
            : '! 아직 녹음하지 않은 회의예요.'}
        </MeetingBanner>
      )}
      {view === 'dropped' &&
        (audio.sentFrames === 0 ? (
          <MeetingBanner
            tone="failed"
            title="녹음을 시작하지 못했어요"
            action={
              <Button size="sm" onClick={() => void audio.start()}>
                다시 시도
              </Button>
            }
          >
            {audioError}
          </MeetingBanner>
        ) : (
          <MeetingBanner
            tone="failed"
            title="연결이 끊겨 녹음이 멈췄어요"
            action={
              <Button
                variant="secondary"
                size="sm"
                disabled={data.finish.isPending}
                onClick={askToEnd}
              >
                회의 끝내기
              </Button>
            }
          >
            지금까지 들은 말은 저장했어요. 이 회의는 더 녹음할 수 없어서, 계속하려면 새 회의를
            시작해 주세요.
          </MeetingBanner>
        ))}
      {view === 'finalizing' && (
        <MeetingBanner tone="info">마지막 말을 정리하는 동안 이 화면을 닫지 마세요.</MeetingBanner>
      )}
      {view === 'failed' && audioError && (
        <MeetingBanner tone="failed" title="마무리하지 못했어요">
          {audioError}
        </MeetingBanner>
      )}
      {(view === 'recording' || view === 'paused') &&
        audio.error &&
        audio.error !== hiddenWarning && (
          <MeetingBanner
            tone="pending"
            action={
              <button
                type="button"
                aria-label="안내 닫기"
                onClick={() => setHiddenWarning(audio.error)}
                className="rounded-[8px] px-2 py-1 hover:bg-card"
              >
                ✕
              </button>
            }
          >
            {audio.error}
          </MeetingBanner>
        )}
      {view === 'recording' && audio.noiseSuppression === false && (
        <MeetingBanner tone="pending">
          이 브라우저에서 마이크 잡음 억제가 꺼져 있어요. 조용한 곳에서 녹음해 주세요.
        </MeetingBanner>
      )}
      {data.meeting.isError && (
        <MeetingBanner
          tone="failed"
          title="회의 정보를 새로 불러오지 못했어요"
          action={
            <Button variant="secondary" size="sm" onClick={() => void data.refresh()}>
              다시 확인
            </Button>
          }
        >
          {meetingError(data.meeting.error)}
        </MeetingBanner>
      )}
      {data.finish.error && (
        <MeetingBanner tone="failed">{meetingError(data.finish.error)}</MeetingBanner>
      )}
    </>
  )

  return (
    <>
      <div className="mx-auto flex max-w-[1240px] flex-col gap-4 lg:h-[calc(100dvh-72px)]">
        <MeetingHeader
          title={meeting.title || '회의'}
          pills={pills}
          meta={meta}
          actions={actions}
        />
        {banners}
        <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] xl:grid-cols-[420px_minmax(0,1fr)]">
          <TranscriptColumn
            className="max-h-[60vh] lg:max-h-none"
            transcripts={transcripts}
            decisions={decisions}
            startedAt={meeting.startedAt}
            live={live}
            countLabel={ended ? `들은 말 ${heard}개` : undefined}
          />
          <ToriColumn
            className="max-h-[70vh] lg:max-h-none"
            transcripts={transcripts}
            decisions={decisions}
            startedAt={meeting.startedAt}
            ongoing={!ended}
            now={now}
            loading={data.transcripts.isPending || data.decisions.isPending}
            error={data.transcripts.isError || data.decisions.isError}
            onRefresh={data.refresh}
          />
        </div>
      </div>
      {candidates}
      <EndMeetingModal
        open={endOpen}
        subtitle={`${meeting.title || '회의'}${audio.recordedMs > 0 ? ` · ${time} 녹음` : ''} · 들은 말 ${heard}개`}
        heard={heard}
        answered={answers.length}
        recording={view === 'recording' || view === 'paused'}
        busy={data.finish.isPending}
        onClose={() => setEndOpen(false)}
        onConfirm={endMeeting}
      />
      <LeaveMeetingModal
        open={blocker.state === 'blocked'}
        subtitle={`${meeting.title || '회의'} · ${time} 녹음 중`}
        onStay={() => blocker.reset?.()}
        onLeave={() => blocker.proceed?.()}
      />
    </>
  )
}
