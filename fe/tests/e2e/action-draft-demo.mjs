// #335 화면 사진: ?demo 시연 데이터로 초안 상태 다섯 가지 · 모달 편집 · 충돌 안내를 찍는다. 서버는 필요 없다.
// npm install --no-save playwright 후 개발 서버(npm run dev)를 띄우고
// DEMO_UI_ORIGIN=http://localhost:5173 node tests/e2e/action-draft-demo.mjs
import fs from 'node:fs/promises'
import path from 'node:path'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const out = path.resolve(process.env.DEMO_EVIDENCE || 'docs/evidence/335')
await fs.mkdir(out, { recursive: true })
const base = `${process.env.DEMO_UI_ORIGIN || 'http://localhost:5173'}/events/evt_9f2c8a?demo`
const browser = await chromium.launch({
  headless: true,
  ...(process.env.DEMO_BROWSER_PATH ? { executablePath: process.env.DEMO_BROWSER_PATH } : {}),
})
const problems = []

async function open(width) {
  const page = await browser.newPage({ viewport: { width, height: width < 600 ? 844 : 900 }, deviceScaleFactor: 2 })
  page.on('pageerror', (e) => problems.push(`${width} pageerror ${e.message}`))
  page.on('dialog', (d) => d.accept())
  await page.goto(base, { waitUntil: 'networkidle' })
  return page
}

const card = (page, title) => page.locator('article', { has: page.getByText(title, { exact: true }) })
const dialog = (page) => page.locator('dialog[open]').last()

async function overflow(page, label) {
  const bad = await page.evaluate(() => {
    const found = []
    for (const el of document.querySelectorAll('dialog[open] > div *')) {
      const r = el.getBoundingClientRect()
      if (r.width > 0 && r.right > window.innerWidth + 0.5) found.push(`${el.tagName}.${String(el.className).slice(0, 40)} right=${Math.round(r.right)}`)
    }
    return { found: found.slice(0, 5) }
  })
  if (bad.found.length) problems.push(`${label}: ${JSON.stringify(bad)}`)
}

async function openStep(page, name) {
  await page.getByRole("button", { name: new RegExp(`^\\d+\\. ${name},`) }).evaluate((el) => el.click())
  await dialog(page).waitFor()
}

