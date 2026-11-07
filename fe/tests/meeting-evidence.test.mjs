import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(
  new URL('../src/features/meetings/evidence.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
})
const { recordCitation, recordMatchesCitation, recordEvidenceBlocks, candidateEvidence } =
  await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

const transcript = {
  id: 'segment',
  sourceId: 'segment',
  sourceVersion: 2,
  final: true,
  seq: 1,
  text: '민수가 명단을 확인합니다.',
}
const decision = {
  id: 'decision',
  meetingId: 'meeting',
  status: 'SUCCEEDED',
  sources: [{ sourceId: 'segment', sourceVersion: 2 }],
}
const suggestion = { decisionId: 'decision', evidence: [{ sourceId: 'segment', sourceVersion: 2 }] }

test('live record citations open by record ID without requiring a stored quote or URL', () => {
  assert.deepEqual(
    recordCitation({ recordId: 'rec_123abc', fileName: '운영.csv', location: { label: '2행' } }),
    {
      recordId: 'rec_123abc',
      fileName: '운영.csv',
      locationLabel: '2행',
    },
  )
  assert.equal(recordCitation({ fileName: '연결 없는 과거 출처' }), null)
  for (const recordId of [
    'https://outside.test/record',
    '../../rec_123',
    'rec_123/file',
    '',
    null,
  ]) {
    assert.equal(recordCitation({ recordId, url: 'https://outside.test' }), null)
  }
})

test('a citation cannot show another accessible club record or a different record', () => {
  const citation = recordCitation({ recordId: 'rec_123abc' })
  assert.equal(
    recordMatchesCitation({ id: 'rec_123abc', clubId: 'selected-club' }, citation, 'selected-club'),
    true,
  )
  assert.equal(
    recordMatchesCitation(
      { id: 'rec_123abc', clubId: 'another-joined-club' },
      citation,
      'selected-club',
    ),
    false,
  )
  assert.equal(
    recordMatchesCitation({ id: 'rec_other', clubId: 'selected-club' }, citation, 'selected-club'),
    false,
  )
})

test('record context selects real parsed blocks at the cited location', () => {
  const parseResult = {
    blocks: [
      { text: '다른 행', location: { label: '1행' } },
      { text: '원문 내용', location: { label: '2행' } },
      { text: '같은 위치의 다음 내용', location: { label: '2행' } },
    ],
  }
  assert.deepEqual(recordEvidenceBlocks(parseResult, '2행'), {
    locationFound: true,
    blocks: [
      { text: '원문 내용', locationLabel: '2행' },
      { text: '같은 위치의 다음 내용', locationLabel: '2행' },
    ],
  })
  const missing = recordEvidenceBlocks(parseResult, '삭제된 위치')
  assert.equal(missing.locationFound, false)
  assert.equal(
    missing.blocks.length,
    3,
    'a stale location falls back to current real text, never a citation quote',
  )
  assert.deepEqual(recordEvidenceBlocks({ blocks: [null, { text: 42 }, { text: '' }] }, ''), {
    blocks: [],
    locationFound: true,
  })
})

test('CSV citation ranges select their individual source rows without including other rows', () => {
  const parseResult = {
    blocks: Array.from({ length: 7 }, (_, index) => ({
      text: `${index + 1}행 실제 내용`,
      location: { label: `${index + 1}행` },
    })),
  }
  const result = recordEvidenceBlocks(parseResult, '2~6행')
  assert.equal(result.locationFound, true)
  assert.deepEqual(
    result.blocks.map((block) => block.locationLabel),
    ['2행', '3행', '4행', '5행', '6행'],
  )
  assert.deepEqual(
    result.blocks.map((block) => block.text),
    ['2행 실제 내용', '3행 실제 내용', '4행 실제 내용', '5행 실제 내용', '6행 실제 내용'],
  )
})

test('incomplete, ambiguous, and unsafe CSV ranges preserve the current-text fallback', () => {
  const blocks = [
    { text: '범위 밖', location: { label: '1행' } },
    { text: '실제 2행', location: { label: '2행' } },
    { text: '실제 3행', location: { label: '3행' } },
    { text: '실제 5행', location: { label: '5행' } },
    { text: '다른 시트', location: { label: '시트1 · 4행' } },
  ]
  for (const label of [
    '2~5행',
    '5~2행',
    '0~2행',
    '2-3행',
    '2~3쪽',
    '시트1 · 2~3행',
    '2~3행 또는 5행',
    '1~9007199254740991행',
    '2~9007199254740992행',
  ]) {
    const result = recordEvidenceBlocks({ blocks }, label)
    assert.equal(result.locationFound, false, label)
    assert.equal(result.blocks.length, blocks.length, label)
  }
})

test('candidate evidence requires the current meeting decision and exact source version', () => {
  const result = candidateEvidence(suggestion, 'meeting', [decision], [transcript])
  assert.deepEqual(result.sources, [transcript])
  assert.equal(result.message, null)
  assert.equal(
    candidateEvidence(suggestion, 'other-meeting', [decision], [transcript]).sources.length,
    0,
  )
  assert.equal(
    candidateEvidence(suggestion, 'meeting', [{ ...decision, status: 'STALE' }], [transcript])
      .sources.length,
    0,
  )
  const changed = candidateEvidence(
    suggestion,
    'meeting',
    [decision],
    [{ ...transcript, sourceVersion: 3 }],
  )
  assert.equal(changed.sources.length, 0)
  assert.match(changed.message, /수정|없어/)
  assert.equal(
    candidateEvidence(suggestion, 'meeting', [decision], [{ ...transcript, final: false }]).sources
      .length,
    0,
  )
})

test('candidate evidence cannot link to an unrelated decision source or malformed version', () => {
  const unrelated = { ...suggestion, evidence: [{ sourceId: 'another', sourceVersion: 2 }] }
  assert.equal(
    candidateEvidence(
      unrelated,
      'meeting',
      [decision],
      [{ ...transcript, id: 'another', sourceId: 'another' }],
    ).sources.length,
    0,
  )
  for (const sourceVersion of ['2', 0, -1, 1.5, null]) {
    const malformed = { ...suggestion, evidence: [{ sourceId: 'segment', sourceVersion }] }
    assert.equal(
      candidateEvidence(malformed, 'meeting', [decision], [transcript]).sources.length,
      0,
    )
  }
})

test('legacy empty candidate evidence uses only its validated decision sources', () => {
  assert.deepEqual(
    candidateEvidence({ ...suggestion, evidence: [] }, 'meeting', [decision], [transcript]).sources,
    [transcript],
  )
  assert.equal(
    candidateEvidence(
      { ...suggestion, decisionId: 'missing', evidence: [] },
      'meeting',
      [decision],
      [transcript],
    ).sources.length,
    0,
  )
})

test('multi-source evidence deduplicates valid sources and reports an unavailable remainder', () => {
  const multiple = {
    ...suggestion,
    evidence: [
      suggestion.evidence[0],
      suggestion.evidence[0],
      { sourceId: 'missing', sourceVersion: 1 },
    ],
  }
  const result = candidateEvidence(multiple, 'meeting', [decision], [transcript])
  assert.deepEqual(result.sources, [transcript])
  assert.match(result.message, /일부/)
})
