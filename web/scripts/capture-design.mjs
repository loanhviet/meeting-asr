// Export the complete UI with synthetic fixtures as self-contained editable HTML.
// Run with the local web server running. No user meetings are read or sent.
import { chromium, expect } from "@playwright/test";
import ts from "typescript";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import { tmpdir } from "node:os";

const root = path.resolve(fileURLToPath(new URL("../..", import.meta.url)));
const output =
  process.env.MEETING_CAPTURE_DIR || path.join(root, "results/ui-redesign");
await mkdir(output, { recursive: true });
const fixturePath = path.join(
  tmpdir(),
  `meeting-design-fixture-${process.pid}.mjs`,
);
const source = await readFile(
  new URL("../tests/fixtures.ts", import.meta.url),
  "utf8",
);
await writeFile(
  fixturePath,
  ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText,
);
const { installFixture } = await import(pathToFileURL(fixturePath).href);
const browser = await chromium.launch();
const screens = [];
const errors = [];
const props = [
  "display",
  "position",
  "box-sizing",
  "width",
  "height",
  "min-width",
  "min-height",
  "max-width",
  "max-height",
  "margin",
  "padding",
  "gap",
  "flex",
  "flex-direction",
  "flex-wrap",
  "flex-shrink",
  "align-items",
  "justify-content",
  "grid-template-columns",
  "grid-column",
  "border",
  "border-top",
  "border-right",
  "border-left",
  "border-bottom",
  "border-radius",
  "background",
  "color",
  "font-family",
  "font-size",
  "font-weight",
  "line-height",
  "letter-spacing",
  "text-align",
  "white-space",
  "overflow",
  "overflow-wrap",
  "text-overflow",
  "box-shadow",
  "opacity",
  "top",
  "right",
  "bottom",
  "left",
  "z-index",
  "list-style",
  "accent-color",
  "appearance",
];
async function capture(page, name) {
  await page.evaluate(() => {
    document.querySelector("audio")?.pause();
    window.scrollTo(0, 0);
  });
  await page.screenshot({ path: path.join(output, `${name}.png`) });
  const snapshot = await page.evaluate(
    ({ props, name }) => {
      const original = document.querySelector(".workspace");
      const clone = original.cloneNode(true);
      const from = [original, ...original.querySelectorAll("*")];
      const to = [clone, ...clone.querySelectorAll("*")];
      from.forEach((node, index) => {
        const target = to[index],
          style = getComputedStyle(node);
        if (!(target instanceof HTMLElement) && !(target instanceof SVGElement))
          return;
        target.setAttribute(
          "style",
          props
            .map((prop) => `${prop}:${style.getPropertyValue(prop)}`)
            .join(";"),
        );
        if (node instanceof HTMLInputElement)
          target.setAttribute("value", node.value);
        if (node instanceof HTMLTextAreaElement)
          target.textContent = node.value;
        if (node instanceof HTMLSelectElement) {
          Array.from(target.options).forEach((option) => {
            if (option.value === node.value)
              option.setAttribute("selected", "");
            else option.removeAttribute("selected");
          });
        }
        if (node instanceof HTMLProgressElement) {
          target.setAttribute(
            "style",
            `${target.getAttribute("style")};background:linear-gradient(to right,#5364d9 ${(node.value / node.max) * 100}%,#e9edf5 0);appearance:none`,
          );
        }
        if (style.position === "fixed" || node instanceof HTMLDialogElement) {
          const rect = node.getBoundingClientRect();
          target.style.position = "absolute";
          target.style.left = `${rect.left}px`;
          target.style.top = `${rect.top}px`;
          target.style.right = "auto";
          target.style.bottom = "auto";
          target.style.margin = "0";
        } else if (style.position === "sticky") {
          target.style.position = "relative";
          target.style.top = "0";
        }
        if (node instanceof HTMLDialogElement) {
          const panel = document.createElement("div");
          panel.className = "capture-backdrop";
          panel.style.cssText =
            "position:absolute;inset:0;background:#15243770;z-index:90";
          clone.append(panel);
          target.style.zIndex = "100";
        }
      });
      clone.style.position = "relative";
      clone.style.width = `${innerWidth}px`;
      clone.style.height = `${innerHeight}px`;
      const section = document.createElement("section");
      section.className = "design-screen";
      section.setAttribute("aria-label", name);
      section.setAttribute("data-screen", name);
      section.style.cssText = `position:relative;width:${innerWidth}px;height:${innerHeight}px;overflow:hidden;background:#f3f5f9;margin-bottom:80px`;
      section.append(clone);
      section
        .querySelectorAll("audio,script,.sr-only")
        .forEach((node) => node.remove());
      section.querySelectorAll("details").forEach((node) => {
        if (!node.open)
          Array.from(node.children).forEach((child) => {
            if (child.tagName !== "SUMMARY") child.remove();
          });
        const div = document.createElement("div");
        Array.from(node.attributes).forEach((attr) =>
          div.setAttribute(attr.name, attr.value),
        );
        while (node.firstChild) div.appendChild(node.firstChild);
        node.replaceWith(div);
      });
      section.querySelectorAll("summary").forEach((node) => {
        const div = document.createElement("div");
        Array.from(node.attributes).forEach((attr) =>
          div.setAttribute(attr.name, attr.value),
        );
        while (node.firstChild) div.appendChild(node.firstChild);
        node.replaceWith(div);
      });
      const icons = Array.from(original.querySelectorAll("svg"))
        .filter((node) => {
          const r = node.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        })
        .map((node) => ({
          svg: node.outerHTML.replaceAll(
            "currentColor",
            getComputedStyle(node).color,
          ),
          x: node.getBoundingClientRect().x,
          y: node.getBoundingClientRect().y,
          width: node.getBoundingClientRect().width,
          height: node.getBoundingClientRect().height,
        }));
      return {
        name,
        width: innerWidth,
        height: innerHeight,
        icons,
        html: section.outerHTML,
      };
    },
    { props, name },
  );
  screens.push(snapshot);
}
async function fresh(width, options = {}) {
  const page = await browser.newPage({
    viewport: { width, height: width < 500 ? 844 : 1000 },
  });
  page.on("pageerror", (error) => errors.push(error.message));
  const fixture = await installFixture(page, options);
  await page.goto(process.env.MEETING_WEB_URL || "http://127.0.0.1:3000");
  await expect(page.locator("h1")).toBeVisible();
  await expect(page.locator(".sidebar-title")).toContainText("GẦN ĐÂY");
  return { page, fixture };
}
async function openMeeting(page) {
  await page.locator(".meeting-row").first().click();
  await expect(page.locator(".turn")).toHaveCount(5);
  await page.waitForFunction(
    () => document.querySelector("audio")?.readyState >= 1,
  );
}
try {
  const { page } = await fresh(1440);
  await expect(page.locator(".meeting-row")).toHaveCount(1);
  await capture(page, "01-desktop-library");
  await page.getByRole("button", { name: "Cuộc họp mới" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await capture(page, "02-desktop-upload");
  await page.getByRole("button", { name: "Đóng", exact: true }).click();
  await openMeeting(page);
  await capture(page, "03-desktop-transcript-minutes");
  await page
    .locator('.turn[data-turn-id="1"]')
    .getByRole("button", { name: "Sửa & xác nhận", exact: true })
    .click();
  await capture(page, "04-desktop-turn-editor");
  await page
    .locator('.turn[data-turn-id="1"]')
    .getByRole("button", { name: "Hủy", exact: true })
    .click();
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await capture(page, "05-desktop-speaker-timeline");
  await page
    .getByRole("tab", { name: "Tóm tắt & công việc", exact: true })
    .click();
  await capture(page, "06-desktop-grounded-minutes");
  await page.getByRole("button", { name: "Người nói", exact: true }).click();
  await capture(page, "07-desktop-speaker-management");
  await page.getByRole("button", { name: "Đóng", exact: true }).click();
  await page.getByRole("tab", { name: "Transcript", exact: true }).click();
  const editor = page.locator('.turn[data-turn-id="1"]');
  await editor
    .getByRole("button", { name: "Sửa & xác nhận", exact: true })
    .click();
  await editor
    .getByLabel("Chỉnh sửa nội dung lượt nói")
    .fill("Bình xác nhận gửi báo cáo kiểm thử trước thứ Năm.");
  await editor
    .getByRole("button", { name: "Lưu & đánh dấu đã soát", exact: true })
    .click();
  await expect(editor.getByText("✓ Đã soát", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Lịch sử", exact: true }).click();
  await expect(page.locator(".history-list li")).toHaveCount(1);
  await capture(page, "08-desktop-edit-history");
  await page.getByRole("button", { name: "Đóng", exact: true }).click();
  await page
    .getByRole("tab", { name: "Tóm tắt & công việc", exact: true })
    .click();
  await capture(page, "09-desktop-stale-minutes");
  await page.getByText("Xuất biên bản", { exact: true }).click();
  await capture(page, "10-desktop-export");
  await page.close();
  for (const [status, name] of [
    ["running", "11-desktop-processing"],
    ["failed", "12-desktop-processing-error"],
  ]) {
    const { page: state } = await fresh(1440, { status });
    await expect(state.locator(".meeting-row")).toHaveCount(1);
    await state.locator(".meeting-row").click();
    await expect(
      state.locator(status === "running" ? ".processing" : ".failure-state"),
    ).toBeVisible();
    await capture(state, name);
    await state.close();
  }
  const { page: empty } = await fresh(1440, { empty: true });
  await expect(
    empty.getByRole("heading", { name: "Ghi lại những điều quan trọng." }),
  ).toBeVisible();
  await capture(empty, "13-desktop-empty-library");
  await empty.close();
  const { page: mobile } = await fresh(390);
  await expect(mobile.locator(".meeting-row")).toHaveCount(1);
  await capture(mobile, "14-mobile-library");
  await openMeeting(mobile);
  await capture(mobile, "15-mobile-transcript");
  await mobile
    .getByRole("tab", { name: "Tóm tắt & công việc", exact: true })
    .click();
  await capture(mobile, "16-mobile-grounded-minutes");
  await mobile.getByRole("button", { name: "Người nói", exact: true }).click();
  await capture(mobile, "17-mobile-speaker-management");
  await mobile.close();
  if (errors.length) throw new Error(JSON.stringify(errors));
  const html = `<!doctype html><html lang="vi"><head><meta charset="UTF-8"><title>Meeting Notes — Complete UI</title><style>button{border:0}body{margin:0;background:#e8edf4;font-family:Arial,Helvetica,sans-serif}*{box-sizing:border-box}.design-screen{display:block}dialog[open]{display:block}svg{flex-shrink:0}summary{list-style:none}</style></head><body>${screens.map((s) => s.html).join("\n")}</body></html>`;
  await writeFile(path.join(output, "figma-screens.html"), html);
  await writeFile(
    path.join(output, "screens.json"),
    JSON.stringify(
      screens.map(({ html, ...screen }) => screen),
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({ screens: screens.length, output, page_errors: errors }),
  );
} finally {
  await browser.close();
}
