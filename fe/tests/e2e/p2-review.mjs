// 전용 로컬 DB의 합성 계획에만 실행한다. P2_TEST_SESSION은 {token,clubId,eventId} JSON.
// npm install --no-save playwright 후 P2_TEST_SESSION=/tmp/... node tests/e2e/p2-review.mjs
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const session = JSON.parse(await fs.readFile(process.env.P2_TEST_SESSION, 'utf8'))
const origin = process.env.P2_UI_ORIGIN || 'http://127.0.0.1:5175'
const api = process.env.P2_API_ORIGIN || 'http://127.0.0.1:8005'
const evidence = path.resolve(process.env.P2_EVIDENCE || 'docs/evidence/325')
await fs.mkdir(evidence, { recursive: true })
const browser = await chromium.launch({
  headless: true,
  ...(process.env.P2_BROWSER_PATH ? { executablePath: process.env.P2_BROWSER_PATH } : {}),
})
const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, hasTouch: true })
await context.addInitScript(({ token, clubId }) => {
  localStorage.setItem('unyounghae_access_token', token)
  localStorage.setItem('unyounghae_selected_club_id', clubId)
}, session)
const page = await context.newPage()
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
const calls = []
page.on('request', (request) => {
  if (request.url().includes('/api/v1/'))
    calls.push({ method: request.method(), url: request.url() })
})
const url = `/planning?eventId=${session.eventId}`
const plan = `/events/${session.eventId}/plan`
async function request(route, method = 'GET', data) {
  const result = await context.request.fetch(`${api}/api/v1${route}`, {
    method,
    headers: { Authorization: `Bearer ${session.token}` },
    data,
  })
  assert.ok(result.ok(), `${method} ${route}: ${result.status()} ${await result.text()}`)
  return (await result.json()).data
}
const steps = () => request(`${plan}/steps`)
const ready = () => page.getByRole('heading', { name: '준비 순서', exact: true }).waitFor()
const shot = (name) => page.screenshot({ path: path.join(evidence, `${name}.png`), fullPage: true })
const titleField = () => page.getByRole('dialog').getByLabel('제목', { exact: true }).first()
const edit = (name) =>
  page.getByRole('button', { name: `${name} 일정·내용 수정`, exact: true }).click()
const dialogSave = () =>
  page.getByRole('dialog').getByRole('button', { name: '저장', exact: true }).click()
const configuration = () =>
  page.getByRole('button', { name: '단계 구성 변경', exact: true }).click()
const saveConfiguration = async () => {
  await page.getByRole('button', { name: '구성 저장', exact: true }).click()
  await ready()
}
const order = (phase) =>
  page
    .locator(`[data-phase-group="${phase}"] [data-sort-code]`)
    .evaluateAll((rows) => rows.map((row) => row.dataset.sortCode))
