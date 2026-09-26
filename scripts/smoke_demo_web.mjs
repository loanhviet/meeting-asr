// Run from the project root after smoke_demo.py, with both local servers running.
// Uses the real API, makes no mocked network responses, and does not edit jobs.
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";

const requireWeb = createRequire(
  new URL("../web/package.json", import.meta.url),
);
const { chromium, expect } = requireWeb("@playwright/test");
const output = new URL("../results/demo-api-smoke/", import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
const rows = [];
page.on("pageerror", (error) => errors.push(error.message));

async function select(name) {
  await page
    .getByRole("navigation", { name: "Cuộc họp gần đây" })
    .getByRole("button", { name: new RegExp(name.replaceAll(".", "\\.")) })
    .first()
    .click();
  await page
    .getByRole("searchbox", { name: "Tìm trong transcript" })
    .waitFor({ timeout: 90000 });
}

try {
  await page.goto(process.env.MEETING_WEB_URL || "http://127.0.0.1:3000");
  for (const name of ["demo_clean.wav", "demo_noisy.mp3", "demo_overlap.m4a"]) {
    await select(name);
    await page.waitForFunction(
      () => document.querySelector("audio")?.readyState >= 1,
    );
    const duration = await page
      .locator("audio")
      .evaluate((audio) => audio.duration);
    expect(duration).toBeGreaterThan(80);
    expect(duration).toBeLessThan(100);
    await page
      .getByRole("button", { name: /^Nghe từ/ })
      .first()
      .click();
    await page.waitForFunction(() => {
      const audio = document.querySelector("audio");
      return audio && !audio.paused && audio.currentTime > 0;
    });
    await page.locator("audio").evaluate((audio) => audio.pause());
    await page.getByRole("tab", { name: "Timeline", exact: true }).click();
    await page.getByRole("tab", { name: "Nội dung", exact: true }).click();
    rows.push({ name, duration, playback: true, timeline: true });
    if (name === "demo_clean.wav") {
      await page.screenshot({
        path: new URL("web-desktop.png", output).pathname,
        fullPage: true,
      });
    }
  }
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: /PDF/ }).click();
  const download = await downloadPromise;
  expect(await download.failure()).toBeNull();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  await page.screenshot({
    path: new URL("web-mobile.png", output).pathname,
    fullPage: true,
  });
  await page.reload();
  await select("demo_clean.wav");
  await page
    .getByRole("searchbox", { name: "Tìm trong transcript" })
    .fill("đã kiểm tra demo");
  await expect(page.locator(".turn")).toHaveCount(1);
  await expect(page.locator(".turn")).toContainText("đã kiểm tra demo");
  expect(errors).toEqual([]);
  const result = {
    live_backend: true,
    samples: rows,
    pdf_download: true,
    mobile_no_overflow: true,
    persisted_edit_search: true,
    page_errors: errors,
  };
  await writeFile(
    new URL("web-smoke.json", output),
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
