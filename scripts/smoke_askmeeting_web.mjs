// Exercise the isolated demo API and spoken audio; answers may be scripted fixtures.
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";

const requireWeb = createRequire(
  new URL("../web/package.json", import.meta.url),
);
const { chromium, expect } = requireWeb("@playwright/test");
const webUrl = process.env.MEETING_WEB_URL || "http://127.0.0.1:3000";
const apiUrl = process.env.MEETING_ASK_API_URL || "http://127.0.0.1:8001";
const output = new URL("../results/askmeeting-demo/", import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  // Forward browser API traffic to the isolated real service, never invent responses.
  await page.route("**/api/**", async (route) => {
    const original = new URL(route.request().url());
    const response = await route.fetch({
      url: apiUrl + original.pathname + original.search,
    });
    await route.fulfill({ response });
  });
  const health = await (await page.request.get(apiUrl + "/api/health")).json();
  await page.goto(webUrl + "/?job=ask-demo");
  const view = await (
    await page.request.get(apiUrl + "/api/jobs/ask-demo/result")
  ).json();
  const expected = view.edited.turns.find((turn) => turn.turn_id === "t01");
  await page.getByRole("tab", { name: "Hỏi đáp", exact: true }).click();
  await page
    .getByLabel("Câu hỏi của bạn")
    .fill("Ai nhận kiểm thử chức năng hỏi đáp?");
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  await expect(page.locator(".ask-answer").first()).toContainText(
    "Bình nhận kiểm thử",
  );
  await expect(page.locator(".ask-evidence blockquote").first()).toHaveText(
    expected.text,
  );
  await page.locator(".ask-evidence .source-link").first().click();
  await expect(page.locator('.turn[data-turn-id="t01"]')).toHaveClass(
    /selected/,
  );
  await expect
    .poll(() => page.locator("audio").evaluate((audio) => audio.currentTime))
    .toBeGreaterThanOrEqual(expected.start);
  await page.locator("audio").evaluate((audio) => audio.pause());
  const audio = await page.request.get(apiUrl + "/api/jobs/ask-demo/audio", {
    headers: { Range: "bytes=0-1023" },
  });
  expect(audio.status()).toBe(206);
  expect((await audio.body()).subarray(0, 4).toString()).toBe("RIFF");
  await page.getByRole("tab", { name: "Hỏi đáp", exact: true }).click();
  await page
    .getByLabel("Câu hỏi của bạn")
    .fill("Ngân sách được duyệt bao nhiêu tiền?");
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  await expect(page.locator(".ask-answer").first()).toContainText(
    "Chưa tìm thấy câu trả lời có dẫn chứng.",
  );
  await page.screenshot({ path: new URL("live-browser.png", output).pathname });
  await page.reload();
  await page.getByRole("tab", { name: "Hỏi đáp", exact: true }).click();
  await expect(page.locator(".ask-answer")).toHaveCount(2);
  if (errors.length) throw new Error(JSON.stringify(errors));
  const report = {
    live_api: true,
    provider_mode: health.demo_provider,
    spoken_audio: true,
    http_range: audio.status(),
    source_turn_id: expected.turn_id,
    source_start: expected.start,
    history_persisted: true,
    abstention: true,
    page_errors: errors,
  };
  await writeFile(
    new URL("browser-smoke.json", output),
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
