// 전용 합성 DB: 행사 상태 PLANNING, 현재 draft에는 날짜가 있고 event.start_date는 NULL인 fixture.
// 응답 fixture 구간의 결과를 실제 AI 모델 결과로 해석하지 않는다.
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
import fs from 'node:fs/promises'
import assert from 'node:assert/strict'
const session = JSON.parse(await fs.readFile(process.env.P2_TEST_SESSION, 'utf8'))
const dir = process.env.P2_EVIDENCE || 'docs/evidence/325'
const ui = process.env.P2_UI_ORIGIN || 'http://127.0.0.1:5175'
const apiOrigin = process.env.P2_API_ORIGIN || 'http://127.0.0.1:8005'
const browser = await chromium.launch({
  headless: true,
  ...(process.env.P2_BROWSER_PATH ? { executablePath: process.env.P2_BROWSER_PATH } : {}),
})
const context = await browser.newContext({ viewport: { width: 1280, height: 832 } })
await context.addInitScript(({ token, clubId }) => {
  localStorage.setItem('unyounghae_access_token', token)
  localStorage.setItem('unyounghae_selected_club_id', clubId)
}, session)
const page = await context.newPage()
const plan = `/events/${session.eventId}/plan`
async function api(path, method = 'GET', data) {
  const response = await context.request.fetch(apiOrigin + '/api/v1' + path, {
    method,
    headers: { Authorization: 'Bearer ' + session.token },
    data,
  })
  assert.ok(response.ok(), `${response.status()} ${await response.text()}`)
  return (await response.json()).data
}
const ready = () => page.getByRole('heading', { name: '준비 순서', exact: true }).waitFor()
await page.goto(`${ui}/planning?eventId=${session.eventId}&stage=review`)
await ready()
let screen = await api(plan)
console.log(
  'Actual AI review:',
  screen.review?.status,
  screen.review?.outcome,
  screen.review?.errorCode,
)
await page.screenshot({ path: dir + '/p2-review-result.png', fullPage: true })
// 현재 합성 행사는 생성 실패 뒤 구성 API로 만들어 행사 테이블 시작일은 비어 있다.
await page.getByRole('button', { name: '운영 시작', exact: true }).click()
await page
  .getByText(
    '운영을 시작하려면 행사 시작일과 하나 이상의 단계가 필요해요. 행사 조건을 확인해 주세요.',
    { exact: true },
  )
  .waitFor()
await page.screenshot({ path: dir + '/p2-start-failure.png', fullPage: true })
// 실제 1개 단계, 일정 미정, Action 없는 단계의 저장·새로고침.
const single = await api('/events', 'POST', { clubId: session.clubId })
await api(`/events/${single.id}/plan/steps`, 'PATCH', { expectedRevision: 0, codes: ['EVENT_DAY'] })
await page.goto(`${ui}/planning?eventId=${single.id}`)
await ready()
assert.ok(
  (await page.locator('main').innerText()).includes('포함 단계 1개 · 포함하지 않은 단계 12개'),
)
await page.reload()
await ready()
await page.screenshot({ path: dir + '/p2-single-stage.png', fullPage: true })
// 렌더링 경계값: 미래 code와 긴 검토 의견은 저장된 API 응답에만 fixture를 덧씌운다.
await page.route(`**/api/v1/events/${session.eventId}/plan/steps`, async (route) => {
  const response = await route.fetch()
  const body = await response.json()
  body.data.push({
    ...body.data[0],
    id: 'future_step_fixture',
    code: 'FUTURE_STEP',
    name: '알 수 없는 새 단계도 누락 없이 표시',
    actions: [],
  })
  await route.fulfill({ response, json: body })
})
const reviewStatus = { value: 'DONE', stale: false }
await page.route(`**/api/v1/events/${session.eventId}/plan`, async (route) => {
  const response = await route.fetch()
  const body = await response.json()
  body.data.review = {
    status: reviewStatus.value,
    generatedRevision: 1,
    reviewedRevision: reviewStatus.stale ? 0 : body.data.planRevision,
    outcome: 'issues',
    errorCode: reviewStatus.value === 'FAILED' ? 'AI_UNAVAILABLE' : null,
    items: [
      {
        stepNames: ['모집 공지', '예약'],
        message: '긴 검토 의견을 읽고 일정과 내용을 확인해 주세요. '.repeat(24),
        suggestion: '계획은 자동으로 바뀌지 않아요. 내용을 검토한 뒤 필요한 항목을 수정해 주세요.',
      },
    ],
  }
  await route.fulfill({ response, json: body })
})
await page.goto(`${ui}/planning?eventId=${session.eventId}&stage=review`)
await ready()
await page
  .getByRole('heading', { name: '알 수 없는 새 단계도 누락 없이 표시', exact: true })
  .waitFor()
await page.getByText('이런 점을 확인해 보세요', { exact: true }).waitFor()
await page.screenshot({ path: dir + '/p2-long-review-unknown-code-fixture.png', fullPage: true })
for (const width of [1280, 390, 320]) {
  await page.setViewportSize({ width, height: 832 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
}
reviewStatus.value = 'FAILED'
await page.reload()
await ready()
await page.getByText('검토하지 못했어요', { exact: true }).waitFor()
await page.getByRole('button', { name: '다시 시도', exact: true }).waitFor()
await page.screenshot({ path: dir + '/p2-review-failure-fixture.png', fullPage: true })
reviewStatus.value = 'DONE'
reviewStatus.stale = true
await page.reload()
await ready()
await page.getByText('검토한 뒤로 계획이 더 바뀌었어요', { exact: true }).waitFor()
await page.getByRole('button', { name: '다시 검토', exact: true }).waitFor()
// 구성 화면의 320px 터치 타깃과 가로 넘침.
await page.getByRole('button', { name: '단계 구성 변경', exact: true }).click()
await page.locator('[data-phase-group]').first().waitFor()
assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
await page.screenshot({ path: dir + '/p2-configuration-320.png', fullPage: true })
await browser.close()
console.log(
  'PASS actual single stage + start 409 recovery; response-fixture unknown code, long review, failed/stale states; narrow editor',
)
