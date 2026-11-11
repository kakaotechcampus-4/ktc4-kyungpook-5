// Use a synthetic-only API/DB. Real runs create new events; fixtures never replace model results in real runs.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import http from 'node:http'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const session = JSON.parse(await fs.readFile(process.env.GENERATION_TEST_SESSION, 'utf8'))
const origin = process.env.GENERATION_UI_ORIGIN || 'http://127.0.0.1:5176'
const api = process.env.GENERATION_API_ORIGIN || 'http://127.0.0.1:8005'
const evidence = path.resolve(process.env.GENERATION_EVIDENCE || 'docs/evidence/326')
await fs.mkdir(evidence, { recursive: true })
const browser = await chromium.launch({
  headless: true,
  ...(process.env.P2_BROWSER_PATH ? { executablePath: process.env.P2_BROWSER_PATH } : {}),
})
const errors = [],
  reports = [],
  scenarios = new Map()
const draft = {
  conditions: {
    title: '가을 운영진 MT',
    eventType: 'MT',
    headcount: 30,
    feePerPerson: 50000,
    budgetTotal: 1500000,
    startDate: '2026-11-28',
    endDate: '2026-11-29',
    location: '경주',
  },
  conditionMeta: {},
  deferredTopics: [],
}
const step = (id) => ({
  id,
  code: 'EVENT_DAY',
  name: '행사 당일',
  actor: 'MANUAL',
  stepOrder: 1,
  startsAt: null,
  deadline: null,
  version: 1,
  actions: [],
})
const envelope = (data) => JSON.stringify({ data, meta: null })
const eventLine = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', origin)
  res.setHeader('Access-Control-Allow-Headers', 'authorization,content-type,idempotency-key,accept')
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
  if (req.method === 'OPTIONS') {
    res.end()
    return
  }
  const match = req.url.match(/\/events\/([^/]+)\/plan(.*)/)
  const s = match && scenarios.get(match[1])
  if (!s) {
    res.writeHead(404)
    res.end()
    return
  }
  const suffix = match[2]
  if (req.method === 'POST') {
    let body = ''
    for await (const chunk of req) body += chunk
    s.posts.push({ path: suffix, key: req.headers['idempotency-key'], body: JSON.parse(body) })
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' })
    res.flushHeaders()
    s.response = res
    return
  }
  if (s.saved && s.failReads && suffix === '/steps/snapshot') {
    res.writeHead(500, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ error: { code: 'INTERNAL_ERROR', message: 'fixture read failure' } }))
    return
  }
  const steps = s.saved && !s.stale ? [step('new-' + s.id)] : s.old ? [step('old-' + s.id)] : []
  const revision = s.saved && !s.stale ? (s.later ? 2 : 1) : 0
  const screen = {
    draft,
    baseRevision: revision,
    planRevision: revision,
    generationReadiness: { canGenerate: true, reasons: [] },
    warnings: [],
    excludedSteps: [],
    review: null,
    summary: { totalSteps: steps.length, aiSteps: 0, approvalSteps: 0, manualSteps: steps.length },
  }
  const data =
    suffix === '/steps/snapshot'
      ? { baseRevision: revision, planRevision: revision, steps }
      : suffix === '/steps'
        ? steps
        : suffix === '/messages'
          ? s.messages
          : screen
  res.writeHead(200, { 'Content-Type': 'application/json' })
  res.end(envelope(data))
})
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
const fixtureOrigin = `http://127.0.0.1:${server.address().port}`

