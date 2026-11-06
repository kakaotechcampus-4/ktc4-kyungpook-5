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

// 생성 화면의 진행 줄은 실제로 지난 구간만 체크한다. 요청 상태 하나가 줄 네 개의 상태를 정한다.
test('generation rows only check the stages that actually passed', () => {
  const rows = (phase, stoppedAt) => m.generationRows(phase, stoppedAt).join(' ')
  assert.deepEqual(m.GENERATION_ROWS, ['조건 확인', '초안 작성', '저장 확인', '계획 불러오기'])
  assert.equal(rows('requesting'), 'active pending pending pending')
  assert.equal(rows('generating'), 'done active pending pending')
  assert.equal(rows('verifying'), 'done done active pending')
  assert.equal(rows('loading'), 'done done done active')
  assert.equal(rows('done'), 'done done done done')
  // 저장은 됐지만 불러오지 못했다 → 마지막 줄만 멈춤
  assert.equal(rows('load-failed'), 'done done done failed')
  assert.equal(rows('changed'), 'done done done failed')
  // 연결이 끊겨 앞 구간의 결과를 모른다 → 앞의 두 줄은 체크하지 않고 저장 확인 중으로 본다
  assert.equal(rows('unknown'), 'unknown unknown active pending')
  // 멈춘 자리에서 실패를 보인다. 생성 실패는 「초안 작성」, 조건 부족은 「조건 확인」
  assert.equal(rows('failed', 'generating'), 'done failed pending pending')
  assert.equal(rows('failed', 'requesting'), 'failed pending pending pending')
  assert.equal(rows('failed', 'loading'), 'done done done failed')
})

// 「초안 작성」 옆 문구는 서버 신호로만 바뀐다(#388). 시작을 보지 못한 화면에는 붙이지 않는다.
test('drafting note follows generation_started then generation_writing only', () => {
  const note = (flow, ended = false) => m.draftingNote({ draft, ...flow }, ended)
  assert.equal(note({ phase: 'generating' }), '토리가 생각 중이에요')
  assert.equal(note({ phase: 'generating', writing: true }), '초안을 작성하는 중이에요')
  // 다음 줄로 넘어갔거나 끝났으면 문구를 지운다. 걸린 시간만 남는다
  assert.equal(note({ phase: 'verifying', writing: true }), null)
  assert.equal(note({ phase: 'generating', writing: true }, true), null)
  // 새로고침 뒤 결과를 확인하는 화면은 생성 시작을 보지 못했다
  assert.equal(note({ phase: 'unknown' }), null)
  assert.equal(note({ phase: 'requesting' }), null)
})

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
  assert.deepEqual(m.parseRequest(raw, 'u', 'c', 'e'), request)
  assert.equal(m.parseRequest(raw, 'other', 'c', 'e'), null)
  assert.equal(m.parseRequest(raw, 'u', 'other', 'e'), null)
  assert.equal(m.parseRequest(raw, 'u', 'c', 'other-event'), null)
  for (const value of [
    'unavailable',
    '{}',
    JSON.stringify({ ...request, version: 2 }),
    JSON.stringify({ ...request, draft: { conditions: {} } }),
    JSON.stringify({ ...request, baseline: { baseRevision: -1, planRevision: 0, steps: [] } }),
  ]) {
    assert.equal(m.parseRequest(value, 'u', 'c', 'e'), null)
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
  assert.deepEqual(
    m.parseRequest(m.readRequestText('u', 'c', 'e'), 'u', 'c', 'e').body,
    request.body,
  )
  const next = { ...request, key: 'next' }
  m.writeRequest(next)
  m.removeRequest(request)
  assert.equal(m.parseRequest(m.readRequestText('u', 'c', 'e'), 'u', 'c', 'e').key, 'next')
  m.removeRequest(next)
  assert.equal(m.readRequestText('u', 'c', 'e'), null)
})
test('a pending request locks only its own event (#342)', () => {
  const data = new Map()
  globalThis.sessionStorage = {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => data.set(k, v),
    removeItem: (k) => data.delete(k),
  }
  globalThis.window = new EventTarget()
  m.writeRequest(request)
  assert.notEqual(m.readRequestText('u', 'c', 'e'), null)
  assert.equal(m.readRequestText('u', 'c', 'other-event'), null)
  assert.equal(m.readRequestText('u', 'c', null), null)
  m.removeRequest(request)
})
test('request lookup applies a saved response, waits while processing, releases otherwise (#342)', () => {
  assert.equal(m.recoveryStep({ status: 'completed', result }), 'apply')
  assert.equal(m.recoveryStep({ status: 'processing', result: null }), 'wait')
  assert.equal(m.recoveryStep({ status: 'not_saved', result: null }), 'release')
  // 저장은 끝났지만 응답을 읽을 수 없다. 잠금을 풀고 저장된 계획을 다시 읽는다.
  assert.equal(m.recoveryStep({ status: 'completed', result: null }), 'release')
  assert.equal(m.recoveryStep({ status: 'completed', result: { ...result, draft: {} } }), 'release')
})
test('a cut chat stays in the conversation unless draft generation had started (#368)', () => {
  // 채팅 "인원 40명으로 바꿔 줘" → 끊김: 초안 생성 화면을 띄우지 않는다.
  assert.equal(m.checksInChat({ kind: 'chat', started: false }, 'unknown'), true)
  // 채팅 "이대로 초안 만들어 줘" → generation_started → 끊김: 초안 생성 화면에서 확인한다.
  assert.equal(m.checksInChat({ kind: 'chat', started: true }, 'unknown'), false)
  // 버튼 생성은 늘 초안 생성 화면에서 확인한다.
  assert.equal(m.checksInChat({ kind: 'button', started: false }, 'unknown'), false)
  // 결과를 받은 뒤의 단계(불러오기 등)는 채팅이어도 초안 생성 화면이다.
  assert.equal(m.checksInChat({ kind: 'chat', started: false }, 'loading'), false)
  assert.equal(m.checksInChat(null, 'unknown'), false)
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
