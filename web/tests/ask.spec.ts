import { expect, test } from "@playwright/test";
import { installFixture } from "./fixtures";

test("AskMeeting cites audio, restores history and uses corrected transcript", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByRole("tab", { name: "Hỏi đáp", exact: true }).click();
  await expect(page.getByText("Bạn muốn tìm lại điều gì?")).toBeVisible();
  await page
    .getByRole("button", { name: "Ai nhận phần kiểm thử?", exact: true })
    .click();
  await page.getByLabel("Câu hỏi của bạn").press("Control+Enter");
  await expect(page.locator(".ask-answer")).toHaveCount(1);
  await expect(page.locator(".ask-answer")).toContainText("Bình nhận kiểm thử");
  await expect(page.locator(".ask-evidence")).toContainText(
    "Tôi nhận phần kiểm thử",
  );
  await expect(page.locator(".ask-evidence")).toContainText("Nguồn cần soát");
  await page
    .getByRole("button", { name: "Nghe nguồn hỏi đáp 00:10 Bình" })
    .click();
  await expect(page.locator('.turn[data-turn-id="1"]')).toHaveClass(/selected/);
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((a) => (a as HTMLAudioElement).currentTime),
    )
    .toBeGreaterThanOrEqual(10);
  await page.locator("audio").evaluate((a) => (a as HTMLAudioElement).pause());
  const turn = page.locator('.turn[data-turn-id="1"]');
  await turn
    .getByRole("button", { name: "Sửa & xác nhận", exact: true })
    .click();
  await turn
    .getByLabel("Chỉnh sửa nội dung lượt nói")
    .fill("An nhận kiểm thử vào thứ Sáu.");
  await turn.getByLabel("Người nói của lượt này").selectOption("A");
  await turn.getByLabel("Chỉnh sửa nội dung lượt nói").press("Control+Enter");
  await expect(turn.locator(".turn-text")).toHaveText(
    "An nhận kiểm thử vào thứ Sáu.",
  );
  await page.getByRole("tab", { name: "Hỏi đáp", exact: true }).click();
  await expect(page.locator(".ask-answer")).toContainText(
    "Transcript đã thay đổi",
  );
  await page
    .getByRole("button", { name: /Hỏi lại với transcript hiện tại/ })
    .click();
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  await expect(page.locator(".ask-answer")).toHaveCount(2);
  await expect(page.locator(".ask-answer").first()).toContainText(
    "An nhận kiểm thử",
  );
  await expect(page.locator(".ask-answer").first()).not.toContainText(
    "Nguồn cần soát",
  );
  await page.reload();
  await page.getByRole("tab", { name: "Hỏi đáp", exact: true }).click();
  await expect(page.locator(".ask-answer")).toHaveCount(2);
});

test("missing evidence abstains and disabled LLM keeps the panel usable", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByRole("tab", { name: "Hỏi đáp", exact: true }).click();
  await page.getByLabel("Câu hỏi của bạn").fill("Ngân sách là bao nhiêu?");
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  await expect(
    page.getByText("Chưa tìm thấy câu trả lời có dẫn chứng."),
  ).toBeVisible();
  await expect(page.locator(".ask-evidence")).toHaveCount(0);
  await page.getByLabel("Câu hỏi của bạn").fill("   ");
  await expect(
    page.getByRole("button", { name: "Gửi câu hỏi", exact: true }),
  ).toBeDisabled();
  await page.unrouteAll();
  await installFixture(page, { llm: false });
  await page.reload();
  await page.getByRole("tab", { name: "Hỏi đáp", exact: true }).click();
  await expect(page.getByText(/Bật dịch vụ LLM/)).toBeVisible();
  await expect(page.getByLabel("Câu hỏi của bạn")).toBeDisabled();
});

test("request conflicts preserve the question and pending requests cannot double-submit", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByRole("tab", { name: "Hỏi đáp", exact: true }).click();
  let calls = 0;
  await page.route("**/api/jobs/fixture/questions", async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    calls++;
    await new Promise((resolve) => setTimeout(resolve, 300));
    return route.fulfill({
      status: 409,
      json: { detail: "transcript changed; reload before asking" },
    });
  });
  await page.getByLabel("Câu hỏi của bạn").fill("Ai nhận kiểm thử?");
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Đang tìm câu trả lời…" }),
  ).toBeDisabled();
  await expect(page.locator(".ask-panel").getByRole("alert")).toContainText(
    "Nội dung đã thay đổi ở phiên khác",
  );
  await expect(page.getByLabel("Câu hỏi của bạn")).toHaveValue(
    "Ai nhận kiểm thử?",
  );
  expect(calls).toBe(1);
  await expect(page.locator(".ask-answer")).toHaveCount(0);
});

test("mobile question composer and cited answers do not overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installFixture(page);
  await page.goto("/?job=fixture");
  await page.getByRole("tab", { name: "Hỏi đáp", exact: true }).click();
  await page.getByLabel("Câu hỏi của bạn").fill("Deadline kiểm thử?");
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  await expect(page.locator(".ask-answer")).toHaveCount(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Nghe nguồn hỏi đáp 00:10 Bình" })
    .click();
  await expect(
    page.getByRole("tab", { name: "Transcript", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
});
