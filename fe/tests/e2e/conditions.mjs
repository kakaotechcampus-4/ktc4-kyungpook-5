// Product FE + synthetic local account/event. Plan/SSE/record responses below are fixtures.
// Actual-model generation/save/P2 regression remains in generation.mjs (GENERATION_REAL=1).
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const session = JSON.parse(await fs.readFile(process.env.CONDITIONS_TEST_SESSION, 'utf8'))
const origin = process.env.CONDITIONS_UI_ORIGIN || 'http://127.0.0.1:5177'
const api = process.env.CONDITIONS_API_ORIGIN || 'http://127.0.0.1:8005'
const evidence = path.resolve(process.env.CONDITIONS_EVIDENCE || 'docs/evidence/323')
await fs.mkdir(evidence, { recursive: true })
const response = await fetch(api + '/api/v1/events', {
  method: 'POST',
  headers: { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ clubId: session.clubId }),
})
assert.equal(response.status, 201)
const event = (await response.json()).data
const browser = await chromium.launch({
  headless: true,
  ...(process.env.P2_BROWSER_PATH ? { executablePath: process.env.P2_BROWSER_PATH } : {}),
})
const errors = [],
  reports = [],
  posts = [],
  unhandled = []
let revision = 0,
  hasPrevious = false,
  releaseChat
let readiness = { canGenerate: true, reasons: [] }
const draft = {
  conditions: {
    title: '봄 MT',
    eventType: 'MT',
    headcount: 32,
    feePerPerson: 0,
    startDate: null,
    endDate: null,
    location: null,
    budgetTotal: null,
  },
  conditionMeta: {
    headcount: {
      status: 'tentative',
      evidenceMessageId: 'user-1',
      evidenceQuote: '인원은 대략 32명 정도야',
    },
  },
  deferredTopics: ['dates', 'location'],
}
const source = {
  recordId: 'synthetic-323-record',
  fileName: '2025 MT 준비표.csv',
  location: { label: '준비 일정' },
}
const record = (content) => ({
  status: 'available',
  reason: null,
  result: {
    facts: [
      { content, sources: [source] },
      { content: '참가 신청 마감 후 인원을 확정했어요.', sources: [source] },
    ],
    conflicts: [],
    notFound: [],
  },
})
const history = [
  { revision: 1, lookup: record('지난 MT는 숙소와 이동 수단을 정한 뒤 참가 신청을 받았어요.') },
  { revision: 0, lookup: record('지난 MT의 참가비 기록이에요.') },
]
let messages = [
  {
    id: 'user-1',
    role: 'USER',
    content:
      '봄 MT를 준비해. 인원은 대략 32명 정도야. 참가비는 무료고 날짜와 장소는 나중에 정할게.',
  },
  {
    id: 'assistant-1',
    role: 'ASSISTANT',
    content: '32명은 잠정 인원으로 정리했어요. 오른쪽 조건을 확인해 주세요.',
    quickReplies: [],
  },
]
const steps = () =>
  hasPrevious
    ? [
        {
          id: 'previous-step',
          code: 'EVENT_DAY',
          name: '행사 당일',
          actor: 'MANUAL',
          stepOrder: 1,
          startsAt: null,
          deadline: null,
          version: 1,
          actions: [],
        },
      ]
    : []
