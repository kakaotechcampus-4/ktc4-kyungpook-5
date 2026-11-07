import assert from 'node:assert/strict'
import { build } from 'esbuild'
import test from 'node:test'

const { outputFiles } = await build({
  entryPoints: [new URL('../src/features/events/cardModel.ts', import.meta.url).pathname],
  bundle: true,
  write: false,
  platform: 'node',
  format: 'esm',
})
const { cardStatusText, cardStepText, showsProgress } = await import(
  `data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`
)

const ev = (status, states, extra = {}) => ({
  status,
  pendingApprovalCount: 0,
  currentStepName: null,
  stepProgress: states.map((state, i) => ({ stepOrder: i + 1, state })),
  ...extra,
})

test('planning card shows draft size, not progress', () => {
  assert.equal(cardStatusText(ev('PLANNING', ['TODO', 'TODO', 'TODO'])), '계획 중 · 초안 3단계')
  assert.equal(cardStepText(ev('PLANNING', ['TODO', 'TODO', 'TODO'])), '3단계')
})

test('planning card without draft says so', () => {
  assert.equal(cardStatusText(ev('PLANNING', [])), '계획 중 · 초안 없음')
  assert.equal(cardStepText(ev('PLANNING', [])), '—')
})

test('planning card ignores step progress', () => {
  assert.equal(cardStepText(ev('PLANNING', ['CURRENT', 'TODO'])), '2단계')
  assert.equal(showsProgress('PLANNING'), false)
})

test('on-going card keeps progress and approvals', () => {
  const e = ev('ON_GOING', ['DONE', 'CURRENT', 'TODO'], { pendingApprovalCount: 2 })
  assert.equal(cardStepText(e), '2 / 3')
  assert.equal(cardStatusText(e), '승인 대기 2건')
  assert.equal(showsProgress('ON_GOING'), true)
})
