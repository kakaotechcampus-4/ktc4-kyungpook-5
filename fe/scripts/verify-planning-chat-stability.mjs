// Run against a local Vite server; every API response and SSE frame is a fixture.
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright')
import fs from 'node:fs/promises'
import assert from 'node:assert/strict'
const baseUrl = process.env.PLANNING_BASE_URL ?? 'http://127.0.0.1:5182'
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
})
try {
  const width = Number(process.argv[2] ?? 1440)
  const page = await browser.newPage({ viewport: { width, height: 900 } })
  let revision = 0
  let created = 0
  let streamed = 0
  const errors = []
  const messages = []
  const draft = {
    conditions: {
      title: '가을 MT',
      eventType: 'MT',
      headcount: 30,
      feePerPerson: null,
      startDate: null,
      endDate: null,
      location: null,
      budgetTotal: null,
    },
    conditionMeta: {},
    deferredTopics: [],
  }
  const screen = () => ({
    draft,
    baseRevision: revision,
    planRevision: 0,
    generationReadiness: { canGenerate: true, reasons: [] },
    warnings: [],
    summary: { totalSteps: 0, aiSteps: 0, approvalSteps: 0, manualSteps: 0 },
    review: null,
    recordLookupHistory: [],
  })
  page.on('pageerror', (error) => errors.push(error.message))
  await page.exposeFunction('traceNextTurn', async (body) => {
    streamed++
    if (body.message === '실패 시나리오')
      return [{ event: 'error', data: { code: 'AI_UNAVAILABLE', message: 'fixture failure' } }]
    revision++
    const reply =
      `확인했어요 ${revision}.\n\n` +
      Array.from(
        { length: 5 },
        (_, i) =>
          `${i + 1}. 동아리 구성원이 함께 준비할 수 있도록 일정과 장소를 먼저 확인해요. 필요한 준비물을 정하고 역할을 나누면 행사 준비를 차근차근 진행할 수 있어요.`,
      ).join('\n\n')
    messages.push(
      { id: `user-${revision}`, role: 'USER', content: body.message },
      { id: `reply-${revision}`, role: 'ASSISTANT', content: reply },
    )
    const progress = [
      {
        operationId: `condition-${revision}`,
        kind: 'condition_applied',
        status: 'completed',
        text: '행사 조건을 반영했어요',
        conditionDraft: draft,
      },
      {
        operationId: `search-${revision}`,
        kind: 'search_finished',
        status: 'completed',
        text: '참고할 기록을 찾았어요',
      },
    ]
    const result = {
      ...screen(),
      reply,
      changedFields: [],
      recordLookup: null,
      generationResult: null,
    }
    return [
      { event: 'progress', data: progress[0] },
      { event: 'progress', data: progress[1] },
      ...[reply.slice(0, 100), reply.slice(100, 250), reply.slice(250)].map((text) => ({
        event: 'reply_delta',
        data: { text },
      })),
      { event: 'done', data: result },
    ]
  })
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    await new Promise((resolve) => setTimeout(resolve, 80))
    let data
    if (path.endsWith('/me'))
      data = {
        id: 'trace-user',
        email: 'preview@example.com',
        clubs: [{ id: 'trace-club', name: '예시 동아리', role: 'OWNER' }],
      }
    else if (path.endsWith('/events') && request.method() === 'POST') {
      created++
      data = { id: 'trace-event' }
    } else if (path.endsWith('/drafts'))
      data = revision
        ? [
            {
              id: 'trace-event',
              title: '가을 MT',
              createdAt: '2026-11-05T00:00:00Z',
              savedAt: null,
            },
          ]
        : []
    else if (path.endsWith('/steps/snapshot'))
      data = { baseRevision: revision, planRevision: 0, steps: [] }
    else if (path.endsWith('/messages')) data = messages
    else if (path.endsWith('/steps')) data = []
    else if (path.endsWith('/plan')) data = screen()
    else if (path.endsWith('/trace-event'))
      data = {
        id: 'trace-event',
        title: '가을 MT',
        status: 'PLANNING',
        startDate: null,
        endDate: null,
        location: null,
        headcount: 30,
        currentStep: null,
        dday: null,
      }
    else throw new Error(`Unexpected ${request.method()} ${path}`)
    await route.fulfill({ json: { data, meta: null } })
  })
  await page.addInitScript(() => {
    localStorage.setItem('unyounghae_access_token', 'trace-only')
    localStorage.setItem('unyounghae_selected_club_id', 'trace-club')
    const original = window.fetch
    window.fetch = async (url, init) => {
      if (!String(url).endsWith('/chat/stream')) return original(url, init)
      const frames = await window.traceNextTurn(JSON.parse(init.body))
      window.traceMarks.push({ name: 'stream-start', at: performance.now() })
      return new Response(
        new ReadableStream({
          start(controller) {
            let i = 0
            const tick = () => {
              const frame = frames[i++]
              if (!frame) {
                controller.close()
                return
              }
              if (frame.event === 'done')
                window.traceMarks.push({ name: 'done', at: performance.now() })
              controller.enqueue(
                new TextEncoder().encode(
                  `event: ${frame.event}\ndata: ${JSON.stringify(frame.data)}\n\n`,
                ),
              )
              setTimeout(tick, 120)
            }
            setTimeout(tick, 120)
          },
        }),
        { headers: { 'Content-Type': 'text/event-stream' } },
      )
    }
    window.traceMarks = []
    window.traceSamples = []
    const ids = new WeakMap()
    let id = 0
    const identify = (node) => {
      if (!node) return null
      if (!ids.has(node)) ids.set(node, ++id)
      return ids.get(node)
    }
    const sample = () => {
      const panel = document.querySelector('[aria-label="계획 대화 내용"]')
      const input = document.querySelector('#planning-chat-answer')
      const paragraphs = panel
        ? [...panel.querySelectorAll('p')].filter((p) => p.textContent.startsWith('확인했어요'))
        : []
      const reply = paragraphs.at(-1)
      window.traceSamples.push({
        t: performance.now(),
        panel: identify(panel),
        input: identify(input),
        reply: identify(reply),
        top: panel?.getBoundingClientRect().top,
        height: panel?.clientHeight,
        scroll: panel?.scrollTop,
        full: panel?.scrollHeight,
        replyTop: reply?.getBoundingClientRect().top,
        replyBottom: reply?.getBoundingClientRect().bottom,
        inputWidth: input?.clientWidth,
        inputHeight: input?.clientHeight,
        inputTop: input?.getBoundingClientRect().top,
        focused: document.activeElement === input,
        foreign: document.body.innerText.includes('다른 계획의 처리 결과'),
        noDraft: document.body.innerText.includes('저장된 초안이 없어요'),
        loading: document.body.innerText.includes('저장된 계획을 불러오는 중'),
        status: document.querySelector('p[role="status"]:not(.sr-only)')?.textContent,
        windowScroll: window.scrollY,
      })
      requestAnimationFrame(sample)
    }
    requestAnimationFrame(sample)
  })
  await page.goto(`${baseUrl}/planning`)
  const input = page.getByRole('textbox', { name: '계획 대화 답변' })
  await input.waitFor()
  const turns = []
  for (let n = 1; n <= 3; n++) {
    await input.fill(`행사 ${n}번째 조건을 확인해 주세요`)
    await page.evaluate(() => window.traceMarks.push({ name: 'submit', at: performance.now() }))
    await input.press('Enter')
    await page.waitForFunction(() => !document.querySelector('#planning-chat-answer')?.readOnly, {
      timeout: 15000,
    })
    await new Promise((resolve) => setTimeout(resolve, 1200))
    turns.push(
      await page.evaluate(() => {
        const submit = window.traceMarks.filter((m) => m.name === 'submit').at(-1).at
        const done = window.traceMarks.filter((m) => m.name === 'done').at(-1)?.at
        const samples = window.traceSamples.filter((s) => s.t >= submit)
        const after = samples.filter((s) => s.t > done + 250)
        const range = (list, key) => {
          const values = list.map((s) => s[key]).filter((v) => typeof v === 'number')
          return values.length ? [Math.min(...values), Math.max(...values)] : []
        }
        return {
          nodes: {
            panel: [...new Set(samples.map((s) => s.panel))],
            input: [...new Set(samples.map((s) => s.input))],
            reply: [...new Set(samples.map((s) => s.reply).filter(Boolean))],
          },
          panelTop: range(samples, 'top'),
          panelHeight: range(samples, 'height'),
          inputWidth: range(samples, 'inputWidth'),
          inputTop: range(samples, 'inputTop'),
          focused: samples.every((s) => s.focused),
          afterReplyTop: range(after, 'replyTop'),
          afterScroll: range(after, 'scroll'),
          afterFull: range(after, 'full'),
          foreignBanner: samples.some((s) => s.foreign),
          loading: samples.some((s) => s.loading),
          visibleBusyStatus: samples.some((s) => s.status?.includes('준비하고')),
          last: samples.at(-1),
        }
      }),
    )
  }
  for (const [n, turn] of turns.entries()) {
    assert.equal(turn.nodes.panel.length, 1, `turn ${n + 1}: panel remounted`)
    assert.equal(turn.nodes.input.length, 1, `turn ${n + 1}: input remounted`)
    assert.equal(turn.nodes.reply.length, n === 0 ? 1 : 2, `turn ${n + 1}: reply was replaced`)
    for (const key of [
      'panelTop',
      'panelHeight',
      'inputWidth',
      'inputTop',
      'afterReplyTop',
      'afterScroll',
      'afterFull',
    ])
      assert.equal(turn[key][0], turn[key][1], `turn ${n + 1}: ${key} changed`)
    assert.equal(turn.foreignBanner, false)
    assert.equal(turn.loading, false)
    assert.equal(turn.focused, true)
  }
  // 사용자가 이전 대화를 읽으려고 위로 올렸다면 응답이 도착해도 끌어내리지 않는다.
  await page.evaluate(() => {
    document.querySelector('[aria-label="계획 대화 내용"]').scrollTop = 0
  })
  await new Promise((resolve) => setTimeout(resolve, 50))
  await input.fill('이전 대화를 읽으며 네 번째 조건을 보내요')
  await input.press('Enter')
  await page.waitForFunction(() => document.querySelector('#planning-chat-answer')?.readOnly)
  await page.waitForFunction(() => !document.querySelector('#planning-chat-answer')?.readOnly)
  await new Promise((resolve) => setTimeout(resolve, 600))
  assert.equal(
    await page.locator('[aria-label="계획 대화 내용"]').evaluate((el) => el.scrollTop),
    0,
  )
  const fold = page.getByRole('button', { name: '처리한 작업 2개' }).first()
  assert.equal(await fold.getAttribute('aria-expanded'), 'true')
  await fold.click()
  assert.equal(await fold.getAttribute('aria-expanded'), 'false')
  await fold.press('Enter')
  assert.equal(await fold.getAttribute('aria-expanded'), 'true')
  await new Promise((resolve) => setTimeout(resolve, 600))
  assert.equal(await fold.getAttribute('aria-expanded'), 'true', 'receipt folded automatically')
  // 명시적 실패는 작성한 글과 저장된 이전 답변을 보존한다.
  await input.fill('실패 시나리오')
  await input.press('Enter')
  await page.getByRole('alert').filter({ hasText: '답변 서비스를 이용할 수 없어요' }).waitFor()
  await page.waitForFunction(
    () => document.querySelector('#planning-chat-answer')?.value === '실패 시나리오',
  )
  assert.equal(await input.inputValue(), '실패 시나리오')
  // 새 계획은 ID 채택과 달리 명시적으로 초기화한다. 기존 계획을 다시 골라 이력을 복원한다.
  const originalInput = await input.elementHandle()
  await page.getByRole('button', { name: '새 계획', exact: true }).click()
  await input.waitFor()
  assert.equal(await originalInput.evaluate((el) => el.isConnected), false)
  assert.equal(await input.inputValue(), '')
  assert.equal(await page.getByText('확인했어요 4.', { exact: true }).count(), 0)
  await page.getByRole('button', { name: '직접 입력', exact: true }).click()
  assert.equal(await input.evaluate((el) => document.activeElement === el), true)
  await page.getByRole('button', { name: '이전 계획', exact: true }).click()
  await page.getByRole('button', { name: /가을 MT.*생성/ }).click()
  await page.getByText('확인했어요 4.', { exact: true }).waitFor()
  // 복원된 다른 계획의 요청에 대해서는 기존 잠금·안내가 남아 있어야 한다.
  await page.evaluate((draft) => {
    sessionStorage.setItem(
      'planning-request:v1:trace-user:trace-club',
      JSON.stringify({
        version: 1,
        userId: 'trace-user',
        clubId: 'trace-club',
        eventId: 'other-event',
        key: 'other-key',
        kind: 'chat',
        body: { messageId: 'other-key', message: '다른 요청', baseRevision: 0 },
        baseline: { baseRevision: 0, planRevision: 0, steps: [] },
        draft,
        started: false,
      }),
    )
    window.dispatchEvent(new Event('planning-request-change'))
  }, draft)
  await page.getByText('다른 계획의 처리 결과를 확인해야 해요.', { exact: false }).waitFor()
  assert.equal(await input.getAttribute('readonly'), '')
  assert.equal(created, 1, '첫 계획을 만든 뒤 같은 계획을 다시 생성하지 않는다')
  assert.equal(streamed, 5, '각 메시지를 한 번씩만 전송한다')
  assert.deepEqual(errors, [], '브라우저 JavaScript 오류가 없어야 한다')
  const trace = await page.evaluate(() => ({
    samples: window.traceSamples,
    marks: window.traceMarks,
  }))
  if (process.env.PLANNING_TRACE_OUTPUT)
    await fs.writeFile(process.env.PLANNING_TRACE_OUTPUT, JSON.stringify({ turns, ...trace }))
  console.log(
    JSON.stringify(
      {
        viewport: width,
        passed: true,
        turns,
        checks: [
          'DOM continuity',
          'stable geometry',
          'reader scroll',
          'manual fold',
          'failure recovery',
          'new/previous plan isolation',
          'foreign-request lock',
        ],
      },
      null,
      2,
    ),
  )
} finally {
  await browser.close()
}
