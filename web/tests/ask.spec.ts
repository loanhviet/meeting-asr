import { expect, test } from "@playwright/test";
import { installFixture } from "./fixtures";

const openAsk = async (page: import("@playwright/test").Page) => {
  await page.getByRole("button", { name: "Hỏi cuộc họp" }).click();
  await expect(
    page.getByRole("complementary", { name: "Hỏi cuộc họp" }),
  ).toBeVisible();
};

test("ask cites audio, keeps history and flags answers after transcript edits", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await openAsk(page);
  await page.getByLabel("Câu hỏi của bạn").fill("Ai nhận phần kiểm thử?");
  await page.getByLabel("Câu hỏi của bạn").press("Enter");
  const exchange = page.locator(".exchange");
  await expect(exchange).toHaveCount(1);
  await expect(exchange).toContainText("Bình nhận kiểm thử");
  await expect(exchange).toContainText("Tôi nhận phần kiểm thử");
  await page
    .getByRole("button", { name: "Nghe nguồn hỏi đáp 00:10 Bình" })
    .click();
  await expect(page.locator('.turn[data-turn-id="1"]')).toHaveClass(/flash-/);
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((a) => (a as HTMLAudioElement).currentTime),
    )
    .toBeGreaterThanOrEqual(10);
  await page.locator("audio").evaluate((a) => (a as HTMLAudioElement).pause());
  await page.getByLabel("Đóng hỏi đáp").click();

  const turn = page.locator('.turn[data-turn-id="1"]');
  await turn.getByRole("button", { name: "Sửa", exact: true }).click();
  await turn
    .getByLabel("Chỉnh sửa nội dung lượt nói")
    .fill("An nhận kiểm thử vào thứ Sáu.");
  await turn.getByLabel("Người nói").selectOption("A");
  await turn.getByLabel("Chỉnh sửa nội dung lượt nói").press("Control+Enter");
  await expect(turn.locator(".turn-body > p")).toHaveText(
    "An nhận kiểm thử vào thứ Sáu.",
  );

  await openAsk(page);
  await expect(exchange.first()).toContainText("Transcript đã thay đổi");
  await page
    .getByRole("button", { name: /Hỏi lại với transcript hiện tại/ })
    .click();
  await expect(exchange).toHaveCount(2);
  await expect(exchange.last()).toContainText("An nhận kiểm thử");
  await page.reload();
  await openAsk(page);
  await expect(exchange).toHaveCount(2);
});

test("suggestions come from the minutes; missing evidence abstains; disabled LLM", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await openAsk(page);
  const suggestions = page.getByLabel("Câu hỏi gợi ý");
  await expect(suggestions.getByRole("button")).toContainText([
    "Nhóm đã chốt những gì?",
  ]);
  await page.getByLabel("Câu hỏi của bạn").fill("Ngân sách là bao nhiêu?");
  await page.getByRole("button", { name: "Hỏi", exact: true }).click();
  await expect(
    page.getByText("Chưa tìm thấy câu trả lời có dẫn chứng."),
  ).toBeVisible();
  await page.getByLabel("Câu hỏi của bạn").fill("   ");
  await expect(
    page.getByRole("button", { name: "Hỏi", exact: true }),
  ).toBeDisabled();
  await page.unrouteAll();
  await installFixture(page, { llm: false });
  await page.reload();
  await openAsk(page);
  await expect(page.getByText(/Bật dịch vụ LLM/)).toBeVisible();
  await expect(page.getByLabel("Câu hỏi của bạn")).toBeDisabled();
});

test("conflicts keep the question and a pending request cannot double-submit", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/?job=fixture");
  await openAsk(page);
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
  await page.getByRole("button", { name: "Hỏi", exact: true }).click();
  await expect(page.getByRole("button", { name: "Đang hỏi…" })).toBeDisabled();
  await expect(
    page
      .getByRole("complementary", { name: "Hỏi cuộc họp" })
      .getByRole("alert"),
  ).toContainText("Nội dung đã thay đổi ở phiên khác");
  await expect(page.getByLabel("Câu hỏi của bạn")).toHaveValue(
    "Ai nhận kiểm thử?",
  );
  expect(calls).toBe(1);
  await expect(page.locator(".exchange")).toHaveCount(0);
});