const keyboardMove = async (name, key = 'ArrowDown', drop = 'Enter') => {
  const handle = page.getByRole('button', { name: `${name} 순서 변경`, exact: true })
  await handle.focus()
  await handle.press('Space')
  await handle.press(key)
  await handle.press(drop)
}
try {
  await page.goto(origin + url)
  await ready()
  assert.ok(page.url().includes('stage=review'))
  await shot('p2-laptop-13-stages')
  const allSteps = await steps()
  assert.equal(allSteps.length, 13, 'start the dedicated fixture with all 13 stages')
  // 대화는 저장된 메시지만 표시하고, 입력/빠른 답변이 없다. Escape 뒤 포커스 복귀.
  await page.getByRole('button', { name: '이전 대화 보기', exact: true }).click()
  assert.equal(await page.getByRole('dialog').locator('input,textarea').count(), 0)
  assert.equal(await page.getByRole('dialog').getByRole('button').count(), 2)
  await shot('p2-conversation-readonly')
  await page.keyboard.press('Escape')
  assert.equal(
    await page
      .getByRole('button', { name: '이전 대화 보기', exact: true })
      .evaluate((el) => el === document.activeElement),
    true,
  )
  // 실제 일정과 작업 제목을 저장하고 새로고침한다.
  await edit('모집 공지')
  await page.getByRole('dialog').getByLabel('시작일', { exact: true }).fill('2026-11-10')
  await page.getByRole('dialog').getByLabel('마감일', { exact: true }).fill('2026-11-15')
  await titleField().fill('MT 참가 신청 공지 · P2 저장 확인')
  await dialogSave()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  await page.reload()
  await ready()
  assert.ok((await page.locator('main').innerText()).includes('MT 참가 신청 공지 · P2 저장 확인'))
  assert.ok((await steps()).find((step) => step.code === 'RECRUIT_NOTICE').startsAt)
  await edit('모집 공지')
  await titleField().fill('취소할 입력')
  await page.getByRole('dialog').getByRole('button', { name: '취소', exact: true }).click()
  assert.equal(
    (await steps()).find((step) => step.code === 'RECRUIT_NOTICE').actions[0].title,
    'MT 참가 신청 공지 · P2 저장 확인',
  )
  // 날짜 역전은 요청 전에 막는다.
  await edit('모집 공지')
  await page.getByRole('dialog').getByLabel('시작일', { exact: true }).fill('2026-11-20')
  await dialogSave()
  await page.getByText('마감일은 시작일과 같거나 이후여야 해요.', { exact: true }).waitFor()
  await page.keyboard.press('Escape')
  // 다른 편집자가 Step 버전을 올린 뒤 저장하면 실제 HTTP 409, 최신 계획으로 회복.
  await edit('모집 공지')
  let step = (await steps()).find((step) => step.code === 'RECRUIT_NOTICE')
  await request(`/steps/${step.id}`, 'PATCH', {
    expectedVersion: step.version,
    deadline: '2026-11-16T00:00:00+09:00',
  })
  await page.getByRole('dialog').getByLabel('마감일', { exact: true }).fill('2026-11-17')
  await dialogSave()
  await page
    .getByText('다른 변경이 있어요. 최신 계획을 다시 불러온 뒤 다시 시도해 주세요.', {
      exact: true,
    })
    .waitFor()
  await shot('p2-detail-version-conflict')
  await page.getByRole('button', { name: '최신 내용 다시 불러오기', exact: true }).click()
  await ready()
  // 일정 성공 후 Action 충돌: 부분 저장 사실을 알리고 최신 계획에서 확인.
  await edit('모집 공지')
  step = (await steps()).find((step) => step.code === 'RECRUIT_NOTICE')
  await request(`/actions/${step.actions[0].id}`, 'PATCH', {
    expectedVersion: step.actions[0].version,
    title: '동시 편집자가 저장한 공지',
  })
  await page.getByRole('dialog').getByLabel('시작일', { exact: true }).fill('2026-11-11')
  await titleField().fill('충돌로 저장되지 않을 공지')
  await dialogSave()
  await page.getByText(/일정은 저장됐어요/).waitFor()
  await shot('p2-detail-partial-save')
  await page.getByRole('button', { name: '최신 내용 다시 불러오기', exact: true }).click()
  await ready()
  step = (await steps()).find((step) => step.code === 'RECRUIT_NOTICE')
  assert.ok(step.startsAt.startsWith('2026-11-10T15:00'))
  assert.equal(step.actions[0].title, '동시 편집자가 저장한 공지')
  // 구성의 키보드 확정, Escape, 변경 취소는 서버에 바로 반영하지 않는다.
  await configuration()
  const initial = await order('사전 준비')
  await keyboardMove('담당 인원 배치')
  assert.notDeepEqual(await order('사전 준비'), initial)
  await keyboardMove('담당 인원 배치', 'ArrowUp', 'Escape')
  assert.notDeepEqual(await order('사전 준비'), initial)
  await page.getByRole('button', { name: '변경 취소', exact: true }).click()
  await ready()
  assert.deepEqual(
    (await steps()).slice(0, 3).map((step) => step.code),
    initial,
  )
  // 손잡이 마우스 정렬과 다른 그룹 드롭 취소.
  await configuration()
  const first = page.getByRole('button', { name: '담당 인원 배치 순서 변경', exact: true })
  let a = await first.boundingBox()
  let b = await page.locator('[data-sort-code="DEMAND_SURVEY"]').boundingBox()
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2)
  await page.mouse.down()
  await page.mouse.move(b.x + 100, b.y + b.height - 2, { steps: 10 })
  await page.mouse.up()
  assert.equal((await order('사전 준비')).at(-1), 'ASSIGN_ROLES')
  const afterMouse = await order('사전 준비')
  a = await first.boundingBox()
  b = await page.locator('[data-phase-group="모집 · 확정"] header').boundingBox()
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2)
  await page.mouse.down()
  await page.mouse.move(b.x + 100, b.y + 10, { steps: 10 })
  await page.mouse.up()
  assert.deepEqual(await order('사전 준비'), afterMouse)
  // CDP 실제 터치 이벤트로 같은 그룹 정렬.
  const cdp = await context.newCDPSession(page)
  a = await first.boundingBox()
  b = await page.locator('[data-sort-code="RESEARCH_VENUE"]').boundingBox()
  await cdp.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [{ x: a.x + a.width / 2, y: a.y + a.height / 2 }],
  })
  for (let i = 1; i <= 8; i++)
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [
        { x: a.x + 50, y: a.y + a.height / 2 + ((b.y + 2 - a.y - a.height / 2) * i) / 8 },
      ],
    })
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  assert.equal((await order('사전 준비'))[0], 'ASSIGN_ROLES')
  await keyboardMove('담당 인원 배치')
  const savedOrder = await order('사전 준비')
  await shot('p2-configuration-laptop')
  await saveConfiguration()
  await page.reload()
  await ready()
  assert.deepEqual(
    (await steps()).slice(0, 3).map((step) => step.code),
    savedOrder,
  )
  // 실제 구성 충돌은 보존 안내 후 최신 버전으로 다시 시작한다.
  await configuration()
  await keyboardMove('담당 인원 배치', 'ArrowUp')
  const snap = await request(`${plan}/steps/snapshot`)
  await request(`${plan}/steps`, 'PATCH', {
    expectedRevision: snap.baseRevision,
    codes: snap.steps.map((step) => step.code),
  })
  await page.getByRole('button', { name: '구성 저장', exact: true }).click()
  await page
    .getByText('다른 변경이 있어요. 최신 계획을 다시 불러온 뒤 다시 시도해 주세요.', {
      exact: true,
    })
    .waitFor()
  await shot('p2-configuration-version-conflict')
  await page.getByRole('button', { name: '최신 내용으로 다시 시작', exact: true }).click()
  await page.getByRole('button', { name: '변경 취소', exact: true }).click()
  await ready()
  // 제외 저장의 삭제 확인: 취소한 경우 유지, 승인한 경우 DB에서 삭제.
  await configuration()
  await page.getByRole('button', { name: '모집 공지 제외', exact: true }).click()
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: '구성 저장', exact: true }).click()
  assert.equal((await steps()).length, 13)
  page.once('dialog', (dialog) => dialog.accept())
  await saveConfiguration()
  await page.reload()
  await ready()
  assert.equal((await steps()).length, 12)
  assert.equal(
    (await steps()).some((row) => row.id === step.id),
    false,
  )
  await page.getByText('포함하지 않은 단계 1개 보기', { exact: true }).click()
  assert.ok((await page.locator('main').innerText()).includes('모집 공지'))
  await shot('p2-excluded-saved')
  // 다시 포함은 새 ID/빈 일정/기본 작업. 삭제한 입력은 되살리지 않는다.
  await configuration()
  await page.getByRole('button', { name: '모집 공지 다시 포함', exact: true }).click()
  await saveConfiguration()
  await page.reload()
  await ready()
  const recreated = (await steps()).find((row) => row.code === 'RECRUIT_NOTICE')
  assert.notEqual(recreated.id, step.id)
  assert.equal(recreated.startsAt, null)
  assert.equal(recreated.deadline, null)
  assert.notEqual(recreated.actions[0].title, '동시 편집자가 저장한 공지')
  // 조건 수정은 기존 초안을 유지한다.
  await page.getByRole('button', { name: '행사 조건 수정', exact: true }).click()
  await page.getByText('기존 초안 검토하기', { exact: true }).waitFor()
  assert.equal((await steps()).length, 13)
  await page.getByText('기존 초안 검토하기', { exact: true }).click()
  await ready()
  // 행사 상세의 기존 목록 진입을 유지하고 같은 ID의 계획으로 돌아온다.
  await page.getByRole('link', { name: '행사 상세', exact: true }).click()
  await page.getByRole('button', { name: '계획 이어보기', exact: true }).click()
  await ready()
  assert.ok(page.url().includes(session.eventId))
  // 새로고침/직접 링크는 생성 API를 부르지 않는다.
  assert.equal(calls.filter((call) => /\/generate(?:\/stream)?$/.test(call.url)).length, 0)
  // 초안 없는 직접 review는 조건 화면으로. 추가 행사는 전용 DB의 합성 테스트 데이터다.
  const empty = await request('/events', 'POST', { clubId: session.clubId })
  await page.goto(`${origin}/planning?eventId=${empty.id}&stage=review`)
  await page
    .getByText('저장된 초안이 없어요. 조건을 정한 뒤 초안을 만들 수 있어요.', { exact: true })
    .waitFor()
  assert.ok(page.url().includes('stage=conditions'))
  await page.goto(origin + url)
  await ready()
  // 여러 화면 크기에서 실제 데이터를 렌더링하고 가로 넘침 확인.
  for (const [width, height] of [
    [1440, 1000],
    [1280, 832],
    [1024, 768],
    [390, 844],
    [320, 720],
  ]) {
    await page.setViewportSize({ width, height })
    assert.ok(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      `overflow at ${width}`,
    )
    await shot(`p2-${width}`)
  }
  assert.deepEqual(errors, [])
  console.log(
    'PASS actual API/DB: detail save/cancel/reload/date validation, step/action conflicts and partial save, mouse/touch/keyboard sort and cross-group cancellation, structure save/cancel/conflict, exclusion confirm/reinclude, readonly focus, conditions return, event entry, no-draft links, 320–1440px.',
  )
} finally {
  await browser.close()
}
