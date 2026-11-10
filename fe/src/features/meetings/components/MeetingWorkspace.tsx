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
  isCandidateSaved,
  meetingAnswers,
  meetingProcessingSteps,
  meetingView,
  recordedClock,
} from '../timeline'
import { CandidatesModal, ConfirmedTasks } from './Suggestions'
import { MeetingEnded } from './MeetingEnded'
import { EndMeetingModal, LeaveMeetingModal } from './MeetingConfirm'
import type { MeetingEvidenceFocus } from '../evidence'
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
  const [evidenceFocus, setEvidenceFocus] = useState<MeetingEvidenceFocus | null>(null)
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
  const allDecisions = data.decisions.data ?? EMPTY
  // 화자 확인에서 후보를 저장하면 서버가 답 없는 ANSWER 판단을 남긴다. 토리 답이 아니라서
  // 토리 칸·들은 말 표시에서는 빼고, 후보 근거 찾기와 저장 여부 판단에는 원래 목록을 쓴다.
  const decisions = useMemo(
    () => allDecisions.filter((d) => d.modelVersion !== 'meeting-review'),
    [allDecisions],
  )
  const answers = useMemo(() => meetingAnswers(transcripts, decisions), [transcripts, decisions])
  const heard = transcripts.filter((t) => t.final).length
  const currentEvidence =
    evidenceFocus &&
    transcripts.some((transcript) =>
      transcript.final && transcript.sourceId === evidenceFocus.sourceId &&
      transcript.sourceVersion === evidenceFocus.sourceVersion,
    ) &&
    allDecisions.some((decision) =>
      decision.id === evidenceFocus.decisionId && decision.meetingId === meetingId &&
      decision.status !== 'STALE' && decision.sources.some((source) =>
        source.sourceId === evidenceFocus.sourceId && source.sourceVersion === evidenceFocus.sourceVersion,
      ),
    )
      ? evidenceFocus
      : null
  const candidateSavedCount = data.suggestions.filter(isCandidateSaved).length
  const candidatesPending =
    data.suggestionsQuery.isPending || data.transcripts.isPending || data.decisions.isPending
  const candidatesError =
    data.suggestionsQuery.isError || data.transcripts.isError || data.decisions.isError
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
      candidateSavedCount,
      candidatePending: candidatesPending,
      candidateError: candidatesError,
      extractionError: extractionFailed(decisions),
    }),
    [
      answers.length,
      candidateSavedCount,
      candidatesPending,
      candidatesError,
      data.decisions.isError,
      data.decisions.isPending,
      data.suggestions,
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
  const candidateSaveMeta = candidatesPending
    ? '후보 저장 확인 중'
    : candidatesError
      ? '후보 저장 확인 실패'
      : `후보 저장 ${candidateSavedCount}/${data.suggestions.length}건`
  const meta = `${when} · ${candidateSaveMeta} · 토리 ${answers.length}번`
  // 화자 확인 패널은 회의 직후 화면에만 있다. 회의 기록에서는 남은 일이 있을 때만 배너로 알린다.
  // 후보를 저장하면 서버가 검토 jobId로 판단을 남기므로, 그 판단이 있으면 검토가 끝난 것이다.
  const review = data.review.data
  const reviewCandidatesSaved = !!review && allDecisions.some((d) => d.jobId === review.jobId)
  const reviewBanner: { tone: 'failed' | 'info'; text: string } | null =
    data.review.isError || review?.status === 'FAILED' || review?.status === 'SUBMISSION_UNKNOWN'
      ? {
          tone: 'failed',
          text: '화자분리를 완료하지 못했거나 상태를 확인하지 못했어요. 열어서 이유를 확인해 주세요.',
        }
      : review?.status === 'PROCESSING' || review?.status === 'SUBMITTING'
        ? { tone: 'info', text: '화자분리 결과를 기다리는 중이에요.' }
        : review?.status === 'QUEUED'
          ? { tone: 'info', text: '화자분리를 아직 실행하지 않았어요.' }
          : review && !reviewCandidatesSaved
            ? { tone: 'info', text: '화자 이름과 할 일 후보를 이어서 확인할 수 있어요.' }
            : // 들은 말이 없으면 저장된 녹음도 없어 검토를 시작할 수 없다.
              review === null && heard > 0
              ? { tone: 'info', text: '녹음에서 화자를 나눠 이름을 확인할 수 있어요.' }
              : null
  const candidates = (
    <CandidatesModal
      open={candidatesOpen}
      onClose={() => setCandidatesOpen(false)}
      clubId={clubId}
      suggestions={data.suggestions}
      onSaved={() => void data.refresh()}
      activeSuggestionId={evidenceFocus?.suggestionId}
      evidence={{
        meetingId: meeting.id,
        // 화자 확인에서 저장한 후보의 근거는 그 판단에 있다.
        decisions: allDecisions,
        transcripts,
        startedAt: meeting.startedAt,
        onOpen: (target) => {
          setCandidatesOpen(false)
          setJustEnded(false)
          setEvidenceFocus(target)
        },
      }}
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
          review={review ?? undefined}
          reviewCandidatesSaved={reviewCandidatesSaved}
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
      {evidenceFocus && (
        <MeetingBanner
          tone={currentEvidence ? 'info' : 'pending'}
          action={
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setCandidatesOpen(true)}>
                후보로 돌아가기
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEvidenceFocus(null)}>
                강조 해제
              </Button>
            </div>
          }
        >
          {currentEvidence
            ? `「${evidenceFocus.title}」의 근거 발화를 표시했어요.`
            : '선택한 근거 발화가 수정되었거나 없어 다시 확인해야 해요.'}
        </MeetingBanner>
      )}
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
      {view === 'record' && reviewBanner && (
        <MeetingBanner
          tone={reviewBanner.tone}
          title="회의 후 화자 확인"
          action={
            <Button size="sm" variant="secondary" onClick={() => setJustEnded(true)}>
              열기
            </Button>
          }
        >
          {reviewBanner.text}
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
            evidenceFocus={currentEvidence}
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
            clubId={clubId}
            evidenceFocus={currentEvidence}
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
