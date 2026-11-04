// 완료 줄·패널·강조를 같은 MutationObserver 콜백과 프레임 번호로 기록한다.
// 실제 응답과 고정 SSE 확인에 함께 쓰며, 인증 정보는 기록하지 않는다.
module.exports = function installFactsProbe() {
  window.__trace = { events: [], renders: [] };
  let frame = 0;
  const tick = () => {
    frame++;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  window.__pauseFlash = true;
  const orig = window.fetch;
  window.fetch = async (...args) => {
    let res;
    if (window.__mockTurn && String(args[0]).includes("/chat/stream")) {
      const plan = window.__mockTurn;
      window.__mockTurn = null;
      const encoder = new TextEncoder();
      res = new Response(
        new ReadableStream({
          start(controller) {
            for (const step of plan) {
              setTimeout(() => {
                controller.enqueue(
                  encoder.encode(
                    "event: " +
                      step.event +
                      "\n" +
                      "data: " +
                      JSON.stringify(step.data) +
                      "\n\n",
                  ),
                );
                if (step.event === "done" || step.event === "error")
                  controller.close();
              }, step.delay);
            }
          },
        }),
        { headers: { "content-type": "text/event-stream" } },
      );
    } else res = await orig(...args);
    if (!String(args[0]).includes("/chat/stream")) return res;
    const reader = res.body.getReader(),
      decoder = new TextDecoder();
    let buffer = "";
    return new Response(
      new ReadableStream({
        async start(controller) {
          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              buffer += decoder.decode(value, { stream: true });
              let end;
              while ((end = buffer.indexOf("\n\n")) >= 0) {
                const block = buffer.slice(0, end);
                buffer = buffer.slice(end + 2);
                const event = block.match(/^event: (.+)$/m)?.[1],
                  data = block.match(/^data: (.+)$/m)?.[1];
                if (event && data)
                  window.__trace.events.push({
                    at: performance.now(),
                    frame,
                    event,
                    data: JSON.parse(data),
                  });
              }
              controller.enqueue(value);
            }
            controller.close();
          } catch (e) {
            controller.error(e);
          }
        },
      }),
      { status: res.status, headers: res.headers },
    );
  };
  let previous = "";
  new MutationObserver(() => {
    const panel = Array.from(document.querySelectorAll("h2")).find(
      (e) => e.textContent === "지금까지 정한 것",
    )?.parentElement;
    if (!panel) return;
    const flash = Array.from(panel.querySelectorAll(".animate-fact-flash")).map(
      (e) => e.parentElement.innerText,
    );
    if (window.__pauseFlash && flash.length)
      panel
        .querySelectorAll(".animate-fact-flash")
        .forEach((e) => e.getAnimations().forEach((a) => a.pause()));
    const row = {
      frame,
      at: performance.now(),
      url: location.search,
      completedChecks: document.querySelectorAll(
        'ul[aria-label="토리가 처리한 작업"] svg.text-done',
      ).length,
      lines: Array.from(
        document.querySelectorAll('ul[aria-label="토리가 처리한 작업"]'),
      ).map((e) => e.innerText),
      panel: panel.innerText,
      flash,
      animation: panel.querySelector(".animate-fact-flash")
        ? getComputedStyle(panel.querySelector(".animate-fact-flash"))
            .animationName
        : null,
    };
    const signature = JSON.stringify({ ...row, frame: 0, at: 0 });
    if (signature !== previous) {
      previous = signature;
      window.__trace.renders.push(row);
    }
  }).observe(document, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["class"],
  });
};
