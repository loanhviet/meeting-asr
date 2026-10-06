import { expect, test } from "@playwright/test";
import { installFixture } from "./fixtures";

test("upload, correct text and speaker, rename, stale summary and export", async ({
  page,
}) => {
  await installFixture(page, { empty: true });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Ghi lại những điều quan trọng." }),
  ).toBeVisible();
  await page.getByLabel("Chọn bản ghi cuộc họp").setInputFiles({
    name: "meeting.wav",
    mimeType: "audio/wav",
    buffer: Buffer.from("fixture"),
  });
  const turn = page.locator('.turn[data-turn-id="1"]');
  await turn
    .getByRole("button", { name: "Sửa & xác nhận", exact: true })
    .click();
  await turn.getByLabel("Chỉnh sửa nội dung lượt nói").fill("Nội dung đã soát");
  await turn.getByLabel("Người nói của lượt này").selectOption("A");
  await turn.getByLabel("Chỉnh sửa nội dung lượt nói").press("Control+Enter");
  await expect(turn.locator(".turn-text")).toHaveText("Nội dung đã soát");
  await expect(turn.locator(".review-label")).toHaveText("✓ Đã soát");
  await expect(turn.locator(".turn-meta strong")).toHaveText("An");
  await turn.getByText("Xem bản ban đầu").click();
  await expect(turn.locator(".original-turn")).toContainText(
    "Tôi nhận phần kiểm thử",
  );
  await page.getByRole("button", { name: "Người nói", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Quản lý người nói" });
  await dialog.getByLabel("A", { exact: true }).fill("Anh An");
  await dialog
    .locator(".speaker-form")
    .filter({ has: page.locator("#speaker-A") })
    .getByRole("button", { name: "Lưu tên" })
    .click();
  await expect(dialog.getByLabel("A", { exact: true })).toHaveValue("Anh An");
  await dialog.getByRole("button", { name: "Đóng", exact: true }).click();
  await expect(turn.locator(".turn-meta strong")).toHaveText("Anh An");
  await page.getByRole("tab", { name: "Tóm tắt & công việc" }).click();
  await expect(page.getByText(/Nội dung đã thay đổi/)).toBeVisible();
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(
    page.locator(".timeline-row").getByText("Anh An", { exact: true }),
  ).toBeVisible();
  await page.getByText("Xuất biên bản", { exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Markdown ↗" }).click();
  expect((await download).suggestedFilename()).toBe("meeting.md");
  await page.reload();
  await expect(page.locator('.turn[data-turn-id="1"] .turn-text')).toHaveText(
    "Nội dung đã soát",
  );
});

test("citations seek the original source and clear transcript filters", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByLabel("Tìm trong transcript").fill("không có kết quả");
  await page.getByRole("tab", { name: "Tóm tắt & công việc" }).click();
  await expect(page.getByText("Nguồn cần soát").first()).toBeVisible();
  await page
    .getByRole("button", { name: "Nghe dẫn chứng 00:10 Bình" })
    .first()
    .click();
  await expect(
    page.getByRole("tab", { name: "Transcript", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Tìm trong transcript")).toHaveValue("");
  await expect(page.locator('.turn[data-turn-id="1"]')).toHaveClass(/selected/);
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((a) => (a as HTMLAudioElement).currentTime),
    )
    .toBeGreaterThanOrEqual(10);
  await page.locator("audio").evaluate((a) => (a as HTMLAudioElement).pause());
});

test("review queue, loop playback and keyboard ignore text inputs", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByRole("button", { name: "Đoạn cần soát tiếp" }).click();
  await expect(page.locator('.turn[data-turn-id="1"]')).toHaveClass(/selected/);
  await page.getByRole("button", { name: "Lặp đoạn", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Lặp đoạn", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.locator("audio").evaluate(async (a) => {
    (a as HTMLAudioElement).currentTime = 12.99;
    await (a as HTMLAudioElement).play();
  });
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((a) => (a as HTMLAudioElement).currentTime),
    )
    .toBeLessThan(12);
  await page.locator("audio").evaluate((a) => (a as HTMLAudioElement).pause());
  await page.getByLabel("Tìm trong transcript").fill("jj");
  await expect(page.getByLabel("Tìm trong transcript")).toHaveValue("jj");
  await page.getByLabel("Tìm trong transcript").fill("");
  await page.evaluate(() => (document.activeElement as HTMLElement).blur());
  await page.keyboard.press("n");
  await expect(page.locator('.turn[data-turn-id="3"]')).toHaveClass(/selected/);
  await page.locator("audio").evaluate((a) => (a as HTMLAudioElement).pause());
  await page.getByRole("button", { name: /^Cần soát/ }).click();
  await expect(page.locator(".turn")).toHaveCount(2);
  await page
    .locator('.turn[data-turn-id="1"]')
    .getByRole("button", { name: "Đúng, đánh dấu đã soát" })
    .click();
  await expect(page.locator(".turn")).toHaveCount(1);
  await expect(
    page.getByText("1/5 lượt đã soát", { exact: true }),
  ).toBeVisible();
});

test("merge duplicate speaker groups and inspect edit history", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByRole("button", { name: "Người nói", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Quản lý người nói" });
  await dialog.getByLabel("Nhóm cần gộp").selectOption("C");
  await dialog.getByLabel("Gộp vào", { exact: true }).selectOption("B");
  await dialog.getByRole("button", { name: "Gộp 1 lượt nói" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(
    page.locator('.turn[data-turn-id="3"] .turn-meta strong'),
  ).toHaveText("Bình");
  await expect(page.locator(".meeting-heading")).toContainText("2 người nói");
  await page.getByRole("button", { name: "Lịch sử", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Lịch sử chỉnh sửa" }),
  ).toContainText("C → B · 1 lượt");
});

test("minutes templates regenerate and reveal revision conflicts", async ({
  page,
}) => {
  const { view, job } = await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByRole("tab", { name: "Tóm tắt & công việc" }).click();
  await page.getByLabel("Mẫu biên bản").selectOption("standup");
  await page.getByRole("button", { name: "Tạo lại", exact: true }).click();
  await expect.poll(() => view.summary_template).toBe("standup");
  await page.getByRole("tab", { name: "Transcript", exact: true }).click();
  const turn = page.locator('.turn[data-turn-id="1"]');
  await turn
    .getByRole("button", { name: "Sửa & xác nhận", exact: true })
    .click();
  await turn.getByLabel("Chỉnh sửa nội dung lượt nói").fill("Không ghi đè");
  view.revision = 20;
  job.revision = 20;
  await turn.getByRole("button", { name: "Lưu & đánh dấu đã soát" }).click();
  await expect(page.locator(".alert[role=alert]")).toContainText(
    "Nội dung đã thay đổi ở phiên khác",
  );
  await expect(turn.locator(".turn-text")).not.toHaveText("Không ghi đè");
});

test("mobile library transcript minutes and dialogs have no horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installFixture(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Thư viện cuộc họp", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /Họp tiến độ dự án.wav/ })
    .last()
    .click();
  await expect(page.locator(".turn")).toHaveCount(5);
  for (const tab of ["Transcript", "Tóm tắt & công việc", "Timeline"]) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
  await page.getByRole("button", { name: "Người nói", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/mobile-speakers.png",
    fullPage: true,
  });
});

test("unsupported upload, processing and failed state allow retry", async ({
  page,
}) => {
  const { job } = await installFixture(page, {
    empty: true,
    status: "running",
  });
  await page.goto("/");
  await page.getByLabel("Chọn bản ghi cuộc họp").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("x"),
  });
  await expect(page.locator(".alert[role=alert]")).toContainText(
    "WAV, MP3 hoặc M4A",
  );
  await page.getByLabel("Chọn bản ghi cuộc họp").setInputFiles({
    name: "meeting.wav",
    mimeType: "audio/wav",
    buffer: Buffer.from("x"),
  });
  await expect(
    page.getByRole("heading", { name: "Phiên âm nội dung", exact: true }),
  ).toBeVisible();
  job.status = "failed";
  job.stage = "failed";
  job.error = "Không đọc được audio";
  await expect(
    page.getByRole("heading", { name: "Chưa xử lý được bản ghi" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Phiên âm nội dung", exact: true }),
  ).toBeVisible();
});
