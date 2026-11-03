import { expect, Page, test } from "@playwright/test";
import { installFixture } from "./fixtures";

const noOverflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
const pause = (page: Page) =>
  page.locator("audio").evaluate((a) => (a as HTMLAudioElement).pause());
const currentTime = (page: Page) =>
  page.locator("audio").evaluate((a) => (a as HTMLAudioElement).currentTime);

test("upload opens the meeting with minutes first; edits, rename, finalize and export", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await installFixture(page, { empty: true });
  await page.goto("/");
  await expect(page.getByText("Kéo bản ghi cuộc họp vào đây")).toBeVisible();
  await page.getByRole("button", { name: "Tải bản ghi" }).click();
  await page.getByLabel("Chọn bản ghi cuộc họp").setInputFiles({
    name: "meeting.wav",
    mimeType: "audio/wav",
    buffer: Buffer.from("fixture"),
  });
  const minutes = page.getByRole("region", { name: "Biên bản" });
  await expect(
    minutes.getByText("Chốt bản thử nghiệm vào thứ Sáu."),
  ).toBeVisible();
  await expect(
    minutes.getByText("Kiểm thử và gửi báo cáo kết quả"),
  ).toBeVisible();

  const turn = page.locator('.turn[data-turn-id="1"]');
  await turn.getByRole("button", { name: "Sửa", exact: true }).click();
  await turn.getByLabel("Chỉnh sửa nội dung lượt nói").fill("Nội dung đã soát");
  await turn.getByLabel("Người nói").selectOption("A");
  await turn.getByLabel("Chỉnh sửa nội dung lượt nói").press("Control+Enter");
  await expect(turn.locator(".turn-body > p")).toHaveText("Nội dung đã soát");
  await expect(turn.locator(".turn-who")).toContainText("An");
  await expect(turn.getByText("đã nghe lại")).toBeVisible();
  await turn.getByText("Bản ban đầu").click();
  await expect(turn.locator(".original")).toContainText(
    "Tôi nhận phần kiểm thử",
  );
  await expect(
    minutes.getByText("Transcript đã sửa sau khi tạo biên bản."),
  ).toBeVisible();

  await page.getByRole("button", { name: "Họp tiến độ dự án" }).click();
  await page.getByLabel("Tên cuộc họp").fill("Họp chốt bản thử nghiệm");
  await page.getByLabel("Tên cuộc họp").press("Enter");
  await expect(
    page.getByRole("heading", { name: "Họp chốt bản thử nghiệm" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Chốt biên bản" }).click();
  await expect(page.getByRole("button", { name: "Đã chốt" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(
    page.getByRole("status").filter({ hasText: "Đã chốt biên bản." }),
  ).toBeVisible();

  await page.getByLabel("Thêm thao tác").click();
  await page
    .locator(".menu-panel")
    .getByRole("button", { name: "Sao chép danh sách việc" })
    .click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
    "☐ Kiểm thử và gửi báo cáo kết quả — Bình — hạn: Thứ Năm",
  );
  await page.getByLabel("Thêm thao tác").click();
  const download = page.waitForEvent("download");
  await page
    .locator(".menu-panel")
    .getByRole("link", { name: "Markdown" })
    .click();
  expect((await download).suggestedFilename()).toBe("meeting.md");

  await page.getByRole("button", { name: "Thư viện" }).click();
  const row = page.getByRole("button", { name: /Họp chốt bản thử nghiệm/ });
  await expect(row).toContainText("Đã chốt");
  await row.click();
  await expect(
    page.locator('.turn[data-turn-id="1"] .turn-body > p'),
  ).toHaveText("Nội dung đã soát");
});

test("evidence links jump to the source turn, clear search and play from it", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByLabel("Tìm trong transcript").fill("không có kết quả");
  await expect(page.getByText("Không tìm thấy lượt nói")).toBeVisible();
  await expect(page.getByText("Nguồn chưa rõ").first()).toBeVisible();
  await page
    .getByRole("button", { name: "Nghe dẫn chứng 00:10 Bình" })
    .first()
    .click();
  await expect(page.getByLabel("Tìm trong transcript")).toHaveValue("");
  await expect(page.locator('.turn[data-turn-id="1"]')).toHaveClass(/flash-/);
  await expect.poll(() => currentTime(page)).toBeGreaterThanOrEqual(10);
  await pause(page);
});

test("action items record done, owner and deadline", async ({ page }) => {
  const { minutes } = await installFixture(page);
  await page.goto("/?job=fixture");
  const item = page.locator(".action").first();
  await item.getByRole("button", { name: /Đánh dấu hoàn thành/ }).click();
  await expect(item).toHaveClass(/done/);
  await expect(
    page.getByRole("heading", { name: /Việc cần làm/ }),
  ).toContainText("1/1 xong");
  await item.getByLabel("Người làm").selectOption("Cả nhóm");
  await item.getByLabel("Hạn chót").fill("Thứ Sáu 17h");
  await item.getByLabel("Hạn chót").press("Enter");
  await expect.poll(() => minutes.action_items[0].deadline).toBe("Thứ Sáu 17h");
  expect(minutes.action_items[0]).toMatchObject({
    done: true,
    speaker: "Cả nhóm",
  });
});

test("review mode walks only the items behind the minutes", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByRole("button", { name: /2 mục/ }).click();
  await expect(page).toHaveURL(/view=review/);
  await expect(page.getByText("Mục 1 / 2")).toBeVisible();
  await expect(page.getByText(/Ảnh hưởng tới/)).toContainText(
    "Kiểm thử và gửi báo cáo kết quả",
  );
  await page.getByRole("button", { name: /Đúng rồi/ }).click();
  await expect(page.getByText("Mục 2 / 2")).toBeVisible();
  await page.keyboard.press("e");
  await page
    .getByLabel("Sửa lời nói")
    .fill("Tôi là Bình, tôi sẽ gửi báo cáo kiểm thử.");
  await page.getByLabel("Sửa lời nói").press("Control+Enter");
  await expect(
    page.getByRole("heading", { name: "Đã soát xong" }),
  ).toBeVisible();
  await expect(page.getByText("1 đúng · 1 đã sửa · 0 bỏ qua")).toBeVisible();
  await page
    .getByRole("button", { name: "Cập nhật biên bản theo bản sửa" })
    .click();
  await expect(page).not.toHaveURL(/view=review/);
  await expect(
    page.getByRole("button", { name: /mục/ }).filter({ hasText: "Soát ngay" }),
  ).toHaveCount(0);
  await pause(page);
});

test("speaker step names voices, plays a sample and merges a split speaker", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByRole("button", { name: /^Người nói/ }).click();
  await expect(
    page.getByRole("heading", { name: "Ai đang nói?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Nghe thử giọng An" }).click();
  await expect.poll(() => currentTime(page)).toBeGreaterThan(0);
  await pause(page);
  const nameA = page.locator("#speaker-A");
  await nameA.fill("Anh An");
  await nameA.press("Enter");
  await expect(page.getByText("Đã lưu")).toBeVisible();
  const card = page
    .locator(".speaker-card")
    .filter({ has: page.locator("#speaker-C") });
  await card.getByText("Cùng một người với giọng khác?").click();
  await card.getByLabel("Gộp vào").selectOption("B");
  await card.getByRole("button", { name: "Gộp 1 lượt" }).click();
  await expect(page.locator("#speaker-C")).toHaveCount(0);
  await page.getByRole("textbox", { name: "Người dự họp" }).fill("Trung, Đạt");
  await page.getByRole("button", { name: "Lưu danh sách" }).click();
  await expect(
    page.locator(".suggest").first().getByRole("button", { name: "Trung" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /^Xong/ }).click();
  await expect(page.locator('.turn[data-turn-id="0"] .turn-who')).toContainText(
    "Anh An",
  );
  await expect(page.locator('.turn[data-turn-id="3"] .turn-who')).toContainText(
    "Bình",
  );
  await expect(
    page
      .locator(".action")
      .first()
      .getByLabel("Người làm")
      .locator("option", { hasText: "Trung" }),
  ).toHaveCount(1);
  await page.getByLabel("Thêm thao tác").click();
  await page.getByRole("button", { name: "Lịch sử chỉnh sửa" }).click();
  await expect(
    page.getByRole("dialog", { name: "Lịch sử chỉnh sửa" }),
  ).toContainText("Người nói 03 → Bình · 1 lượt");
});

test("loop replays the turn and shortcuts ignore text inputs", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByRole("button", { name: "Nghe lượt 00:10" }).click();
  await page.getByRole("button", { name: "Lặp đoạn" }).click();
  await expect(page.getByRole("button", { name: "Lặp đoạn" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.locator("audio").evaluate(async (a) => {
    (a as HTMLAudioElement).currentTime = 12.99;
    await (a as HTMLAudioElement).play();
  });
  await expect.poll(() => currentTime(page)).toBeLessThan(12);
  await pause(page);
  await page.getByLabel("Tìm trong transcript").fill("jj ");
  await expect(page.getByLabel("Tìm trong transcript")).toHaveValue("jj ");
  await expect(page.getByRole("button", { name: "Phát audio" })).toBeVisible();
});

test("templates regenerate the minutes and revision conflicts are reported", async ({
  page,
}) => {
  const { view, job } = await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByLabel("Thêm thao tác").click();
  await page.getByLabel("Mẫu").selectOption("standup");
  await page.getByRole("button", { name: "Tạo lại biên bản" }).click();
  await expect.poll(() => view.summary_template).toBe("standup");
  const turn = page.locator('.turn[data-turn-id="1"]');
  await turn.getByRole("button", { name: "Sửa", exact: true }).click();
  await turn.getByLabel("Chỉnh sửa nội dung lượt nói").fill("Không ghi đè");
  view.revision = 20;
  job.revision = 20;
  await turn.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.locator(".banner[role=alert]")).toContainText(
    "Nội dung đã thay đổi ở phiên khác",
  );
  await expect(turn.locator(".turn-body > p")).not.toHaveText("Không ghi đè");
});

test("phone layouts have no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installFixture(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Cuộc họp", exact: true }),
  ).toBeVisible();
  expect(await noOverflow(page)).toBe(true);
  await page.getByRole("button", { name: /Họp tiến độ dự án/ }).click();
  await expect(page.locator(".turn")).toHaveCount(5);
  expect(await noOverflow(page)).toBe(true);
  await page.getByRole("button", { name: "Hỏi cuộc họp" }).click();
  expect(await noOverflow(page)).toBe(true);
  await page.getByLabel("Đóng hỏi đáp").click();
  await page.getByRole("button", { name: /^Người nói/ }).click();
  await expect(
    page.getByRole("heading", { name: "Ai đang nói?" }),
  ).toBeVisible();
  expect(await noOverflow(page)).toBe(true);
  await page.goto("/?job=fixture&view=review");
  await expect(page.getByText("Mục 1 / 2")).toBeVisible();
  expect(await noOverflow(page)).toBe(true);
  await pause(page);
});

test("unsupported upload, processing and failed state allow retry", async ({
  page,
}) => {
  const { job } = await installFixture(page, {
    empty: true,
    status: "running",
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Tải bản ghi" }).click();
  await page.getByLabel("Chọn bản ghi cuộc họp").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("x"),
  });
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "WAV, MP3 hoặc M4A",
  );
  await page.getByLabel("Chọn bản ghi cuộc họp").setInputFiles({
    name: "meeting.wav",
    mimeType: "audio/wav",
    buffer: Buffer.from("x"),
  });
  await expect(
    page.getByRole("heading", { name: "Đang chép lời" }),
  ).toBeVisible();
  await expect(page.getByText("còn khoảng 3 phút")).toBeVisible();
  job.status = "failed";
  job.stage = "failed";
  job.error = "Không đọc được audio";
  await expect(
    page.getByRole("heading", { name: "Chưa xử lý được bản ghi" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Đang chép lời" }),
  ).toBeVisible();
});
