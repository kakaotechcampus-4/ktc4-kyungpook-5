import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = await readFile(
  new URL('../src/features/planning/recordReferences.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
})
const api = {}
vm.runInNewContext(outputText, { exports: api, Set })
const plain = (value) => JSON.parse(JSON.stringify(value))
const src = (recordId, label = '2행') => ({
  recordId,
  fileName: `${recordId}.csv`,
  location: { label },
})
const lookup = {
  status: 'available',
  query: '과거 참가비',
  reason: null,
  result: {
    facts: [{ content: '참가비 45000원', sources: [src('a'), src('a')] }],
    notFound: [],
    conflicts: [],
  },
}
const screen = {
  baseRevision: 4,
  recordLookupHistory: [{ revision: 2, lookup }],
  lastRecordLookup: lookup,
}

test('a turn without a lookup preserves references after refresh or generation', () => {
  assert.deepEqual(
    plain(api.planningRecordHistory(screen, { baseRevision: 5, recordLookup: null })),
    screen.recordLookupHistory,
  )
  assert.deepEqual(plain(api.planningRecordHistory(screen, null)), screen.recordLookupHistory)
})

test('a failed new search becomes latest while the old evidence remains historical', () => {
  const failed = { status: 'failed', result: null, query: '작년 숙소', reason: null }
  const entries = plain(
    api.planningRecordHistory(screen, { baseRevision: 5, recordLookup: failed }),
  )
  assert.equal(entries[0].lookup.status, 'failed')
  assert.equal(entries[1].lookup.status, 'available')
  assert.equal(entries.length, 2)
  assert.equal(screen.recordLookupHistory.length, 1)
})

test('saved responses do not duplicate and late responses do not replace newer data', () => {
  assert.equal(
    api.planningRecordHistory(screen, { baseRevision: 2, recordLookup: lookup }).length,
    1,
  )
  const newer = { ...screen, baseRevision: 5, recordLookupHistory: [{ revision: 5, lookup }] }
  assert.equal(
    api.planningRecordHistory(newer, { baseRevision: 5, recordLookup: lookup }).length,
    1,
  )
  assert.deepEqual(
    plain(
      api.planningRecordHistory(newer, { baseRevision: 3, recordLookup: { status: 'failed' } }),
    ),
    newer.recordLookupHistory,
  )
})

test('old snapshots restore their available state even without evidence details', () => {
  const legacy = { ...lookup, result: null }
  assert.deepEqual(
    plain(api.planningRecordHistory({ baseRevision: 9, lastRecordLookup: legacy }, null)),
    [{ revision: 0, lookup: legacy }],
  )
  assert.deepEqual(plain(api.planningRecordHistory(undefined, null)), [])
})

test('document counts deduplicate across searches and include conflict evidence', () => {
  const conflict = {
    ...lookup,
    result: {
      facts: [],
      notFound: [],
      conflicts: [
        {
          description: '금액 차이',
          values: [
            { content: '45000원', sources: [src('a', '3행')] },
            { content: '40000원', sources: [src('b')] },
          ],
        },
      ],
    },
  }
  assert.equal(
    api.referenceDocumentCount([
      { revision: 2, lookup },
      { revision: 3, lookup: conflict },
    ]),
    2,
  )
  assert.equal(api.uniqueEvidenceSources([src('a'), src('a'), src('a', '3행')]).length, 2)
})

test('lookup status announcements distinguish unavailable, conflict and legacy evidence', () => {
  const messages = ['available', 'not_found', 'failed', 'rejected'].map((status) =>
    api.recordLookupAnnouncement({ ...lookup, status }),
  )
  assert.equal(new Set(messages).size, 4)
  assert.match(api.recordLookupAnnouncement({ ...lookup, result: null }), /상세 출처/)
  assert.match(
    api.recordLookupAnnouncement({ ...lookup, result: { ...lookup.result, conflicts: [{}] } }),
    /내용이 다른/,
  )
})
