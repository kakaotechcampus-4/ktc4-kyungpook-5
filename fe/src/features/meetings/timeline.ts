import type { Decision, TimelineEntry, Transcript } from './types'
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
    .sort((a, b) => b.seq - a.seq || b.createdAt.localeCompare(a.createdAt) || b.id.localeCompare(a.id))
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
