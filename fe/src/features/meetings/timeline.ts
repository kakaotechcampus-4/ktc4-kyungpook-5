import type { Decision, Meeting, Transcript } from './types'
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
export function utteranceAt(transcript: Transcript, startedAt?: string | null) {
  return startedAt && transcript.startMs != null
    ? new Date(startedAt).getTime() + transcript.startMs
    : new Date(transcript.createdAt).getTime()
}
const SEOUL_CLOCK = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})
export function transcriptTime(transcript: Transcript, startedAt?: string | null) {
  const at = utteranceAt(transcript, startedAt)
  return Number.isNaN(at) ? '' : SEOUL_CLOCK.format(at)
}

const SEOUL_PARTS = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  month: 'numeric',
  day: 'numeric',
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

// 서버가 날짜를 잘못 주면 Intl이 에러를 던져 화면 전체가 멈춘다. 그때는 null.
function seoulParts(iso: string) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  return Object.fromEntries(SEOUL_PARTS.formatToParts(date).map((part) => [part.type, part.value]))
}

export function clockTime(iso: string) {
  const parts = seoulParts(iso)
  return parts ? `${parts.hour}:${parts.minute}` : iso
}

// 지난 회의 한 줄: "10/27(월) 14:12 · 22분"
export function meetingWhen(meeting: Pick<Meeting, 'startedAt' | 'endedAt'>) {
  const parts = meeting.startedAt ? seoulParts(meeting.startedAt) : null
  if (!parts) return '시각 미정'
  const start = `${parts.month}/${parts.day}(${parts.weekday}) ${parts.hour}:${parts.minute}`
  const minutes = Math.round(
    (Date.parse(meeting.endedAt ?? '') - Date.parse(meeting.startedAt!)) / 60000,
  )
  return Number.isNaN(minutes) ? start : `${start} · ${Math.max(1, minutes)}분`
}

// 답 카드의 "14:27에 물은 것 · 8분 전"
export function askedAgo(at: number, now: number) {
  const minutes = Math.floor((now - at) / 60000)
  return minutes < 1 ? '방금' : `${minutes}분 전`
}

// 녹음 알약의 "21:38"
export function recordedClock(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = String(total % 60).padStart(2, '0')
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${seconds}` : `${minutes}:${seconds}`
}

export interface ToriResult {
  decision: Decision
  transcript: Transcript
}

// judgment can arrive out of utterance order (#240). A live meeting shows the newest
// arrival first; a finished meeting's record reads in utterance order.
function byOrder(order: 'arrival' | 'seq') {
  return (a: ToriResult, b: ToriResult) => {
    const arrival = b.decision.createdAt.localeCompare(a.decision.createdAt)
    const seq = b.transcript.seq - a.transcript.seq
    return order === 'arrival' ? arrival || seq : seq || arrival
  }
}

export function meetingAnswers(
  transcripts: Transcript[],
  decisions: Decision[],
  order: 'arrival' | 'seq' = 'arrival',
) {
  return decisions
    .filter(
      (d) =>
        (d.status === 'SUCCEEDED' || d.status === 'PARTIAL') && visibleDecision(d, transcripts),
    )
    .map((decision) => ({ decision, transcript: sourceOf(decision, transcripts)! }))
    .sort(byOrder(order))
}

export function lookupFailed(decision: Decision) {
  return String(decision.kind) === 'FAILED'
}

// 토리 칸에 보일 것: 답, 그리고 조회가 실패한 판단. 조회가 실패해도 판단은 kind FAILED로
// 저장되므로 작업(job)을 따로 묻지 않는다.
export function toriResults(
  transcripts: Transcript[],
  decisions: Decision[],
  order: 'arrival' | 'seq',
): ToriResult[] {
  const failures = decisions.flatMap((decision) => {
    const transcript =
      decision.status !== 'STALE' && lookupFailed(decision)
        ? sourceOf(decision, transcripts)
        : undefined
    return transcript ? [{ decision, transcript }] : []
  })
  return [...meetingAnswers(transcripts, decisions, order), ...failures].sort(byOrder(order))
}

export type MeetingView =
  | 'connecting'
  | 'recording'
  | 'paused'
  | 'finalizing'
  | 'stopped'
  | 'dropped'
  | 'ended'
  | 'record'
  | 'failed'

// Which meeting screen to draw. The local audio phase wins over the DB status because
// the terminal DB state can arrive before the last WebSocket acknowledgement.
export function meetingView(
  status: Meeting['status'],
  phase: AudioPhase,
  justEnded: boolean,
): MeetingView {
  if (phase === 'connecting' || phase === 'permission') return 'connecting'
  if (phase === 'recording' || phase === 'paused') return phase
  if (phase === 'flushing' || phase === 'ending' || phase === 'processing') return 'finalizing'
  // The socket failed (end-ack or result timeout) while the server still says FINALIZING:
  // that is the "마무리하지 못했어요" state, not an endless wait.
  if (status === 'FINALIZING') return phase === 'error' ? 'failed' : 'finalizing'
  if (status === 'RECORDING') {
    if (phase === 'error') return 'dropped'
    return phase === 'completed' ? 'finalizing' : 'stopped'
  }
  if (status === 'FAILED') return 'failed'
  return justEnded ? 'ended' : 'record'
}