const screen = () => ({
  draft,
  baseRevision: revision,
  planRevision: 0,
  generationReadiness: readiness,
  warnings: [],
  excludedSteps: [],
  review: null,
  recordLookupHistory: history,
  summary: {
    totalSteps: steps().length,
    manualSteps: steps().length,
    aiSteps: 0,
    approvalSteps: 0,
  },
})
const json = (data) => ({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({ data, meta: null }),
})
async function open(uiOrigin = origin) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  await context.addInitScript(({ token, clubId }) => {
    localStorage.setItem('unyounghae_access_token', token)
    localStorage.setItem('unyounghae_selected_club_id', clubId)
  }, session)
  const page = await context.newPage()
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route(new RegExp(`/api/v1/events/${event.id}/plan(?:/.*)?$`), async (route) => {
    const request = route.request(),
      suffix = new URL(request.url()).pathname.split('/plan')[1]
    if (request.method() === 'POST') {
      posts.push({ suffix, body: request.postDataJSON() })
      assert.equal(suffix, '/chat/stream', 'conditions test must never generate a plan')
      await new Promise((resolve) => {
        releaseChat = resolve
      })
      draft.conditions.headcount = 40
      draft.conditionMeta.headcount = {
        status: 'specified',
        evidenceMessageId: 'user-2',
        evidenceQuote: '인원은 40명으로 확정됐어.',
      }
      revision++
      messages = [
        ...messages,
        { id: 'user-2', role: 'USER', content: '인원은 40명으로 확정됐어.' },
        {
          id: 'assistant-2',
          role: 'ASSISTANT',
          content: '예상 인원을 40명으로 반영했어요.',
          quickReplies: [],
        },
      ]
      const progress = {
        operationId: 'condition-323',
        kind: 'condition_applied',
        status: 'completed',
        text: '예상 인원을 반영했어요',
        conditionDraft: draft,
      }
      const done = {
        reply: '예상 인원을 40명으로 반영했어요.',
        draft,
        changedFields: ['headcount'],
        recordLookup: null,
        generationReadiness: readiness,
        generationResult: null,
        baseRevision: revision,
      }
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: `event: progress\ndata: ${JSON.stringify(progress)}\n\nevent: done\ndata: ${JSON.stringify(done)}\n\n`,
      })
      return
    }
    if (suffix === '/steps/snapshot')
      return route.fulfill(json({ baseRevision: revision, planRevision: 0, steps: steps() }))
    if (suffix === '/steps') return route.fulfill(json(steps()))
    if (suffix === '/messages') return route.fulfill(json(messages))
    if (suffix === '') return route.fulfill(json(screen()))
    unhandled.push(suffix)
    await route.abort()
  })
  await page.route('**/api/v1/records/synthetic-323-record/file', (route) => {
    assert.ok(route.request().headers().authorization, 'record download retains authentication')
    return route.fulfill({
      status: 200,
      contentType: 'text/csv',
      body: '검토용 합성 자료\n준비 일정,숙소 확인 후 신청\n',
    })
  })
  await page.goto(`${uiOrigin}/planning?eventId=${event.id}&stage=conditions`)
  return { page, context }
}
async function screenshot(page, name) {
  await page.screenshot({ path: path.join(evidence, name + '.png'), fullPage: true })
}
async function ctaOffset(card) {
  return card
    .getByRole('button', { name: /이 조건으로 .*만들기/ })
    .evaluate((el) => el.getBoundingClientRect().top + window.scrollY)
}
try {
  if (process.env.CONDITIONS_BASELINE_ORIGIN) {
    const { page, context } = await open(process.env.CONDITIONS_BASELINE_ORIGIN)
    await page.getByRole('heading', { name: '지금까지 정한 것', exact: true }).waitFor()
    await screenshot(page, 'before-1280')
    await context.close()
  }
  const { page, context } = await open()
  const card = page.getByRole('region', { name: '이번 행사 조건', exact: true })
  await card.waitFor()
  const row = (label) =>
    card.locator('dl > div').filter({ has: page.getByText(label, { exact: true }) })
  assert.match(await row('예상 인원').innerText(), /32명[\s\S]*잠정[\s\S]*인원은 대략 32명 정도야/)
  assert.match(await row('참가비').innerText(), /무료/)
  assert.match(await row('일정').innerText(), /나중에 정해요/)
  assert.equal(
    await card.getByRole('button', { name: '이 조건으로 초안 만들기', exact: true }).isEnabled(),
    true,
  )
  for (const width of [1440, 1280, 1024, 1023, 390, 320]) {
    await page.setViewportSize({ width, height: 800 })
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
    )
    await screenshot(page, `conditions-${width}`)
    reports.push({ type: 'fixture', viewport: { width, height: 800 }, overflow: false })
  }
  await page.setViewportSize({ width: 1280, height: 800 })
  const before = await ctaOffset(card)
  await page.getByRole('button', { name: /확인한 내용 1개 더 보기/ }).click()
  await page.getByText('이전 조회 1건', { exact: true }).click()
  assert.equal(await ctaOffset(card), before, 'records stay after generation action')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '2025 MT 준비표.csv 원본 다운로드' }).first().click()
  assert.equal((await download).suggestedFilename(), '2025 MT 준비표.csv')
  const description = await card
    .getByRole('button', { name: '이 조건으로 초안 만들기', exact: true })
    .getAttribute('aria-describedby')
  assert.ok(await page.locator(`[id="${description}"]`).count())
  await screenshot(page, 'references-expanded-1280')
  await page.getByRole('textbox', { name: '계획 대화 답변' }).fill('인원은 40명으로 확정됐어.')
  await page.getByRole('textbox', { name: '계획 대화 답변' }).press('Enter')
  await page.waitForFunction(() => document.querySelector('button[aria-describedby]')?.disabled)
  assert.equal(
    await card.getByRole('button', { name: '이 조건으로 초안 만들기', exact: true }).isDisabled(),
    true,
  )
  assert.equal(await page.getByRole('region', { name: '초안 생성 상태' }).count(), 0)
  await screenshot(page, 'chat-waiting-1280')
  for (let attempt = 0; attempt < 100 && !releaseChat; attempt++)
    await new Promise((resolve) => setTimeout(resolve, 20))
  assert.ok(releaseChat, 'chat request reached fixture')
  releaseChat()
  await row('예상 인원').getByText('40명', { exact: false }).waitFor()
  assert.doesNotMatch(await row('예상 인원').innerText(), /잠정|대략/)
  await screenshot(page, 'headcount-corrected-1280')
  await page.reload()
  await row('예상 인원').getByText('40명', { exact: false }).waitFor()
  assert.equal(posts.length, 1)
  reports.push({
    type: 'fixture',
    case: 'conditions-correction-wait-and-reload',
    chatPosts: posts.length,
  })
  readiness = { canGenerate: false, reasons: ['location_unanswered'] }
  draft.conditions.location = null
  draft.deferredTopics = ['dates']
  await page.reload()
  await card.getByText('장소를 알려 주거나 아직 미정이라고 말해 주세요.').waitFor()
  assert.equal(
    await card.getByRole('button', { name: '이 조건으로 초안 만들기', exact: true }).isDisabled(),
    true,
  )
  assert.match(await row('장소').innerText(), /아직이에요/)
  await screenshot(page, 'blocked-1280')
  readiness = null
  await page.reload()
  await card.getByText(/생성 가능 상태를 확인하지 못했어요/).waitFor()
  assert.equal(
    await card.getByRole('button', { name: '이 조건으로 초안 만들기', exact: true }).isDisabled(),
    true,
  )
  readiness = { canGenerate: false, reasons: ['future_server_reason'] }
  await page.reload()
  await card.getByText('추가 정보를 확인해 주세요.').waitFor()
  assert.equal(
    await card.getByRole('button', { name: '이 조건으로 초안 만들기', exact: true }).isDisabled(),
    true,
  )
  readiness = { canGenerate: true, reasons: [] }
  hasPrevious = true
  await page.reload()
  const previous = card.getByRole('link', { name: '기존 초안 검토하기', exact: true })
  await previous.waitFor()
  assert.match(await card.innerText(), /직접 수정한 내용이 새 초안으로 바뀌어요/)
  assert.equal(await page.getByRole('button', { name: '행사 시작', exact: true }).count(), 0)
  assert.equal(await page.getByRole('heading', { name: '계획 초안', exact: true }).count(), 0)
  await previous.focus()
  await page.keyboard.press('Enter')
  await page.getByRole('heading', { name: '준비 순서', exact: true }).waitFor()
  assert.equal(posts.length, 1, 'opening P2 never generates')
  await page.goBack()
  await card.waitFor()
  await screenshot(page, 'previous-plan-1280')
  reports.push({
    type: 'fixture',
    case: 'server-only-readiness-and-previous-p2-entry',
    generationPosts: 0,
  })
  draft.conditions.title =
    '봄 MT를 준비하는 운영진과 신입 회원이 함께하는 아주 긴 행사 이름 '.repeat(3)
  draft.conditions.location = '장소 후보를 확인하는 중인 긴 건물명과 상세 주소 '.repeat(6)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 390, height: 800 })
  await page.reload()
  await card.waitFor()
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
  assert.ok(await row('행사 이름').evaluate((el) => !el.querySelector('.truncate')))
  await screenshot(page, 'long-conditions-390')
  await context.close()
  const fresh = await open()
  await fresh.page.goto(origin + '/planning')
  const empty = fresh.page.getByRole('region', { name: '이번 행사 조건', exact: true })
  await empty.getByText('어떤 행사를 준비하는지 토리에게 알려 주세요.').waitFor()
  assert.equal(
    await empty.getByRole('button', { name: '이 조건으로 초안 만들기', exact: true }).isDisabled(),
    true,
  )
  await fresh.page.getByText('과거 기록을 찾아보면 여기에 내용과 출처가 남아요.').waitFor()
  await screenshot(fresh.page, 'empty-1280')
  await fresh.context.close()
  assert.deepEqual(errors, [])
  assert.deepEqual(unhandled, [])
  await fs.writeFile(
    path.join(evidence, 'verification-conditions.json'),
    JSON.stringify({ reports, browserErrors: errors }, null, 2) + '\n',
  )
  console.log(JSON.stringify({ passed: reports.length, reports, browserErrors: errors }, null, 2))
} finally {
  await browser.close()
}
