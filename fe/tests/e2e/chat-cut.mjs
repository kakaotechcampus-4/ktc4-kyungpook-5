// 계획 채팅이 끊겼을 때 어느 화면에서 결과를 확인하는지 본다(#368). BE 없이 가짜 API로 돈다.
// 배포 중 = 가짜 API가 모든 요청에 502를 돌려준다(down). 실제 모델·DB는 쓰지 않는다.
//
//   VITE_API_BASE_URL=http://127.0.0.1:8917 npx vite --port 5197 --strictPort --host 127.0.0.1
//   UI_ORIGIN=http://127.0.0.1:5197 MOCK_PORT=8917 node tests/e2e/chat-cut.mjs
import assert from 'node:assert/strict'
import http from 'node:http'
import path from 'node:path'
import fs from 'node:fs/promises'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const UI = process.env.UI_ORIGIN || 'http://127.0.0.1:5197'
const PORT = Number(process.env.MOCK_PORT || 8917)
const OUT = path.resolve(process.env.OUT_DIR || 'docs/evidence/368')
await fs.mkdir(OUT, { recursive: true })

const draft = (headcount) => ({
  conditions: {
    title: '가을 MT',
    eventType: 'MT',
    headcount,
    feePerPerson: 30000,
    budgetTotal: null,
    startDate: '2026-11-28',
    endDate: '2026-11-29',
    location: '경주',
  },
  conditionMeta: {},
  deferredTopics: [],
})
let st
const reset = () => {
  st = {
    down: false,
    headcount: 30,
    revision: 1,
    steps: [],
    messages: [
      { id: 'm1', seq: 1, role: 'USER', content: '가을 MT 준비해요. 30명, 경주, 11월 28~29일' },
      { id: 'm2', seq: 2, role: 'ASSISTANT', content: '가을 MT 조건을 정리했어요.' },
    ],
    lookup: null,
    posts: [],
    lookups: 0,
    response: null,
  }
}
reset()
const view = () => ({
  reply: '인원을 40명으로 바꿨어요.',
  draft: draft(st.headcount),
  changedFields: ['headcount'],
  recordLookup: null,
  generationReadiness: { canGenerate: true, reasons: [] },
  generationResult: null,
  baseRevision: st.revision,
})
const send = (res, status, data) => {
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(status < 300 ? { data, meta: null } : { error: data }))
}
const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', UI)
  res.setHeader('Access-Control-Allow-Headers', 'authorization,content-type,idempotency-key,accept')
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PATCH,OPTIONS')
  if (req.method === 'OPTIONS') return res.end()
  // B: 새로고침 직후 로그인 확인(/me)까지 막히면 계획 화면 전에 멈추므로, 이 행사 경로만 막는 경우도 둔다.
  if (st.down && (!st.eventOnly || req.url.includes('/events/e1'))) {
    res.writeHead(502)
    return res.end('bad gateway')
  }
  const url = new URL(req.url, 'http://x')
  const p = url.pathname.replace('/api/v1', '')
  if (p === '/me')
    return send(res, 200, {
      id: 'u1',
      email: 'tester@example.com',
      emailVerified: true,
      clubs: [{ id: 'c1', name: '확인 동아리', role: 'OWNER' }],
    })
  if (p === '/events/drafts')
    return send(res, 200, [
      { id: 'e1', title: '가을 MT', createdAt: '2026-11-06T00:00:00Z', savedAt: null },
    ])
  if (p === '/events/e1')
    return send(res, 200, {
      id: 'e1',
      title: '가을 MT',
      status: 'PLANNING',
      startDate: '2026-11-28',
      endDate: '2026-11-29',
      dday: 22,
      location: '경주',
      headcount: st.headcount,
      currentStep: null,
      payment: null,
      budget: null,
    })
  if (p === '/events/e1/plan')
    return send(res, 200, {
      draft: draft(st.headcount),
      warnings: [],
      excludedSteps: [],
      summary: { totalSteps: 0, aiSteps: 0, approvalSteps: 0, manualSteps: 0 },
      historyUsage: null,
      baseRevision: st.revision,
      planRevision: 0,
      generationReadiness: { canGenerate: true, reasons: [] },
      recordLookupHistory: [],
      review: null,
    })
  if (p === '/events/e1/plan/messages') return send(res, 200, st.messages)
  if (p === '/events/e1/plan/steps') return send(res, 200, st.steps)
  if (p === '/events/e1/plan/steps/snapshot')
    return send(res, 200, { baseRevision: st.revision, planRevision: 0, steps: st.steps })
  if (p.startsWith('/events/e1/plan/requests/')) {
    st.lookups++
    return send(res, 200, st.lookup ?? { status: 'processing', result: null })
  }
  if (req.method === 'POST' && /\/plan\/(chat|generate)\/stream$/.test(p)) {
    let body = ''
    for await (const c of req) body += c
    st.posts.push({ path: p, key: req.headers['idempotency-key'], body: JSON.parse(body) })
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' })
    res.flushHeaders()
    st.response = res
    return
  }
  // Other screens (notifications etc.) are not part of this check.
  return send(res, 200, [])
})
await new Promise((r) => server.listen(PORT, '127.0.0.1', r))

