const installFactsProbe = require("./planning_facts_probe.cjs");
// 실제 모델 3턴의 조건 완료 → 저장 완료와 같은 DOM 갱신을 기록한다(#302).
// 실행 환경과 브라우저 설정은 docs/planning/evaluation.md의 #302 절을 참고한다.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const fs = require("node:fs");
const path = require("node:path"),
  assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const root = path.resolve(__dirname, "../../../..");
const web = process.env.PLANNING_WEB_URL || "http://localhost:5174";
if (!process.env.PLANNING_STORAGE_STATE)
  throw new Error(
    "로그인한 Playwright storage state 경로를 PLANNING_STORAGE_STATE로 지정하세요.",
  );
const output = root + "/be/app/ai/docs/planning/ui-tests/";
const messages = [
  "MT를 준비할게요. 예상 인원은 40명, 참가비는 2만원으로 해줘. 초안은 아직 만들지 마.",
  "참가비 3만원으로 해줘.",
  "인원은 일단 50명, 일정은 2026년 12월 5일부터 6일까지로 해줘.",
];
(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
  });
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1050 },
    storageState: process.env.PLANNING_STORAGE_STATE,
  });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.error("PAGEERROR", e.message));
  await page.addInitScript(installFactsProbe);
  await page.goto(web + "/planning");
  await page.getByRole("textbox", { name: "계획 대화 답변" }).waitFor();
  for (let i = 0; i < messages.length; i++) {
    if (i === 2)
      await page.emulateMedia({
        reducedMotion: "reduce",
        colorScheme: "light",
      });
    await page.evaluate(() => {
      window.__trace = { events: [], renders: [] };
    });
    await page
      .getByRole("textbox", { name: "계획 대화 답변" })
      .fill(messages[i]);
    await page.getByRole("textbox", { name: "계획 대화 답변" }).press("Enter");
    await page.waitForFunction(
      () =>
        window.__trace.events.some(
          (e) =>
            e.event === "progress" &&
            e.data.kind === "condition_applied" &&
            e.data.status === "completed",
        ),
      null,
      { timeout: 120000 },
    );
    await page.waitForFunction(() =>
      document.querySelector(".animate-fact-flash"),
    );
    await page.waitForTimeout(160); // 체크가 나타나는 전환까지 사진에서 확인한다. 강조는 observer가 멈춘다.
    await page.screenshot({
      path:
        output +
        `plan-facts-sync-302-${i === 0 ? "new" : i === 1 ? "existing" : "reduced-motion"}.jpg`,
      type: "jpeg",
      quality: 85,
    });
    await page.waitForFunction(
      () => window.__trace.events.some((e) => e.event === "done"),
      null,
      { timeout: 120000 },
    );
    await page.waitForFunction(
      () => document.querySelector("textarea")?.readOnly === false,
    );
    await page.waitForTimeout(1800);
    const trace = await page.evaluate(() => window.__trace);
    trace.message = messages[i];
    trace.reducedMotion = i === 2;
    trace.codeCommit = execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: root,
      encoding: "utf8",
    }).trim();
    trace.model = process.env.PLANNING_MODEL_LABEL || "미확인";
    trace.promptVersion = "planning-agent-v8";
    fs.writeFileSync(
      output + `plan-facts-sync-302-real-${i + 1}.json`,
      JSON.stringify(trace, null, 2),
    );
    const event = trace.events.find(
      (e) =>
        e.event === "progress" &&
        e.data.kind === "condition_applied" &&
        e.data.status === "completed",
    );
    const done = trace.events.find((e) => e.event === "done");
    const first = trace.renders.find((r) => r.flash.length);
    const check = trace.renders.find(
      (r) =>
        r.at >= event.at && r.lines.some((l) => l.includes(event.data.text)),
    );
    assert.equal(
      check.at,
      first.at,
      "완료 줄과 패널 강조는 같은 DOM 갱신이어야 한다",
    );
    assert.ok(first.completedChecks > 0);
    if (i === 2) assert.equal(first.animation, "none");
    assert.equal(
      trace.renders.filter((r) => r.at > done.at && r.flash.length).length,
      0,
      "같은 done 값은 강조를 다시 시작하지 않는다",
    );
    console.log(
      JSON.stringify({
        turn: i + 1,
        gap: done.at - event.at,
        frame: first.frame,
        checkAndFlashSameMutation: check.at === first.at,
      }),
    );
  }
  console.log("verifiedPlanUrl", page.url());
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