for (const width of [390, 1280, 320]) {
  const w = String(width)
  // ── 상태 다섯 가지 ──
  let page = await open(width)
  await openStep(page, '입금 확인')
  await card(page, '미납자 4명에게 2차 납부 안내 문자 보내기').waitFor()
  await overflow(page, `${w} step modal`)
  if (width !== 320) {
    await card(page, '미납자 4명에게 2차 납부 안내 문자 보내기').screenshot({ path: `${out}/state-ready-ai-${w}.png` })
    await card(page, '입금 마감 하루 전 단톡방 공지 올리기').screenshot({ path: `${out}/state-drafting-${w}.png` })
    await card(page, '입금 확인된 28명에게 확인 문자 보내기').screenshot({ path: `${out}/state-failed-${w}.png` })
    await card(page, '환불 규정 안내 공지 올리기').screenshot({ path: `${out}/state-ready-user-${w}.png` })
    await card(page, '미응답 회원 9명에게 신청 마감 안내').screenshot({ path: `${out}/state-approved-edit-entry-${w}.png` })
    await page.screenshot({ path: `${out}/step-modal-${w}.png` })
  } else {
    await page.screenshot({ path: `${out}/step-modal-${w}.png` })
  }
  await page.getByRole('button', { name: '닫기', exact: true }).last().click()
  await openStep(page, '사전 안내')
  await card(page, '참가자 사전 안내 공지 올리기').waitFor()
  if (width !== 320) await card(page, '참가자 사전 안내 공지 올리기').screenshot({ path: `${out}/state-none-upcoming-${w}.png` })
  await page.close()

  // ── 모달에서 고치기 → 저장 ──
  page = await open(width)
  await openStep(page, '입금 확인')
  await card(page, '미납자 4명에게 2차 납부 안내 문자 보내기').getByRole('button', { name: '검토하기' }).click()
  const review = page.locator('dialog[open]', { has: page.getByRole('heading', { name: '미납자 4명에게 2차 납부 안내 문자 보내기' }) })
  await review.waitFor()
  await review.screenshot({ path: `${out}/modal-ready-ai-${w}.png` })
  const box = review.getByLabel('보낼 내용')
  const text = await box.inputValue()
  await box.fill(text.replace('[입금 계좌]', '카카오뱅크 3333-01-2345678 (봄MT준비팀)'))
  await overflow(page, `${w} modal edit`)
  await review.screenshot({ path: `${out}/modal-edit-dirty-${w}.png` })
  await review.getByRole('button', { name: '고친 내용 저장' }).click()
  await review.getByText('직접 고친 내용', { exact: true }).waitFor()
  await review.screenshot({ path: `${out}/modal-edit-saved-${w}.png` })
  await page.close()

  // ── 작성 중에 직접 쓰다가 초안 도착 → 저장 409 ──
  page = await open(width)
  await openStep(page, '입금 확인')
  const started = Date.now()
  await card(page, '입금 마감 하루 전 단톡방 공지 올리기').getByRole('button', { name: '검토하기' }).click()
  const drafting = page.locator('dialog[open]', { has: page.getByRole('heading', { name: '입금 마감 하루 전 단톡방 공지 올리기' }) })
  await drafting.waitFor()
  await drafting.screenshot({ path: `${out}/modal-drafting-${w}.png` })
  await drafting.getByLabel('보낼 내용').fill('📢 입금 마감 안내\n내일 밤 12시까지 참가비 45,000원을 보내 주세요.\n계좌는 공지방 상단 고정 메시지를 봐 주세요.')
  // 시연에서는 처음 본 뒤 15초가 지나면 초안이 도착하고, 3초마다 다시 조회한다
  await page.waitForTimeout(Math.max(0, 19_000 - (Date.now() - started)))
  // 다시 조회해도 입력한 글이 남아 있어야 한다
  const kept = await drafting.getByLabel('보낼 내용').inputValue()
  if (!kept.startsWith('📢 입금 마감 안내')) problems.push(`${w} typed text overwritten: ${kept}`)
  await drafting.getByRole('button', { name: '고친 내용 저장' }).click()
  await drafting.getByText('토리 초안이 도착했어요').waitFor()
  await overflow(page, `${w} conflict`)
  await drafting.screenshot({ path: `${out}/modal-save-conflict-${w}.png` })
  await drafting.getByRole('button', { name: '토리 초안 보기' }).click()
  const swapped = await drafting.getByLabel('보낼 내용').inputValue()
  if (!swapped.includes('입금 마감 안내') || !swapped.includes('[입금 계좌]')) problems.push(`${w} tori draft not shown: ${swapped}`)
  await drafting.screenshot({ path: `${out}/modal-conflict-tori-draft-${w}.png` })
  await page.close()

  if (width === 320) continue
  // ── [내 글로 저장] ──
  page = await open(width)
  await openStep(page, '입금 확인')
  const started2 = Date.now()
  await card(page, '입금 마감 하루 전 단톡방 공지 올리기').getByRole('button', { name: '검토하기' }).click()
  const mine = page.locator('dialog[open]', { has: page.getByRole('heading', { name: '입금 마감 하루 전 단톡방 공지 올리기' }) })
  await mine.getByLabel('보낼 내용').fill('📢 입금 마감 안내\n내일 밤 12시까지 참가비를 보내 주세요.')
  await page.waitForTimeout(Math.max(0, 19_000 - (Date.now() - started2)))
  await mine.getByRole('button', { name: '고친 내용 저장' }).click()
  await mine.getByRole('button', { name: '내 글로 저장' }).click()
  await mine.getByText('직접 고친 내용', { exact: true }).waitFor()
  await mine.screenshot({ path: `${out}/modal-conflict-keep-mine-${w}.png` })
  await page.close()

  // ── 승인된 공지 고치기 → 다시 승인 필요 ──
  page = await open(width)
  await openStep(page, '입금 확인')
  await card(page, '미응답 회원 9명에게 신청 마감 안내').getByRole('button', { name: '내용 고치기' }).click()
  const approved = page.locator('dialog[open]', { has: page.getByRole('heading', { name: '미응답 회원 9명에게 신청 마감 안내' }) })
  await approved.getByLabel('보낼 내용').fill('안녕하세요. 봄 MT 참가 신청이 내일 마감돼요. 아직 응답하지 않은 분은 오늘 안에 신청 여부를 알려 주세요.')
  await approved.getByRole('button', { name: '고친 내용 저장' }).click()
  await approved.getByText('고친 내용으로 다시 승인이 필요해요').waitFor()
  await approved.screenshot({ path: `${out}/modal-reapprove-${w}.png` })
  await page.close()

  // ── 「다시 받기」 → 작성 중 ──
  page = await open(width)
  await openStep(page, '입금 확인')
  await card(page, '입금 확인된 28명에게 확인 문자 보내기').getByRole('button', { name: '다시 받기' }).click()
  await card(page, '입금 확인된 28명에게 확인 문자 보내기').getByText('토리가 초안을 쓰고 있어요').waitFor()
  await card(page, '입금 확인된 28명에게 확인 문자 보내기').screenshot({ path: `${out}/redraft-drafting-${w}.png` })
  await page.close()
}

await browser.close()
// 넘침은 본문(카드·입력칸)만 따진다. 공용 Modal 하단 버튼 줄은 좁은 화면에서 원래 넘친다(#335 보고).
console.log(problems.length ? problems.join('\n') : 'no problems')
