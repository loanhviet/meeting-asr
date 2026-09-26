import { expect, test } from "@playwright/test";

test("upload, review, rename, stale summary, timeline and export", async ({
  page,
}) => {
  const job = {
    id: "fixture",
    filename: "cuoc-hop.wav",
    status: "complete",
    stage: "complete",
    progress: 1,
    error: null,
    created: 1700000000,
    revision: 0,
    summary_error: null,
  };
  const turn = {
    turn_id: "0",
    start: 0,
    end: 6,
    speaker: "SPEAKER_00",
    original_speaker: "SPEAKER_00",
    text: "Nội dung ban đầu",
    original_text: "Nội dung ban đầu",
    flagged: true,
    reviewed: false,
    confidence: 0.2,
    flag_reasons: ["độ tin cậy ASR thấp"],
  };
  const minutes = {
    audio_id: "fixture",
    duration: 6,
    num_speakers: 1,
    flagged_ratio: 0.2,
    turns: [turn],
    summary: "Tóm tắt ban đầu",
    topics: [],
    action_items: [],
  };
  const view = {
    original: structuredClone(minutes),
    edited: minutes,
    revision: 0,
    summary_stale: false,
    summary_error: null,
    speaker_names: {} as Record<string, string>,
  };
  let uploaded = false;
  await page.route("http://127.0.0.1:8000/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/health")
      return route.fulfill({ json: { llm_enabled: false } });
    if (path === "/api/jobs" && request.method() === "POST") {
      uploaded = true;
      return route.fulfill({ status: 202, json: { job_id: job.id } });
    }
    if (path === "/api/jobs")
      return route.fulfill({ json: uploaded ? [job] : [] });
    if (path.endsWith("/turns/0")) {
      const update = request.postDataJSON();
      expect(update.expected_revision).toBe(view.revision);
      if (update.text !== undefined) turn.text = update.text;
      if (update.speaker_name) {
        view.speaker_names.SPEAKER_00 = update.speaker_name;
        turn.speaker = update.speaker_name;
      }
      turn.reviewed = update.reviewed;
      view.revision += 1;
      job.revision = view.revision;
      view.summary_stale = true;
      return route.fulfill({ json: view });
    }
    if (path.endsWith("/result")) return route.fulfill({ json: view });
    if (path.endsWith("/audio"))
      return route.fulfill({
        status: 200,
        contentType: "audio/wav",
        body: Buffer.alloc(44),
      });
    if (path.endsWith("/export"))
      return route.fulfill({
        body: turn.text,
        headers: { "Content-Disposition": 'attachment; filename="meeting.md"' },
      });
    return route.fulfill({ json: job });
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Ghi lại những điều quan trọng." }),
  ).toBeVisible();
  await page.getByLabel("Chọn bản ghi cuộc họp").setInputFiles({
    name: "cuoc-hop.wav",
    mimeType: "audio/wav",
    buffer: Buffer.from("fixture"),
  });
  await expect(
    page.getByText("Nội dung ban đầu", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sửa & xác nhận" }).click();
  await page.getByLabel("Chỉnh sửa nội dung lượt nói").fill("Nội dung đã soát");
  await page.getByRole("button", { name: "Lưu & đánh dấu đã soát" }).click();
  await expect(
    page.getByText("Nội dung đã soát", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("✓ Đã soát", { exact: true })).toBeVisible();
  await page.getByText("Đặt tên người nói", { exact: true }).click();
  await page.getByLabel("SPEAKER_00", { exact: true }).fill("An");
  await page.getByRole("button", { name: "Lưu tên" }).click();
  await expect(
    page.locator(".turn-meta").getByText("An", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Tóm tắt & công việc" }).click();
  await expect(page.getByText(/Nội dung đã thay đổi/)).toBeVisible();
  await page.getByRole("tab", { name: "Timeline" }).click();
  await expect(
    page.locator(".timeline-row").getByText("An", { exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Markdown ↗" }).click();
  expect((await download).suggestedFilename()).toBe("meeting.md");
});

test("mobile empty state and unsupported upload", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("http://127.0.0.1:8000/api/**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto("/");
  await page.getByLabel("Chọn bản ghi cuộc họp").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("x"),
  });
  await expect(page.locator(".alert[role='alert']")).toContainText(
    "WAV, MP3 hoặc M4A",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/mobile-empty.png",
    fullPage: true,
  });
});
