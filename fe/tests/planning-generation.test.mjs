import assert from 'node:assert/strict'
import test from 'node:test'
import { build } from 'esbuild'
const { outputFiles } = await build({
  stdin: {
    contents: `export * from './src/features/planning/generation.ts'; export * from './src/features/planning/stream.ts'`,
    resolveDir: process.cwd(),
  },
  bundle: true,
  write: false,
  platform: 'node',
  format: 'esm',
  alias: { '@': new URL('../src', import.meta.url).pathname },
  plugins: [
    {
      name: 'transport',
      setup(builder) {
        builder.onResolve({ filter: /^@\/shared\/api\/client$/ }, () => ({
          path: 'transport',
          namespace: 'test',
        }))
        builder.onLoad({ filter: /.*/, namespace: 'test' }, () => ({
          contents: 'export const apiPostStream = (...args) => globalThis.transport(...args)',
        }))
      },
    },
  ],
})
const m = await import(
  `data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`
)
const draft = {
  conditions: {
    title: null,
    eventType: 'MT',
    startDate: null,
    endDate: null,
    location: null,
    headcount: 30,
    feePerPerson: 0,
    budgetTotal: null,
  },
  conditionMeta: {},
  deferredTopics: [],
}
const request = {
  version: 1,
  userId: 'u',
  clubId: 'c',
  eventId: 'e',
  key: 'k',
  kind: 'button',
  body: { baseRevision: 4, useCurrentConditions: false },
  baseline: { baseRevision: 4, planRevision: 7, steps: [{ id: 'old' }] },
  draft,
  started: true,
}
const result = {
  reply: '초안',
  changedFields: [],
  generationReadiness: { canGenerate: true, reasons: [] },
  baseRevision: 5,
  draft,
  generationResult: { status: 'generated', reason: null },
}
const fresh = { baseRevision: 5, planRevision: 8, steps: [{ id: 'new' }] }

test('generated receipt and new coherent saved snapshot are both required', () => {
  assert.equal(m.generatedSnapshotStatus(request, result, fresh), 'new')
  for (const steps of [
    [],
    [{ id: 'old' }],
    [{ id: 'new' }, { id: 'old' }],
    [{ id: 'new' }, { id: 'new' }],
  ]) {
    assert.equal(m.generatedSnapshotStatus(request, result, { ...fresh, steps }), 'unconfirmed')
  }
  assert.equal(
    m.generatedSnapshotStatus(request, { ...result, generationResult: null }, fresh),
    'unconfirmed',
  )
  assert.equal(
    m.generatedSnapshotStatus(request, result, { ...fresh, planRevision: 7 }),
    'unconfirmed',
  )
  assert.equal(
    m.generatedSnapshotStatus(request, { ...result, baseRevision: 6 }, fresh),
    'unconfirmed',
  )
  assert.equal(
    m.generatedSnapshotStatus(request, result, { ...fresh, baseRevision: 4 }),
    'unconfirmed',
  )
})
test('later edits are not announced as this request’s generated draft', () => {
  assert.equal(m.generatedSnapshotStatus(request, result, { ...fresh, baseRevision: 6 }), 'changed')
})
test('journal is scoped and corrupt/unsupported records cannot silently unlock a request', () => {
  const raw = JSON.stringify(request)
  assert.deepEqual(m.parseRequest(raw, 'u', 'c'), request)
  assert.equal(m.parseRequest(raw, 'other', 'c'), null)
  assert.equal(m.parseRequest(raw, 'u', 'other'), null)
  for (const value of [
    'unavailable',
    '{}',
    JSON.stringify({ ...request, version: 2 }),
    JSON.stringify({ ...request, draft: { conditions: {} } }),
    JSON.stringify({ ...request, baseline: { baseRevision: -1, planRevision: 0, steps: [] } }),
  ]) {
    assert.equal(m.parseRequest(value, 'u', 'c'), null)
  }
})
test('late cleanup preserves another request and original body/key survive storage', () => {
  const data = new Map()
  globalThis.sessionStorage = {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => data.set(k, v),
    removeItem: (k) => data.delete(k),
  }
  globalThis.window = new EventTarget()
  m.writeRequest(request)
  assert.deepEqual(m.parseRequest(m.readRequestText('u', 'c'), 'u', 'c').body, request.body)
  const next = { ...request, key: 'next' }
  m.writeRequest(next)
  m.removeRequest(request)
  assert.equal(m.parseRequest(m.readRequestText('u', 'c'), 'u', 'c').key, 'next')
  m.removeRequest(next)
  assert.equal(m.readRequestText('u', 'c'), null)
})
test('stream cuts never repeat the original POST, including generation_finished', async () => {
  let calls = 0,
    reconnects = 0,
    progress = 0
  globalThis.transport = async (_path, _body, options) => {
    calls++
    options.onEvent({
      event: 'progress',
      data: JSON.stringify({ kind: 'generation_finished', status: 'completed' }),
    })
  }
  await assert.rejects(
    m.streamPlan('/generate', {}, 'key', {
      onProgress: () => progress++,
      onReply() {},
      onReconnect: () => reconnects++,
    }),
  )
  assert.equal(calls, 1)
  assert.equal(progress, 1)
  assert.equal(reconnects, 1)
})
test('a completed done receipt survives a transport failure after the terminal event', async () => {
  globalThis.transport = async (_path, _body, options) => {
    options.onEvent({ event: 'done', data: JSON.stringify(result) })
    throw new TypeError('network closed')
  }
  assert.deepEqual(
    await m.streamPlan('/generate', {}, 'key', {
      onProgress() {},
      onReply() {},
      onReconnect() {
        assert.fail('must not reconnect')
      },
    }),
    result,
  )
})
test('explicit server errors stay failures and malformed streams stay unknown', async () => {
  for (const event of [
    { event: 'error', data: JSON.stringify({ code: 'VERSION_CONFLICT', message: 'changed' }) },
    { event: 'done', data: '{' },
    { event: 'done', data: '{}' },
    { event: 'done', data: JSON.stringify({ ...result, draft: {} }) },
  ]) {
    let calls = 0
    globalThis.transport = async (_path, _body, options) => {
      calls++
      options.onEvent(event)
    }
    await assert.rejects(
      m.streamPlan('/chat', {}, 'same-key', { onProgress() {}, onReply() {}, onReconnect() {} }),
    )
    assert.equal(calls, 1)
  }
})
