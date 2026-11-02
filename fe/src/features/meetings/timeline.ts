import type { Decision, Meeting, TimelineEntry, Transcript } from './types'
import type { AudioPhase } from './audio/useMeetingAudio'
export function sourceOf(decision: Decision, transcripts: Transcript[]): Transcript | undefined {
  return transcripts.find(
    (t) =>
      t.final &&
      decision.sources.some(
        (s) => s.sourceId === t.sourceId && s.sourceVersion === t.sourceVersion,
      ),
  )
}
export function visibleDecision(decision: Decision, transcripts: Transcript[]) {
  return (
    decision.status !== 'STALE' &&
    decision.kind !== 'NO_LOOKUP' &&
    String(decision.kind) !== 'FAILED' &&
    !!sourceOf(decision, transcripts)
  )
}
// Keep each answer with the utterance it used, including answers arriving later.
export function reconcileTimeline(
  _previous: TimelineEntry[],
  transcripts: Transcript[],
  decisions: Decision[],
): TimelineEntry[] {
  const visibleTranscripts = transcripts
    .filter((t) => t.final)
    .sort(
      (a, b) => b.seq - a.seq || b.createdAt.localeCompare(a.createdAt) || b.id.localeCompare(a.id),
    )
  const visibleDecisions = decisions.filter((d) => visibleDecision(d, visibleTranscripts))
  const seen = new Set<string>()
  const entries: TimelineEntry[] = []
  for (const transcript of visibleTranscripts) {
    if (seen.has(`transcript:${transcript.id}`)) continue
    seen.add(`transcript:${transcript.id}`)
    entries.push({ type: 'transcript', id: transcript.id })
    const answers = visibleDecisions
      .filter((d) => sourceOf(d, visibleTranscripts)?.id === transcript.id)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt) || a.id.localeCompare(b.id))
    for (const answer of answers) {
      if (seen.has(`decision:${answer.id}`)) continue
      seen.add(`decision:${answer.id}`)
      entries.push({ type: 'decision', id: answer.id })
    }
  }
  return entries
}
export function transcriptTime(transcript: Transcript, startedAt?: string | null) {
  const at =
    startedAt && transcript.startMs != null
      ? new Date(startedAt).getTime() + transcript.startMs
      : new Date(transcript.createdAt).getTime()
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(at)
}

export function answerDelay(decision: Decision, transcript: Transcript, startedAt?: string | null) {
  const at =
    startedAt && transcript.startMs != null
      ? new Date(startedAt).getTime() + transcript.startMs
      : new Date(transcript.createdAt).getTime()
  return Math.max(1, Math.floor((new Date(decision.createdAt).getTime() - at) / 60000))
}

export function meetingAnswers(transcripts: Transcript[], decisions: Decision[]) {
  return decisions
    .filter(
      (d) =>
        (d.status === 'SUCCEEDED' || d.status === 'PARTIAL') && visibleDecision(d, transcripts),
    )
    .map((decision) => ({ decision, transcript: sourceOf(decision, transcripts)! }))
    .sort(
      (a, b) =>
        b.transcript.seq - a.transcript.seq ||
        b.decision.createdAt.localeCompare(a.decision.createdAt),
    )
}

export function meetingMicStatus(status: Meeting['status'], phase: AudioPhase) {
  if (status === 'FINALIZING') return '마지막 전사와 답변을 처리하고 있어요.'
  if (phase === 'recording') return '이 기기의 마이크로 회의를 듣고 있어요.'
  if (phase === 'connecting' || phase === 'permission') return '마이크 연결을 준비하고 있어요.'
  if (phase === 'flushing' || phase === 'ending' || phase === 'processing')
    return '마지막 음성을 처리하고 있어요.'
  if (phase === 'error') return '마이크 상태를 확인해 주세요.'
  return '이 기기의 마이크가 꺼져 있어요.'
}

// The terminal DB state can arrive before the last WebSocket acknowledgement.
export function meetingAudioVisible(status: Meeting['status'], audioActive: boolean) {
  return status === 'RECORDING' || audioActive
}

export function meetingToriVisible(status: Meeting['status'], audioActive: boolean) {
  return status === 'FINALIZING' || meetingAudioVisible(status, audioActive)
}