async function apiRequest(route, method = 'GET', data) {
  const res = await fetch(api + '/api/v1' + route, {
    method,
    headers: { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json' },
    ...(data ? { body: JSON.stringify(data) } : {}),
  })
  assert.ok(res.ok, `${method} ${route}: HTTP ${res.status}`)
  return (await res.json()).data
}
async function pageContext() {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  await context.addInitScript(({ token, clubId }) => {
    localStorage.setItem('unyounghae_access_token', token)
    localStorage.setItem('unyounghae_selected_club_id', clubId)
  }, session)
  const page = await context.newPage()
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('requestfailed', (r) =>
    console.log('request failed', new URL(r.url()).pathname, r.failure()?.errorText),
  )
  return { page, context }
}
async function fixture({ old = false } = {}) {
  const event = await apiRequest('/events', 'POST', { clubId: session.clubId })
  const s = {
    id: event.id,
    old,
    posts: [],
    messages: [],
    saved: false,
    response: null,
    failReads: false,
    stale: false,
  }
  scenarios.set(event.id, s)
  const { page, context } = await pageContext()
  await page.route(new RegExp(`/api/v1/events/${event.id}/plan(?:/.*)?$`), (route) =>
    route.continue({ url: fixtureOrigin + new URL(route.request().url()).pathname }),
  )
  await page.goto(`${origin}/planning?eventId=${event.id}&stage=conditions`)
  await page
    .getByRole('button', {
      name: old ? '이 조건으로 다시 만들기' : '이 조건으로 초안 만들기',
      exact: true,
    })
    .waitFor({ timeout: 10000 })
    .catch(async (error) => {
      await page.screenshot({ path: '/private/tmp/326-fixture-debug.png' })
      console.log('fixture page', page.url(), await page.locator('body').innerText())
      throw error
    })
  s.start = () =>
    s.response.write(
      eventLine('progress', {
        operationId: 'gen',
        kind: 'generation_started',
        status: 'running',
        text: '실제 생성 시작',
      }),
    )
  s.finish = (status = 'completed') =>
    s.response.write(
      eventLine('progress', {
        operationId: 'gen',
        kind: 'generation_finished',
        status,
        text: '생성 결과',
      }),
    )
  s.done = (status = 'generated', reason = null) => {
    s.saved = status === 'generated'
    const result = {
      reply: '처리했어요',
      draft,
      changedFields: [],
      recordLookup: null,
      generationReadiness: { canGenerate: true, reasons: [] },
      generationResult: status ? { status, reason } : null,
      baseRevision: 1,
    }
    s.response.end(eventLine('done', result))
  }
  return { s, page, context }
}
const waitTitle = (page, name) => page.getByRole('heading', { name, exact: true }).waitFor()
const shot = (page, name) =>
  page.screenshot({ path: path.join(evidence, `${name}.png`), fullPage: true })
async function clickGenerate(page, old = false) {
  await page
    .getByRole('button', {
      name: old ? '이 조건으로 다시 만들기' : '이 조건으로 초안 만들기',
      exact: true,
    })
    .click()
  await waitTitle(page, '생성 요청을 확인하고 있어요')
}
async function waitPost(s) {
  for (let i = 0; i < 100 && !s.response; i++) await new Promise((r) => setTimeout(r, 20))
  assert.ok(s.response, 'stream opened')
}
async function assertNoOverflow(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
}

try {
  if (process.env.GENERATION_REAL === '1') {
    for (const kind of (process.env.GENERATION_REAL_KINDS || 'button,chat').split(',')) {
      const resume = kind === 'chat' && process.env.GENERATION_CHAT_EVENT_ID
      const event = resume
        ? { id: resume }
        : await apiRequest('/events', 'POST', { clubId: session.clubId })
      const plan = `/events/${event.id}/plan`
      const conditions = resume
        ? await apiRequest(plan)
        : await apiRequest(plan + '/chat', 'POST', {
            messageId: crypto.randomUUID(),
            baseRevision: 0,
            message:
              '가을 MT를 계획해요. 이름은 가을 운영진 MT, 2026년 11월 28일부터 29일까지 경주에서 30명, 1인 참가비 5만원으로 준비해요. 예산 총액 150만원이고 모든 조건은 확정입니다. ' +
              (kind === 'chat'
                ? '이 조건으로 초안을 만들 수 있는지 알려 주고, 생성 전에 제 동의를 받아 주세요.'
                : '이 조건을 기억하고 아직 초안 생성은 하지 말아주세요.'),
          })
      assert.equal(conditions.generationReadiness.canGenerate, true)
      const { page, context } = await pageContext()
      const posts = [],
        events = []
      page.on('request', (r) => {
        if (r.method() === 'POST' && /\/plan\/(chat|generate)\/stream/.test(r.url()))
          posts.push({ url: r.url(), key: r.headers()['idempotency-key'] })
      })
      page.on('response', async (r) => {
        if (/\/plan\/(chat|generate)\/stream/.test(r.url()))
          events.push(await r.text().catch(() => ''))
      })
      await page.goto(`${origin}/planning?eventId=${event.id}&stage=conditions`)
      await page.getByRole('button', { name: '이 조건으로 초안 만들기', exact: true }).waitFor()
      if (kind === 'button') await clickGenerate(page)
      else {
        await page
          .getByRole('textbox', { name: '계획 대화 답변' })
          .fill(
            resume
              ? '네, 생성해 주세요. 초안 생성 보류를 해제하고 지금 확정된 조건으로 만들어 주세요.'
              : '네, 지금 확정한 조건으로 행사 계획 초안을 만들어 주세요.',
          )
        await page.getByRole('textbox', { name: '계획 대화 답변' }).press('Enter')
      }
      await page
        .getByRole('heading', { name: '초안을 만들고 있어요', exact: true })
        .waitFor({ timeout: 180000 })
      await shot(page, `real-${kind}-generating-1280`)
      await page
        .getByRole('heading', { name: '준비 순서', exact: true })
        .waitFor({ timeout: 180000 })
      assert.match(page.url(), /stage=review/)
      assert.equal(posts.length, 1)
      assert.equal(await page.locator(':focus').innerText(), '가을 운영진 MT')
      const steps = await apiRequest(plan + '/steps/snapshot')
      assert.ok(steps.steps.length > 0)
      assert.equal(steps.baseRevision, conditions.baseRevision + 1)
      await shot(page, `real-${kind}-p2-1280`)
      await page.reload()
      await waitTitle(page, '준비 순서')
      assert.equal(posts.length, 1)
      assert.equal(
        await page
          .getByRole('status')
          .filter({ hasText: /계획 초안 \d+단계를 만들었어요/ })
          .count(),
        0,
      )
      assert.ok(events.join('').includes('generation_started'))
      assert.ok(events.join('').includes('"status": "generated"'))
      reports.push({
        type: 'real-model-http-db',
        kind,
        eventId: event.id,
        generationPosts: posts.length,
        baseRevision: steps.baseRevision,
        planRevision: steps.planRevision,
        stepCount: steps.steps.length,
      })
      await fs.writeFile(
        path.join(evidence, 'verification-real.json'),
        JSON.stringify({ reports, browserErrors: errors }, null, 2) + '\n',
      )
      await context.close()
      console.log(`real ${kind}: stream → saved ${steps.steps.length} steps → P2 → reload; 1 POST`)
    }
  }
  if (process.env.GENERATION_FIXTURES !== '0') {
    {
      const { s, page, context } = await fixture()
      await clickGenerate(page)
      await waitPost(s)
      await shot(page, 'fixture-requesting-1280')
      s.start()
      await waitTitle(page, '초안을 만들고 있어요')
      assert.equal(await page.locator(':focus').innerText(), '초안을 만들고 있어요')
      for (const width of [1440, 1280, 1024, 390, 320]) {
        await page.setViewportSize({ width, height: 800 })
        await assertNoOverflow(page)
        await shot(page, `fixture-generating-${width}`)
      }
      await page.emulateMedia({ reducedMotion: 'reduce' })
      assert.equal(
        await page
          .locator('[aria-hidden="true"].animate-pulse')
          .evaluate((el) => getComputedStyle(el).animationName),
        'none',
      )
      await page.setViewportSize({ width: 1280, height: 800 })
      s.finish('failed')
      await waitTitle(page, '생성 결과를 확인하고 있어요')
      s.start()
      await waitTitle(page, '초안을 만들고 있어요')
      s.finish()
      await waitTitle(page, '생성 결과를 확인하고 있어요')
      assert.match(page.url(), /stage=conditions/)
      await shot(page, 'fixture-verifying-1280')
      s.done()
      await waitTitle(page, '준비 순서')
      assert.equal(s.posts.length, 1)
      reports.push({ type: 'fixture', case: 'button-states-responsive-motion-focus', posts: 1 })
      await context.close()
    }
    for (const mode of ['read-failure', 'stale-snapshot']) {
      const { s, page, context } = await fixture({ old: true })
      await clickGenerate(page, true)
      await waitPost(s)
      s.start()
      await waitTitle(page, '초안을 만들고 있어요')
      s.finish()
      s.failReads = mode === 'read-failure'
      s.stale = mode === 'stale-snapshot'
      s.done()
      await waitTitle(
        page,
        mode === 'read-failure'
          ? '초안은 저장됐지만 불러오지 못했어요'
          : '새 초안을 확인하지 못했어요',
      )
      await shot(page, `fixture-${mode}-1280`)
      await page.reload()
      await waitTitle(
        page,
        mode === 'read-failure'
          ? '초안은 저장됐지만 불러오지 못했어요'
          : '새 초안을 확인하지 못했어요',
      )
      assert.equal(s.posts.length, 1)
      s.failReads = false
      s.stale = false
      await page.getByRole('button', { name: '초안 다시 불러오기', exact: true }).focus()
      await page.keyboard.press('Enter')
      await waitTitle(page, '준비 순서')
      assert.equal(s.posts.length, 1)
      assert.equal(await page.locator(':focus').innerText(), draft.conditions.title)
      reports.push({ type: 'fixture', case: mode + '-reload-get-only-recovery', posts: 1 })
      await context.close()
    }
    for (const mode of ['changed', 'leave-and-return', 'storage-unavailable']) {
      const { s, page, context } = await fixture()
      if (mode === 'storage-unavailable') {
        await page.evaluate(() => {
          const original = Storage.prototype.setItem
          Storage.prototype.setItem = function (...args) {
            if (this === sessionStorage)
              throw new DOMException('fixture unavailable', 'QuotaExceededError')
            return original.apply(this, args)
          }
        })
        await page.getByRole('button', { name: '이 조건으로 초안 만들기', exact: true }).click()
        await page.getByRole('alert').filter({ hasText: '임시 저장 기능' }).waitFor()
        assert.equal(s.posts.length, 0)
      } else {
        const historyLength = await page.evaluate(() => history.length)
        await page.getByRole('button', { name: '이 조건으로 초안 만들기', exact: true }).focus()
        await page.keyboard.press('Enter')
        await page.keyboard.press('Enter')
        await waitPost(s)
        s.start()
        await waitTitle(page, '초안을 만들고 있어요')
        if (mode === 'leave-and-return') {
          const other = await apiRequest('/events', 'POST', { clubId: session.clubId })
          await page.evaluate((id) => {
            history.pushState({}, '', `/planning?eventId=${id}&stage=conditions`)
            dispatchEvent(new PopStateEvent('popstate'))
          }, other.id)
          await page.getByRole('link', { name: '요청한 계획 확인하기', exact: true }).waitFor()
          s.done()
          await page.waitForFunction(() =>
            Object.keys(sessionStorage).some(
              (k) =>
                k.startsWith('planning-request:') &&
                JSON.parse(sessionStorage.getItem(k)).result?.generationResult?.status ===
                  'generated',
            ),
          )
          assert.ok(page.url().includes(other.id))
          await page.getByRole('link', { name: '요청한 계획 확인하기', exact: true }).click()
          await waitTitle(page, '초안은 저장됐지만 불러오지 못했어요')
          await page.getByRole('button', { name: '초안 다시 불러오기', exact: true }).click()
        } else {
          s.later = true
          s.done()
          await waitTitle(page, '생성 뒤 계획에 다른 변경이 있어요')
          await page.getByRole('button', { name: '현재 계획 확인하기', exact: true }).click()
        }
        await waitTitle(page, '준비 순서')
        assert.equal(s.posts.length, 1)
        if (mode === 'changed') {
          assert.equal(await page.evaluate(() => history.length), historyLength)
          assert.equal(
            await page
              .getByRole('status')
              .filter({ hasText: /계획 초안 \d+단계를 만들었어요/ })
              .count(),
            0,
          )
        }
      }
      reports.push({ type: 'fixture', case: mode, posts: s.posts.length })
      await context.close()
    }
    for (const mode of [
      'clarification',
      'failed',
      'save-conflict',
      'unknown',
      'chat-consultation',
      'chat-generation',
    ]) {
      const { s, page, context } = await fixture({ old: true })
      if (mode.startsWith('chat-')) {
        await page.getByRole('textbox', { name: '계획 대화 답변' }).fill('테스트 요청')
        await page.getByRole('textbox', { name: '계획 대화 답변' }).press('Enter')
      } else await clickGenerate(page, true)
      await waitPost(s)
      if (mode === 'chat-consultation') {
        s.response.write(
          eventLine('progress', {
            operationId: 'search',
            kind: 'search_started',
            status: 'running',
            text: '기록 검색 중',
          }),
        )
        s.response.write(
          eventLine('progress', {
            operationId: 'search',
            kind: 'search_finished',
            status: 'empty',
            text: '찾은 기록 없음',
          }),
        )
      }
      if (mode === 'chat-consultation' || mode === 'clarification') {
        assert.equal(
          await page.getByRole('region', { name: '초안 생성 상태' }).count(),
          mode === 'clarification' ? 1 : 0,
        )
        s.done(
          mode === 'clarification' ? 'needs_clarification' : null,
          '행사 날짜를 확인해 주세요.',
        )
        if (mode === 'clarification') {
          // 생성 화면에서 이유를 먼저 보이고, 「대화로 돌아가기」로 P1의 안내로 돌아간다.
          await waitTitle(page, '초안을 만들기 전에 확인할 내용이 있어요')
          await page.getByRole('button', { name: '대화로 돌아가기', exact: true }).click()
          await page.getByRole('button', { name: '조건 이어서 정하기', exact: true }).click()
          assert.equal(await page.locator(':focus').getAttribute('aria-label'), '계획 대화 답변')
        } else await page.getByRole('button', { name: '보내기', exact: true }).waitFor()
      } else {
        s.start()
        await waitTitle(page, '초안을 만들고 있어요')
        s.finish(mode === 'failed' ? 'failed' : 'completed')
        // 실패한 생성은 저장할 것이 없어 「초안 작성」에 머문다.
        await waitTitle(
          page,
          mode === 'failed' ? '초안을 만들고 있어요' : '생성 결과를 확인하고 있어요',
        )
        if (mode === 'unknown') {
          s.response.destroy()
          await waitTitle(page, '처리 결과를 확인하지 못했어요')
          await shot(page, 'fixture-unknown-1280')
          await page.reload()
          await waitTitle(page, '처리 결과를 확인하지 못했어요')
          assert.equal(await page.getByRole('button', { name: /다시 만들기|다시 생성/ }).count(), 0)
          assert.equal(await page.locator('#planning-draft').isDisabled(), true)
        } else if (mode === 'save-conflict') {
          s.response.end(
            eventLine('error', { code: 'VERSION_CONFLICT', message: 'fixture concurrent edit' }),
          )
          await waitTitle(page, '초안 생성을 마치지 못했어요')
          await page.getByRole('button', { name: '대화로 돌아가기', exact: true }).click()
          await page.getByRole('alert').filter({ hasText: '저장하지 못했어요' }).waitFor()
          await page.getByRole('button', { name: '저장된 계획 다시 확인', exact: true }).click()
          assert.equal(s.posts.length, 1)
          await shot(page, 'fixture-save-conflict-1280')
        } else if (mode === 'failed') {
          s.done('failed', '생성된 초안이 단계·날짜·근거 검증을 통과하지 못했어요.')
          await waitTitle(page, '초안을 완성하지 못했어요')
          await shot(page, 'fixture-generation-failed-1280')
          await page.getByRole('button', { name: '대화로 돌아가기', exact: true }).click()
        } else {
          s.done()
          // 완료를 생성 화면에서 잠시 보인 뒤(DONE_HOLD_MS) 계획 검토로 넘어간다.
          await waitTitle(page, '초안이 준비됐어요')
          await waitTitle(page, '준비 순서')
          assert.equal(await page.locator(':focus').innerText(), draft.conditions.title)
        }
      }
      assert.equal(s.posts.length, 1)
      if (['clarification', 'failed', 'save-conflict'].includes(mode)) {
        await page.getByRole('link', { name: '기존 초안 검토하기', exact: true }).click()
        await waitTitle(page, '준비 순서')
        assert.equal(s.saved, false)
        assert.equal(await page.getByRole('heading', { name: '행사 당일', exact: true }).count(), 1)
      }
      reports.push({ type: 'fixture', case: mode, posts: 1 })
      await context.close()
    }
  }
  assert.deepEqual(errors, [])
  await fs.writeFile(
    path.join(
      evidence,
      process.env.GENERATION_REAL === '1' ? 'verification-real.json' : 'verification-fixtures.json',
    ),
    JSON.stringify({ reports, browserErrors: errors }, null, 2) + '\n',
  )
  console.log(JSON.stringify({ passed: reports.length, reports }, null, 2))
} finally {
  for (const s of scenarios.values()) s.response?.destroy()
  await browser.close()
  await new Promise((resolve) => server.close(resolve))
}
