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
// Append on first observation: a slow answer never jumps back into an old utterance.
export function reconcileTimeline(
  previous: TimelineEntry[],
  transcripts: Transcript[],
  decisions: Decision[],
): TimelineEntry[] {
  const visibleTranscripts = transcripts.filter((t) => t.final)
  const visibleDecisions = decisions.filter((d) => visibleDecision(d, visibleTranscripts))
  const next = previous.filter((e) =>
    e.type === 'transcript'
      ? visibleTranscripts.some((t) => t.id === e.id)
      : visibleDecisions.some((d) => d.id === e.id),
  )
  const seen = new Set(next.map((e) => `${e.type}:${e.id}`))
  const incoming: { entry: TimelineEntry; at: string; seq: number }[] = [
    ...visibleTranscripts.map((t) => ({
      entry: { type: 'transcript' as const, id: t.id },
      at: t.createdAt,
      seq: t.seq,
    })),
    ...visibleDecisions.map((d) => ({
      entry: { type: 'decision' as const, id: d.id },
      at: d.createdAt,
      seq: Number.MAX_SAFE_INTEGER,
    })),
  ]
  incoming.sort((a, b) => a.at.localeCompare(b.at) || a.seq - b.seq)
  for (const { entry } of incoming) if (!seen.has(`${entry.type}:${entry.id}`)) next.push(entry)
  return next
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
