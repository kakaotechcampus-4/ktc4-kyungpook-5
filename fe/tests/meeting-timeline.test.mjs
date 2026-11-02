// Run from fe/: node --test tests/*.test.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

// timeline.ts has only type imports. Transpile the real source without loading
// generated API types, browser globals, or a second copy of the implementation.
const source = await readFile(
  new URL('../src/features/meetings/timeline.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
})
const { reconcileTimeline, sourceOf, transcriptTime, visibleDecision, meetingAnswers, meetingMicStatus, meetingAudioVisible, meetingToriVisible } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`
)

function transcript(id, seq, overrides = {}) {
  return {
    id,
    sourceId: id,
    sourceVersion: 1,
    seq,
    text: '확정된 발화',
    final: true,
    version: 1,
    speakerLabel: null,
    startMs: (seq - 1) * 60_000,
    endMs: (seq - 1) * 60_000 + 5000,
    decisionJobId: null,
    createdAt: `2026-10-19T05:0${seq - 1}:00.000Z`,
    modifiedAt: `2026-10-19T05:0${seq - 1}:00.000Z`,
    ...overrides,
  }
}

function decision(id, parent, overrides = {}) {
  return {
    id,
    jobId: `job-${id}`,
    sourceType: 'MEETING_TRANSCRIPT',
    meetingId: 'meeting-1',
    sources: [{ sourceId: parent.sourceId, sourceVersion: parent.sourceVersion }],
    status: 'SUCCEEDED',
    route: 'RAG',
    kind: 'ANSWER',
    output: '등록한 자료에서 찾은 답입니다.',
    citations: [],
    createdAt: '2026-10-19T05:00:20.000Z',
    ...overrides,
  }
}

test('only final transcripts and their answers enter the timeline', () => {
  const final = transcript('final', 1)
  const partial = transcript('partial', 2, { final: false })
  const result = reconcileTimeline([], [partial, final], [decision('partial-answer', partial)])
  assert.deepEqual(result, [{ type: 'transcript', id: 'final' }])
})

test('stale decisions and answers for an older source version remain hidden', () => {
  const current = transcript('utterance', 1, { sourceVersion: 2, version: 2 })
  const stale = decision('stale-answer', current, { status: 'STALE' })
  const outdated = decision('outdated-answer', current, {
    sources: [{ sourceId: current.sourceId, sourceVersion: 1 }],
  })
  const valid = decision('current-answer', current)
  assert.equal(visibleDecision(stale, [current]), false)
  assert.equal(visibleDecision(outdated, [current]), false)
  assert.equal(sourceOf(outdated, [current]), undefined)
  assert.equal(sourceOf(valid, [current]), current)
  assert.deepEqual(reconcileTimeline([], [current], [stale, outdated, valid]), [
    { type: 'transcript', id: 'utterance' },
    { type: 'decision', id: 'current-answer' },
  ])
})

test('NO_LOOKUP and FAILED do not appear as answers; NOT_FOUND remains a query result', () => {
  const utterance = transcript('utterance', 1)
  const ignored = decision('ignored', utterance, { kind: 'NO_LOOKUP', route: 'NONE' })
  const failed = decision('failed', utterance, { kind: 'FAILED', status: 'FAILED', route: 'ERROR' })
  const notFound = decision('no-record', utterance, { kind: 'NOT_FOUND', output: null })
  assert.deepEqual(reconcileTimeline([], [utterance], [ignored, failed, notFound]), [
    { type: 'transcript', id: 'utterance' },
    { type: 'decision', id: 'no-record' },
  ])
})

test('a late answer stays with its utterance while newer speech remains first', () => {
  const first = transcript('first', 1)
  const second = transcript('second', 2)
  const alreadyDisplayed = reconcileTimeline([], [first, second], [])
  // This answer was created before the second utterance but arrived in a later GET.
  const late = decision('late-answer', first)
  const result = reconcileTimeline(alreadyDisplayed, [first, second], [late])
  assert.deepEqual(result, [
    { type: 'transcript', id: 'second' },
    { type: 'transcript', id: 'first' },
    { type: 'decision', id: 'late-answer' },
  ])
  assert.deepEqual(reconcileTimeline([], [second, first], [late]), result)
  assert.equal(sourceOf(late, [first, second]), first)
  assert.equal(transcriptTime(sourceOf(late, [first, second]), '2026-10-19T05:00:00.000Z'), '14:00')
})

test('repeated GET snapshots do not duplicate entries; a correction removes the old answer', () => {
  const utterance = transcript('utterance', 1)
  const oldAnswer = decision('old-answer', utterance)
  const previous = reconcileTimeline([], [utterance], [oldAnswer])
  assert.deepEqual(reconcileTimeline(previous, [utterance], [oldAnswer]), previous)

  const corrected = { ...utterance, sourceVersion: 2, version: 2, text: '정정한 확정 발화' }
  const newAnswer = decision('new-answer', corrected, { createdAt: '2026-10-19T05:02:00.000Z' })
  assert.deepEqual(reconcileTimeline(previous, [corrected], [oldAnswer, newAnswer]), [
    { type: 'transcript', id: 'utterance' },
    { type: 'decision', id: 'new-answer' },
  ])
})

test('an initial snapshot orders equal-time utterances by descending sequence', () => {
  const first = transcript('first', 1)
  const second = transcript('second', 2, { createdAt: first.createdAt })
  assert.deepEqual(reconcileTimeline([], [second, first], []), [
    { type: 'transcript', id: 'second' },
    { type: 'transcript', id: 'first' },
  ])
})


test('meeting answers show current source results newest first, retaining partial results', () => {
  const first = transcript('first', 1)
  const latest = transcript('latest', 2, { sourceVersion: 2 })
  const old = decision('old', first)
  const current = decision('current', latest, { status: 'PARTIAL' })
  const outdated = decision('outdated', latest, { sources: [{ sourceId: latest.sourceId, sourceVersion: 1 }] })
  const failed = decision('failed', latest, { status: 'FAILED' })
  assert.deepEqual(meetingAnswers([first, latest], [old, outdated, failed, current]).map(({ decision: d }) => d.id), ['current', 'old'])
})


test('microphone status follows the local phase, not only the recording meeting', () => {
  assert.match(meetingMicStatus('RECORDING', 'idle'), /마이크가 꺼져/)
  assert.match(meetingMicStatus('RECORDING', 'recording'), /듣고 있어요/)
  assert.match(meetingMicStatus('RECORDING', 'permission'), /준비/)
  assert.match(meetingMicStatus('RECORDING', 'error'), /확인/)
  assert.match(meetingMicStatus('FINALIZING', 'recording'), /마지막 전사/)
})


test('audio and Tori remain mounted until WebSocket processing ends even when DB reaches a terminal state', () => {
  for (const status of ['RECORDING', 'FINALIZING', 'COMPLETED', 'FAILED']) {
    assert.equal(meetingAudioVisible(status, true), true, `${status} must keep the active socket`)
    assert.equal(meetingToriVisible(status, true), true, `${status} must keep the active status`)
  }
  assert.equal(meetingAudioVisible('RECORDING', false), true)
  assert.equal(meetingAudioVisible('FINALIZING', false), false)
  assert.equal(meetingToriVisible('FINALIZING', false), true)
  for (const status of ['COMPLETED', 'FAILED']) {
    assert.equal(meetingAudioVisible(status, false), false)
    assert.equal(meetingToriVisible(status, false), false)
  }
})