const line = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
const browser = await chromium.launch({
  headless: true,
  ...(process.env.P2_BROWSER_PATH ? { executablePath: process.env.P2_BROWSER_PATH } : {}),
})
const errors = []
const results = []
async function open() {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  await context.addInitScript(() => {
    localStorage.setItem('unyounghae_access_token', 'fake-token')
    localStorage.setItem('unyounghae_selected_club_id', 'c1')
  })
  const page = await context.newPage()
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(`${UI}/planning?eventId=e1&stage=conditions`)
  await page
    .getByRole('button', { name: '이 조건으로 초안 만들기', exact: true })
    .waitFor({ timeout: 15000 })
  return { page, context }
}
const box = (page) => page.getByRole('textbox', { name: '계획 대화 답변' })
async function waitStream() {
  for (let i = 0; i < 200 && !st.response; i++) await new Promise((r) => setTimeout(r, 20))
  assert.ok(st.response, 'stream opened')
}
async function sendChat(page, text) {
  await box(page).fill(text)
  await box(page).press('Enter')
  await waitStream()
}
const NOTICE = '서버에 저장됐는지 확인하고 있어요'
const generationRegion = (page) => page.getByRole('region', { name: '초안 생성 상태' })
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
// The turn the server saved before going down.
function saveTurn(text) {
  st.headcount = 40
  st.revision = 2
  st.messages = [
    ...st.messages,
    { id: 'm3', seq: 3, role: 'USER', content: text },
    { id: 'm4', seq: 4, role: 'ASSISTANT', content: '인원을 40명으로 바꿨어요.' },
  ]
  st.lookup = { status: 'completed', result: view() }
}

