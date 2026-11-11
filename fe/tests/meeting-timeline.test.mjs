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
const { sourceOf, transcriptTime, visibleDecision, meetingAnswers, toriResults, extractionFailed, isCandidateSaved, meetingProcessingSteps, meetingWhen, clockTime, askedAgo, recordedClock, meetingView } = await import(
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
  assert.deepEqual(meetingAnswers([current], [stale, outdated, valid]).map(({ decision: d }) => d.id), ['current-answer'])
})

test('NO_LOOKUP and FAILED do not appear as answers; NOT_FOUND remains a query result', () => {
  const utterance = transcript('utterance', 1)
  const ignored = decision('ignored', utterance, { kind: 'NO_LOOKUP', route: 'NONE' })
  const failed = decision('failed', utterance, { kind: 'FAILED', status: 'FAILED', route: 'ERROR' })
  const notFound = decision('no-record', utterance, { kind: 'NOT_FOUND', output: null })
  assert.deepEqual(meetingAnswers([utterance], [ignored, failed, notFound]).map(({ decision: d }) => d.id), ['no-record'])
})

test('an answer keeps the time of the utterance it answers', () => {
  const first = transcript('first', 1)
  const late = decision('late-answer', first)
  assert.equal(transcriptTime(sourceOf(late, [first]), '2026-10-19T05:00:00.000Z'), '14:00')
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

test('a late answer for an earlier utterance leads while live and follows utterance order in the record', () => {
  const earlier = transcript('earlier', 12)
  const later = transcript('later', 13)
  const quick = decision('quick', later, { createdAt: '2026-10-19T05:00:04.000Z' })
  const slow = decision('slow', earlier, { createdAt: '2026-10-19T05:00:05.000Z' })
  const ids = (order) => meetingAnswers([earlier, later], [quick, slow], order).map(({ decision: d }) => d.id)
  assert.deepEqual(ids(), ['slow', 'quick'])
  assert.deepEqual(ids('seq'), ['quick', 'slow'])
})





test('meeting list rows read the Seoul start time and the meeting length', () => {
  assert.equal(meetingWhen({ startedAt: '2026-10-27T05:12:00Z', endedAt: '2026-10-27T05:34:20Z' }), '10/27(화) 14:12 · 22분')
  assert.equal(meetingWhen({ startedAt: '2026-10-27T05:12:00Z', endedAt: null }), '10/27(화) 14:12')
  assert.equal(meetingWhen({ startedAt: null, endedAt: null }), '시각 미정')
  assert.equal(clockTime('2026-10-26T15:05:00Z'), '00:05')
  assert.equal(meetingWhen({ startedAt: 'not a date', endedAt: null }), '시각 미정', 'a bad date does not throw')
  assert.equal(meetingWhen({ startedAt: '2026-10-27T05:12:00Z', endedAt: 'not a date' }), '10/27(화) 14:12')
  assert.equal(clockTime('not a date'), 'not a date')
})

test('answer cards say how long ago the question was asked', () => {
  const at = Date.parse('2026-10-19T05:27:00Z')
  assert.equal(askedAgo(at, at + 59_000), '방금')
  assert.equal(askedAgo(at, at + 8 * 60_000 + 5_000), '8분 전')
})

test('the recording pill shows minutes and seconds, adding hours only when needed', () => {
  assert.equal(recordedClock(0), '0:00')
  assert.equal(recordedClock((21 * 60 + 38) * 1000 + 900), '21:38')
  assert.equal(recordedClock((3600 + 5 * 60 + 7) * 1000), '1:05:07')
})

test('the local audio phase decides the screen before the DB status catches up', () => {
  assert.equal(meetingView('RECORDING', 'permission', false), 'connecting')
  assert.equal(meetingView('RECORDING', 'recording', false), 'recording')
  assert.equal(meetingView('RECORDING', 'paused', false), 'paused')
  for (const status of ['RECORDING', 'FINALIZING', 'COMPLETED', 'FAILED']) {
    assert.equal(meetingView(status, 'processing', false), 'finalizing', `${status} keeps waiting for the socket`)
  }
  assert.equal(meetingView('FINALIZING', 'idle', false), 'finalizing')
  assert.equal(meetingView('FINALIZING', 'error', true), 'failed', 'a failed finish is not shown as an endless wait')
  assert.equal(meetingView('RECORDING', 'idle', false), 'stopped')
  assert.equal(meetingView('RECORDING', 'error', false), 'dropped')
  assert.equal(meetingView('RECORDING', 'completed', true), 'finalizing')
  assert.equal(meetingView('COMPLETED', 'completed', true), 'ended')
  assert.equal(meetingView('COMPLETED', 'idle', false), 'record')
  assert.equal(meetingView('FAILED', 'error', true), 'failed')
})

test('lookup failures sit with the answers in the same order, without polling jobs', () => {
  const first = transcript('first', 1)
  const second = transcript('second', 2)
  const answer = decision('answer', first, { createdAt: '2026-10-19T05:00:30.000Z' })
  const failure = decision('failure', second, { kind: 'FAILED', status: 'PARTIAL', route: 'ERROR', output: null, createdAt: '2026-10-19T05:00:10.000Z' })
  const stale = decision('stale', second, { kind: 'FAILED', status: 'STALE', route: 'ERROR' })
  const ids = (order) => toriResults([first, second], [answer, failure, stale], order).map(({ decision: d }) => d.id)
  assert.deepEqual(ids('arrival'), ['answer', 'failure'])
  assert.deepEqual(ids('seq'), ['failure', 'answer'])
  assert.equal(transcriptTime({ ...first, startMs: null, createdAt: 'not a date' }), '', 'a bad time does not throw')
})

test('a failed task extraction is told apart from a meeting with no candidates', () => {
  const utterance = transcript('utterance', 1)
  const ok = decision('ok', utterance, { toolCalls: [{ tool: 'tasks.extract', status: 'OK', resultCount: 0 }] })
  const failed = decision('failed', utterance, { status: 'PARTIAL', toolCalls: [{ tool: 'tasks.extract', status: 'FAILED', code: 'TIMEOUT' }] })
  const stale = { ...failed, id: 'stale', status: 'STALE' }
  assert.equal(extractionFailed([ok]), false)
  assert.equal(extractionFailed([ok, failed]), true)
  assert.equal(extractionFailed([ok, stale]), false, 'an outdated decision does not count')
})

test('candidate saves count edited proposals and accepted candidates once each', () => {
  const suggestions = [
    { id: 'new', status: 'PROPOSED', version: 1 },
    { id: 'saved', status: 'PROPOSED', version: 2 },
    { id: 'confirmed', status: 'ACCEPTED', version: 1 },
  ]
  assert.deepEqual(suggestions.map(isCandidateSaved), [false, true, true])
  const savedCount = () => suggestions.filter(isCandidateSaved).length
  assert.equal(savedCount(), 2)

  suggestions[0].version += 1
  assert.equal(savedCount(), 3, 'saving a proposal counts it without accepting or reserving it')
  assert.equal(suggestions[0].status, 'PROPOSED')
  suggestions[0].version += 1
  assert.equal(savedCount(), 3, 'saving again does not create another saved candidate')
})

test('candidate save status stays unconfirmed while data is pending or failed', () => {
  const input = {
    transcriptCount: 0,
    transcriptPending: false,
    transcriptError: false,
    answerCount: 0,
    answerPending: false,
    answerError: false,
    candidateCount: 1,
    candidateSavedCount: 1,
    candidatePending: false,
    candidateError: false,
    extractionError: false,
  }
  assert.equal(meetingProcessingSteps({ ...input, candidatePending: true })[3].state, 'waiting')
  assert.equal(meetingProcessingSteps({ ...input, candidateError: true })[3].state, 'failed')
  assert.equal(meetingProcessingSteps(input)[3].state, 'done')
})

test('meeting processing status keeps failures separate from empty results and saves', () => {
  const steps = meetingProcessingSteps({
    transcriptCount: 2,
    transcriptPending: false,
    transcriptError: false,
    answerCount: 1,
    answerPending: false,
    answerError: true,
    candidateCount: 3,
    candidateSavedCount: 1,
    candidatePending: false,
    candidateError: false,
    extractionError: false,
  })
  assert.deepEqual(steps.map((step) => step.state), ['done', 'failed', 'done', 'waiting'])
  assert.match(steps[3].detail, /1\/3/)
})
