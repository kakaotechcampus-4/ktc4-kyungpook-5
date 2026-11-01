import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = await readFile(
  new URL('../src/features/planning/reviewState.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
const exports = {}
vm.runInNewContext(outputText, { exports })
const { reviewCardState, showGenerationWarnings } = exports

const review = (status, generatedRevision, reviewedRevision = null, outcome = null) => ({
  status,
  generatedRevision,
  reviewedRevision,
  outcome,
})
const state = (planRevision, r, requesting = false) =>
  reviewCardState({ planRevision, review: r, requesting })

test('no review snapshot hides the card', () => {
  assert.equal(state(3, null), 'hidden')
})

test('not requested: hidden until the plan is edited after generation', () => {
  assert.equal(state(2, review('NOT_REQUESTED', 2)), 'hidden')
  assert.equal(state(3, review('NOT_REQUESTED', 2)), 'request')
})

test('a request in flight always shows reviewing', () => {
  for (const r of [
    review('NOT_REQUESTED', 2),
    review('NOT_REQUESTED', 2),
    review('DONE', 2, 3, 'issues'),
    review('FAILED', 2, 3),
    review('DONE', 2, 1, 'no_issues'),
  ])
    assert.equal(state(3, r, true), 'reviewing')
  assert.equal(state(2, review('NOT_REQUESTED', 2), true), 'reviewing')
})

test('server states for the current revision', () => {
  assert.equal(state(3, review('REVIEWING', 2, 3)), 'reviewing')
  assert.equal(state(3, review('DONE', 2, 3, 'issues')), 'issues')
  assert.equal(state(3, review('DONE', 2, 3, 'no_issues')), 'clear')
  assert.equal(state(3, review('FAILED', 2, 3)), 'failed')
})

test('a review of an older revision is stale', () => {
  for (const status of ['DONE', 'FAILED', 'REVIEWING'])
    assert.equal(state(4, review(status, 2, 3, status === 'DONE' ? 'issues' : null)), 'stale')
})

test('after a failed request the card falls back, never stuck on reviewing', () => {
  assert.equal(state(3, review('NOT_REQUESTED', 2), false), 'request')
})

test('generation warnings hide once the plan was edited', () => {
  assert.equal(showGenerationWarnings(3, null), true)
  assert.equal(showGenerationWarnings(2, review('NOT_REQUESTED', 2)), true)
  assert.equal(showGenerationWarnings(3, review('NOT_REQUESTED', 2)), false)
})
