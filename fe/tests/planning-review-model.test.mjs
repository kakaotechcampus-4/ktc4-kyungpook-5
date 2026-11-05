import assert from 'node:assert/strict'
import { build } from 'esbuild'
import test from 'node:test'
const { outputFiles } = await build({
  entryPoints: [new URL('../src/features/planning/reviewModel.ts', import.meta.url).pathname],
  bundle: true,
  write: false,
  platform: 'node',
  format: 'esm',
})
const { currentExcluded, reviewGroups, planningStage } = await import(
  `data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`
)

test('current exclusions follow saved inclusion, not historical AI exclusion reasons', () => {
  const before = currentExcluded([{ code: 'DEMAND_SURVEY' }, { code: 'EVENT_DAY' }])
  assert.equal(before.length, 11)
  assert.ok(!before.some((step) => step.code === 'DEMAND_SURVEY'))
  const after = currentExcluded([{ code: 'EVENT_DAY' }])
  assert.equal(after.length, 12)
  assert.ok(after.some((step) => step.code === 'DEMAND_SURVEY'))
})
test('catalogue groups keep server order and unknown codes stay visible', () => {
  const steps = [
    { code: 'RESEARCH_VENUE' },
    { code: 'ASSIGN_ROLES' },
    { code: 'FUTURE_STEP', name: '새 단계' },
  ]
  assert.deepEqual(
    reviewGroups(steps).map((group) => group.steps),
    [steps.slice(0, 2), steps.slice(2)],
  )
  assert.equal(reviewGroups(steps).flatMap((group) => group.steps).length, steps.length)
})
test('one and all catalogue stages remain visible', () => {
  const catalogue = currentExcluded([])
  assert.equal(catalogue.length, 13)
  assert.equal(currentExcluded(catalogue).length, 0)
  assert.equal(reviewGroups(catalogue).flatMap((group) => group.steps).length, 13)
  assert.equal(reviewGroups([catalogue[9]]).flatMap((group) => group.steps).length, 1)
})
test('existing and direct links choose review only with a stored draft; explicit conditions stays', () => {
  assert.equal(planningStage(null, true), 'review')
  assert.equal(planningStage('review', false), 'conditions')
  assert.equal(planningStage(null, false), 'conditions')
  assert.equal(planningStage('conditions', true), 'conditions')
})
