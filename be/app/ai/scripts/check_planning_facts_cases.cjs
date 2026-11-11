// 고정 SSE로 저장 전 실패·저장 값 차이·새 계획 주소 이동을 검증한다(#302).
// 실제 모델을 호출하지 않으며, 새 계획 생성은 지정한 로컬 DB에서 한다.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const fs = require("node:fs"),
  assert = require("node:assert/strict");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const tag = (process.env.PLANNING_PROBE_TAG || "").replace(/[^a-z0-9-]/g, "");
const prefix = `plan-facts-sync-302${tag ? "-" + tag : ""}`;
const root = path.resolve(__dirname, "../../../..");
const output = path.join(root, "be/app/ai/docs/planning/ui-tests/");
const web = process.env.PLANNING_WEB_URL || "http://localhost:5174";
const api = process.env.PLANNING_API_URL || "http://127.0.0.1:8010";
if (!process.env.PLANNING_STORAGE_STATE || !process.env.PLANNING_PLAN_URL)
  throw new Error("PLANNING_STORAGE_STATE와 PLANNING_PLAN_URL을 지정하세요.");
const state = JSON.parse(fs.readFileSync(process.env.PLANNING_STORAGE_STATE));
const token = state.origins[0].localStorage.find(
  (x) => x.name === "unyounghae_access_token",
).value;
const existing = process.env.PLANNING_PLAN_URL;
const eid = new URL(existing).searchParams.get("eventId");
const installFactsProbe = require("./planning_facts_probe.cjs");
(async () => {
  const screen = (
    await (
      await fetch(`${api}/api/v1/events/${eid}/plan`, {
        headers: { Authorization: "Bearer " + token },
      })
    ).json()
  ).data;
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
  });
  const ctx = await browser.newContext({
    storageState: state,
    viewport: { width: 1600, height: 1050 },
  });
  for (const scenario of [
    "existing-failure",
    "new-failure",
    "saved-difference",
    "new-fast-done",
  ]) {
    const page = await ctx.newPage();
    page.on("pageerror", (e) => console.error("PAGEERROR", e.message));
    await page.addInitScript(installFactsProbe);
    const isNew = scenario.startsWith("new");
    let saved = false;
    const draft = structuredClone(screen.draft);
    if (isNew) {
      for (const k of Object.keys(draft.conditions)) draft.conditions[k] = null;
      draft.deferredTopics = [];
    }
    draft.conditions.headcount = 99;
    draft.conditions.feePerPerson = 0;
    draft.conditionMeta = {};
    let result = {
      ...screen,
      reply: "인원과 참가비를 반영했어요.",
      draft,
      baseRevision: isNew ? 1 : screen.baseRevision + 1,
    };
    if (scenario === "saved-difference") {
      result = structuredClone(result);
      result.draft.conditions.feePerPerson = 10000;
    }
    if (scenario === "new-fast-done") {
      await page.route("**/api/v1/events/*/plan", async (route) => {
        if (saved)
          await route.fulfill({
            json: { data: { ...screen, draft, baseRevision: 1 }, meta: null },
          });
        else await route.continue();
      });
      await page.route("**/api/v1/events/*/plan/messages", async (route) => {
        if (saved)
          await route.fulfill({
            json: {
              data: [
                {
                  id: "u-302",
                  role: "USER",
                  content: "인원99명, 참가비 무료로 해줘",
                },
                { id: "a-302", role: "ASSISTANT", content: result.reply },
              ],
              meta: null,
            },
          });
        else await route.continue();
      });
    }
    await page.goto(isNew ? web + "/planning" : existing);
    await page.getByRole("textbox", { name: "계획 대화 답변" }).waitFor();
    if (!isNew) await page.getByText("50명", { exact: true }).waitFor();
    const before = await page
      .locator("h2")
      .filter({ hasText: "지금까지 정한 것" })
      .locator("..")
      .innerText();
    const completed = {
      operationId: "c-302",
      kind: "condition_applied",
      status: "completed",
      text: "예상 인원 · 참가비 반영했어요",
      conditionDraft: draft,
    };
    const success =
      scenario === "saved-difference" || scenario === "new-fast-done";
    await page.evaluate(
      ({ completed, result, success }) => {
        window.__trace = { events: [], renders: [] };
        window.__mockTurn = [
          { delay: 20, event: "progress", data: completed },
          success
            ? { delay: 650, event: "done", data: result }
            : {
                delay: 650,
                event: "error",
                data: { code: "AI_UNAVAILABLE", message: "로컬 검증용 실패" },
              },
        ];
      },
      { completed, result, success },
    );
    await page
      .getByRole("textbox", { name: "계획 대화 답변" })
      .fill("인원99명, 참가비 무료로 해줘");
    await page.getByRole("textbox", { name: "계획 대화 답변" }).press("Enter");
    await page.waitForFunction(() =>
      document.querySelector(".animate-fact-flash"),
    );
    if (scenario === "new-fast-done") saved = true;
    await page.screenshot({
      path: output + `${prefix}-${scenario}-pending.jpg`,
      type: "jpeg",
      quality: 85,
    });
    await page.waitForFunction(() =>
      window.__trace.events.some(
        (e) => e.event === "done" || e.event === "error",
      ),
    );
    if (isNew) await page.waitForURL("**/planning?eventId=*");
    await page.waitForFunction(
      () => document.querySelector("textarea")?.readOnly === false,
    );
    const after = await page
      .locator("h2")
      .filter({ hasText: "지금까지 정한 것" })
      .locator("..")
      .innerText();
    if (!success) {
      assert.equal(after, before);
      assert.equal(await page.locator(".animate-fact-flash").count(), 0);
      await page
        .getByText("조건 반영을 확인하지 못했어요", { exact: true })
        .waitFor();
    }
    if (scenario === "saved-difference") {
      assert.ok(after.includes("1인 10,000원"));
      const flash = await page
        .locator(".animate-fact-flash")
        .locator("..")
        .allInnerTexts();
      assert.equal(flash.length, 1);
      assert.ok(flash[0].includes("참가비"));
    }
    if (scenario === "new-fast-done") {
      assert.ok(after.includes("99명"));
      assert.equal(await page.locator(".animate-fact-flash").count(), 2);
    }
    await page.screenshot({
      path: output + `${prefix}-${scenario}.jpg`,
      type: "jpeg",
      quality: 85,
    });
    await page.waitForTimeout(1700);
    const trace = await page.evaluate(() => window.__trace);
    trace.scenario = scenario;
    trace.codeCommit = execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: root,
      encoding: "utf8",
    }).trim();
    trace.responseSource = "fixed-sse";
    trace.before = before;
    trace.after = after;
    fs.writeFileSync(
      output + `${prefix}-${scenario}.json`,
      JSON.stringify(trace, null, 2),
    );
    console.log("PASS", scenario);
    await page.close();
  }
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