try {
  // A. 대화 중 끊김 → 배포 중(502) → 서버 복귀 → 저장된 답변
  {
    reset()
    const { page, context } = await open()
    const text = '인원은 40명으로 바꿔 줘'
    await sendChat(page, text)
    st.response.write(
      line('progress', {
        operationId: 'c1',
        kind: 'condition_started',
        status: 'running',
        text: '조건을 반영하고 있어요',
      }),
    )
    await wait(200)
    st.down = true
    st.response.destroy()
    await page.getByText(NOTICE).first().waitFor()
    await wait(3500) // 조회가 502로 한 번 이상 실패하는 동안
    assert.equal(await generationRegion(page).count(), 0, 'A: no generation screen while checking')
    assert.equal(await page.getByText('초안 생성 결과를 확인해야 해요').count(), 0)
    assert.equal(
      await page.getByText('저장된 계획을 불러오지 못했어요').count(),
      0,
      'A: chat not replaced by error card',
    )
    assert.equal(await box(page).getAttribute('readonly'), '', 'A: input locked')
    assert.equal(
      await page.getByRole('button', { name: '이 조건으로 초안 만들기', exact: true }).isDisabled(),
      true,
    )
    await page.screenshot({ path: path.join(OUT, 'a1-chat-checking.png'), fullPage: true })
    saveTurn(text)
    st.down = false
    await page.getByText('인원을 40명으로 바꿨어요.').first().waitFor({ timeout: 10000 })
    await page
      .getByText(NOTICE)
      .waitFor({ state: 'detached', timeout: 5000 })
      .catch(() => {})
    assert.equal(await page.getByText(NOTICE).count(), 0, 'A: notice gone')
    assert.equal(await box(page).inputValue(), '', 'A: saved text not left in input')
    assert.equal(await box(page).getAttribute('readonly'), null, 'A: input unlocked')
    assert.equal(st.posts.length, 1, 'A: no second POST')
    await page.screenshot({ path: path.join(OUT, 'a2-chat-recovered.png'), fullPage: true })
    results.push({
      case: 'A mid-session cut → outage → saved',
      posts: st.posts.length,
      lookups: st.lookups,
    })
    await context.close()
  }
  // B. 끊긴 뒤 배포 중에 새로고침 → 확인 중 카드 → 서버 복귀 → 대화
  {
    reset()
    const { page, context } = await open()
    const text = '인원은 40명으로 바꿔 줘'
    await sendChat(page, text)
    st.down = true
    st.response.destroy()
    await page.getByText(NOTICE).first().waitFor()
    st.eventOnly = true
    await page.reload()
    await page.getByRole('status').filter({ hasText: NOTICE }).first().waitFor()
    await wait(1000)
    assert.equal(await generationRegion(page).count(), 0, 'B: no generation screen after reload')
    assert.equal(
      await page.getByText('저장된 계획을 불러오지 못했어요').count(),
      0,
      'B: no error card',
    )
    await page.screenshot({ path: path.join(OUT, 'b1-reload-checking.png'), fullPage: true })
    saveTurn(text)
    st.down = false
    await page.getByText('인원을 40명으로 바꿨어요.').first().waitFor({ timeout: 10000 })
    await box(page).waitFor()
    assert.equal(await box(page).inputValue(), '')
    assert.equal(st.posts.length, 1)
    await page.screenshot({ path: path.join(OUT, 'b2-reload-recovered.png'), fullPage: true })
    results.push({
      case: 'B reload during outage → saved',
      posts: st.posts.length,
      lookups: st.lookups,
    })
    await context.close()
  }
  // C. 서버에 닿지 않은 채팅 → not_saved → 원래 문장을 입력창에
  {
    reset()
    const { page, context } = await open()
    const text = '장소는 강릉으로 바꿔 줘'
    st.lookup = { status: 'not_saved', result: null }
    await sendChat(page, text)
    st.response.destroy()
    await page
      .getByText('연결이 끊긴 요청은 처리되지 않았어요. 다시 보내 주세요.')
      .waitFor({ timeout: 10000 })
    assert.equal(await generationRegion(page).count(), 0)
    assert.equal(await box(page).inputValue(), text, 'C: original text restored')
    assert.equal(await box(page).getAttribute('readonly'), null)
    await page.screenshot({ path: path.join(OUT, 'c-not-saved.png'), fullPage: true })
    results.push({ case: 'C not_saved → text restored', posts: st.posts.length })
    await context.close()
  }
  // D. 채팅이 초안 생성을 시작한 뒤 끊김 → 지금처럼 초안 생성 화면
  {
    reset()
    const { page, context } = await open()
    await sendChat(page, '이대로 초안 만들어 줘')
    st.response.write(
      line('progress', {
        operationId: 'g',
        kind: 'generation_started',
        status: 'running',
        text: '계획 초안을 만들고 있어요',
      }),
    )
    await page.getByRole('heading', { name: '초안을 만들고 있어요', exact: true }).waitFor()
    st.down = true
    st.response.destroy()
    await page.getByRole('heading', { name: '처리 결과를 확인하고 있어요', exact: true }).waitFor()
    assert.equal(
      await generationRegion(page).count(),
      1,
      'D: generation screen kept for started generation',
    )
    await page.screenshot({
      path: path.join(OUT, 'd-chat-generation-checking.png'),
      fullPage: true,
    })
    results.push({
      case: 'D chat generation_started → cut → generation screen',
      posts: st.posts.length,
    })
    await context.close()
  }
  // E. 버튼 생성이 끊김 → 지금처럼 초안 생성 화면
  {
    reset()
    const { page, context } = await open()
    await page.getByRole('button', { name: '이 조건으로 초안 만들기', exact: true }).click()
    await waitStream()
    st.down = true
    st.response.destroy()
    await page.getByRole('heading', { name: '처리 결과를 확인하고 있어요', exact: true }).waitFor()
    assert.equal(await generationRegion(page).count(), 1)
    results.push({ case: 'E button generation → cut → generation screen', posts: st.posts.length })
    await context.close()
  }
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ passed: results.length, results }, null, 2))
} finally {
  st.response?.destroy()
  await browser.close()
  server.close()
}
